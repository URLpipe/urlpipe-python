from __future__ import annotations

from typing import Any

import pytest

import urlpipe
from urlpipe import _core
from conftest import StubServer


def test_a_503_is_retried_with_the_same_idempotency_key(client: Any, server: StubServer) -> None:
    server.reply(503, {"error": "unavailable"}).reply(200, "# Hello")

    response = client.markdown("https://example.com")

    assert response.data == "# Hello"
    first, second = server.requests
    assert first.headers["idempotency-key"] == second.headers["idempotency-key"]
    assert first.json == second.json


def test_the_callers_idempotency_key_is_reused(client: Any, server: StubServer) -> None:
    server.reply(500, "").reply(502, "").reply(200, "ok")

    client.html("https://example.com", idempotency_key="order-42")

    assert [r.headers["idempotency-key"] for r in server.requests] == ["order-42"] * 3


def test_retries_stop_at_max_retries(make_client: Any, server: StubServer) -> None:
    for _ in range(4):
        server.reply(503, {"error": "unavailable"})

    with pytest.raises(urlpipe.ServerError):
        make_client(max_retries=2).markdown("https://example.com")

    assert len(server.requests) == 3


@pytest.mark.parametrize(
    "status, body, error",
    [
        (422, {"error": "The request timed out."}, urlpipe.AnalysisFailedError),
        (422, {"error": "invalid_url"}, urlpipe.InvalidRequestError),
        (401, {"error": "unauthorized"}, urlpipe.AuthenticationError),
        (403, {"error": "email_unverified"}, urlpipe.EmailUnverifiedError),
        (429, {"error": "quota_exceeded", "limit": 1000}, urlpipe.QuotaExceededError),
        (504, {"error": "gateway"}, urlpipe.ServerError),
    ],
)
def test_errors_that_are_not_retried(
    client: Any, server: StubServer, status: int, body: Any, error: type
) -> None:
    server.reply(status, body).reply(200, "ok")

    with pytest.raises(error):
        client.markdown("https://example.com")

    assert len(server.requests) == 1


def test_rate_limited_honours_retry_after(client: Any, server: StubServer) -> None:
    server.reply(429, {"error": "rate_limited", "retry_after": 0}, headers={"Retry-After": "0"})
    server.reply(200, "ok")

    assert client.markdown("https://example.com").data == "ok"
    assert len(server.requests) == 2


def test_concurrency_limit_is_retried(client: Any, server: StubServer) -> None:
    server.reply(429, {"error": "concurrency_limit", "limit": 1, "running": 1})
    server.reply(200, "ok")

    assert client.markdown("https://example.com").data == "ok"
    first, second = server.requests
    assert first.headers["idempotency-key"] == second.headers["idempotency-key"]


def test_result_polls_are_retried_too(client: Any, server: StubServer) -> None:
    server.reply(502, "").reply(200, "ok")
    assert client.result("tok").data == "ok"
    assert [r.path for r in server.requests] == ["/result/tok", "/result/tok"]


def test_a_connection_error_surfaces_once_retries_run_out(make_client: Any, unused_port: int) -> None:
    client = make_client(base_url=f"http://127.0.0.1:{unused_port}", max_retries=2)
    with pytest.raises(urlpipe.APIConnectionError):
        client.markdown("https://example.com")


def rate_limited(retry_after: Any) -> urlpipe.RateLimitedError:
    return urlpipe.RateLimitedError("slow down", retry_after=retry_after, status=429)


def test_retry_delay_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_core, "BACKOFF_BASE", 1.0)
    busy = urlpipe.ConcurrencyLimitError("busy", status=429)
    down = urlpipe.ServerError("down", status=503)

    assert [_core.retry_delay(busy, n, 5) for n in range(4)] == [1.0, 2.0, 4.0, 8.0]
    assert _core.retry_delay(down, 0, 2) == 1.0
    assert _core.retry_delay(urlpipe.APIConnectionError("x"), 1, 2) == 2.0
    assert _core.retry_delay(rate_limited(12), 0, 2) == 12
    assert _core.retry_delay(rate_limited(3600), 0, 2) == 60.0
    assert _core.retry_delay(rate_limited(None), 1, 2) == 1.0  # D4: 1 s without Retry-After
    assert _core.retry_delay(busy, 7, 10) == 60.0  # D4: backoff capped at 60 s
    assert _core.retry_delay(urlpipe.APIConnectionError("x"), 9, 10) == 60.0
    assert _core.retry_delay(busy, 2, 2) is None
    assert _core.retry_delay(urlpipe.ServerError("x", status=501), 0, 2) is None


def test_d6_result_retries_a_503_without_an_idempotency_key(
    client: Any, server: StubServer
) -> None:
    server.reply(503, "").reply(200, "ok")
    assert client.result("tok").data == "ok"
    assert len(server.requests) == 2
    assert sorted(server.requests[0].headers) == [
        "accept", "accept-encoding", "authorization", "connection", "host", "user-agent",
    ]


def test_d6_result_504_that_is_not_processing_is_a_server_error(
    client: Any, server: StubServer
) -> None:
    server.reply(504, "Gateway Timeout").reply(200, "ok")
    with pytest.raises(urlpipe.ServerError):
        client.result("tok")
    assert len(server.requests) == 1
