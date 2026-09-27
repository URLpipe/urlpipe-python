from __future__ import annotations

import asyncio
from typing import Any, List

import httpx
import pytest

import urlpipe
from conftest import API_KEY, StubServer


@pytest.mark.parametrize("cls", [urlpipe.Client, urlpipe.AsyncClient])
def test_an_api_key_is_required(cls: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("URLPIPE_API_KEY", raising=False)
    with pytest.raises(urlpipe.ConfigurationError, match="URLPIPE_API_KEY"):
        cls()


def test_the_api_key_falls_back_to_the_environment(
    server: StubServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("URLPIPE_API_KEY", "from_env")
    server.reply(200, "ok")
    with urlpipe.Client(base_url=server.url) as client:
        client.markdown("https://example.com")
    assert server.requests[0].headers["authorization"] == "Bearer from_env"


def test_defaults() -> None:
    client = urlpipe.Client(api_key="k")
    assert client.base_url == "https://urlpipe.dev"
    assert client.timeout == 90.0
    assert client.max_retries == 2
    assert client.wait_timeout == 300.0


def test_a_trailing_slash_on_the_base_url(server: StubServer) -> None:
    server.reply(200, "ok")
    urlpipe.Client(api_key=API_KEY, base_url=server.url + "/").markdown("https://example.com")
    assert server.requests[0].path == "/markdown"


def test_an_injected_http_client_is_used_and_left_open(server: StubServer) -> None:
    seen: List[str] = []
    http = httpx.Client(event_hooks={"request": [lambda r: seen.append(r.url.path)]})
    server.reply(200, "ok")

    with urlpipe.Client(api_key=API_KEY, base_url=server.url, http_client=http) as client:
        client.markdown("https://example.com")

    assert seen == ["/markdown"]
    assert http.is_closed is False
    http.close()


def test_an_injected_async_http_client(server: StubServer) -> None:
    seen: List[str] = []

    async def hook(request: httpx.Request) -> None:
        seen.append(request.url.path)

    async def run() -> bool:
        async with httpx.AsyncClient(event_hooks={"request": [hook]}) as http:
            async with urlpipe.AsyncClient(
                api_key=API_KEY, base_url=server.url, http_client=http
            ) as client:
                await client.keywords("https://example.com")
            return http.is_closed

    server.reply(200, ["a"])
    assert asyncio.run(run()) is False
    assert seen == ["/keywords"]


def test_the_client_closes_its_own_pool() -> None:
    client = urlpipe.Client(api_key="k")
    with client:
        pass
    assert client._http.is_closed is True


def test_async_calls_run_concurrently(server: StubServer) -> None:
    async def run() -> List[str]:
        async with urlpipe.AsyncClient(api_key=API_KEY, base_url=server.url) as client:
            results = await asyncio.gather(
                client.markdown("https://example.com/a"),
                client.markdown("https://example.com/b"),
            )
        return [r.data for r in results]

    server.reply(200, "one").reply(200, "two")
    assert sorted(asyncio.run(run())) == ["one", "two"]


def test_the_timeout_is_applied_per_request(server: StubServer) -> None:
    seen: List[Any] = []
    http = httpx.Client(event_hooks={"request": [lambda r: seen.append(r.extensions["timeout"])]})
    server.reply(200, "ok")
    urlpipe.Client(api_key=API_KEY, base_url=server.url, timeout=12, http_client=http).html(
        "https://example.com"
    )
    assert seen[0]["read"] == 12.0


def test_version() -> None:
    assert urlpipe.__version__ == "0.1.0"
