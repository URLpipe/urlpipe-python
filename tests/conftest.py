"""A real local HTTP server the clients talk to, and fixtures that run every
test against both ``Client`` and ``AsyncClient``."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

import pytest

import urlpipe
from urlpipe import _core

API_KEY = "test_key_123"

META_HEADERS = {
    "X-Result-Token": "tok_123",
    "X-Cache": "miss",
    "X-Processing-Time-Ms": "4182",
    "X-Quota-Cost": "1",
    "X-Quota-Limit": "1000",
    "X-Quota-Remaining": "943",
    "X-Quota-Overage": "0",
    "X-Quota-Reset": "2026-08-31T23:59:59Z",
    "X-Concurrency-Limit": "3",
}


@dataclass
class Recorded:
    method: str
    path: str
    headers: Dict[str, str]
    body: bytes

    @property
    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class Reply:
    status: int = 200
    body: Union[str, bytes, Any] = ""
    headers: Dict[str, str] = field(default_factory=dict)
    content_type: Optional[str] = None


class StubServer:
    """Answers each request with the next queued Reply, recording the request."""

    def __init__(self) -> None:
        self.replies: List[Reply] = []
        self.requests: List[Recorded] = []
        self._lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                with stub._lock:
                    stub.requests.append(
                        Recorded(
                            self.command,
                            self.path,
                            {k.lower(): v for k, v in self.headers.items()},
                            body,
                        )
                    )
                    reply = stub.replies.pop(0) if stub.replies else Reply(
                        599, {"error": "no reply queued"}
                    )
                payload, content_type = _encode(reply)
                self.send_response(reply.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _handle
            do_POST = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def reply(
        self,
        status: int = 200,
        body: Union[str, bytes, Any] = "",
        headers: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
    ) -> "StubServer":
        self.replies.append(Reply(status, body, dict(headers or {}), content_type))
        return self

    def reset(self) -> None:
        self.replies.clear()
        self.requests.clear()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _encode(reply: Reply) -> "tuple[bytes, str]":
    if isinstance(reply.body, bytes):
        return reply.body, reply.content_type or "application/octet-stream"
    if isinstance(reply.body, str):
        return reply.body.encode(), reply.content_type or "text/plain; charset=utf-8"
    return (
        json.dumps(reply.body).encode(),
        reply.content_type or "application/json; charset=utf-8",
    )


@pytest.fixture(scope="session")
def _server() -> Iterator[StubServer]:
    server = StubServer()
    yield server
    server.close()


@pytest.fixture
def server(_server: StubServer) -> Iterator[StubServer]:
    _server.reset()
    yield _server
    _server.reset()


@pytest.fixture(autouse=True)
def fast_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the backoff and poll interval so the suite runs in seconds."""
    monkeypatch.setattr(_core, "BACKOFF_BASE", 0.0)
    monkeypatch.setattr(_core, "POLL_INTERVAL", 0.01)


class AsyncAdapter:
    """Calls AsyncClient methods from synchronous test code.

    Each call gets its own event loop and its own AsyncClient, so the tests for
    both clients read the same.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        urlpipe.AsyncClient(**kwargs)  # construction errors surface here, as for Client

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            async def run() -> Any:
                async with urlpipe.AsyncClient(**self._kwargs) as client:
                    return await getattr(client, name)(*args, **kwargs)

            return asyncio.run(run())

        return call


@pytest.fixture(params=["sync", "async"])
def make_client(request: pytest.FixtureRequest, server: StubServer) -> Callable[..., Any]:
    """A factory for a client of either kind pointed at the stub server."""

    def make(**overrides: Any) -> Any:
        kwargs: Dict[str, Any] = {"api_key": API_KEY, "base_url": server.url}
        kwargs.update(overrides)
        if request.param == "sync":
            return urlpipe.Client(**kwargs)
        return AsyncAdapter(**kwargs)

    return make


@pytest.fixture
def client(make_client: Callable[..., Any]) -> Any:
    return make_client()


@pytest.fixture
def unused_port() -> int:
    """A local port nothing listens on."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
