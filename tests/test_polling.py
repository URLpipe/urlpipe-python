from __future__ import annotations

import base64
from typing import Any

import pytest

import urlpipe
from conftest import StubServer

TIMEOUT_BODY = {
    "error": "processing_timeout",
    "message": "The analysis is taking longer than expected.",
    "token": "tok_slow",
}
PROCESSING = {"status": "processing", "token": "tok_slow", "labels": {}}


def test_a_sync_timeout_is_polled_to_completion(client: Any, server: StubServer) -> None:
    server.reply(504, TIMEOUT_BODY, headers={"X-Result-Token": "tok_slow"})
    server.reply(202, PROCESSING).reply(202, PROCESSING)
    server.reply(200, {"title": "Example Domain"},
                 headers={"X-Result-Token": "tok_slow", "X-Processing-Time-Ms": "71000"})

    response = client.meta("https://example.com")

    assert [(r.method, r.path) for r in server.requests] == [
        ("POST", "/meta"),
        ("GET", "/result/tok_slow"),
        ("GET", "/result/tok_slow"),
        ("GET", "/result/tok_slow"),
    ]
    assert response.status == "completed"
    assert response.data == {"title": "Example Domain"}
    assert response.token == "tok_slow"
    assert response.meta.processing_time_ms == 71000


def test_polling_types_data_by_the_original_operation(client: Any, server: StubServer) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x01" * 8
    server.reply(504, TIMEOUT_BODY)
    server.reply(200, base64.b64encode(png).decode(), headers={"X-Result-Url": "https://u/i"})

    shot = client.screenshot("https://example.com").data

    assert shot.data == png
    assert shot.mime_type == "image/png"
    assert shot.result_url == "https://u/i"


def test_polling_surfaces_a_real_error(client: Any, server: StubServer) -> None:
    server.reply(504, TIMEOUT_BODY).reply(422, {"error": "The page could not be loaded."})
    with pytest.raises(urlpipe.AnalysisFailedError):
        client.markdown("https://example.com")


def test_polling_gives_up_at_wait_timeout(make_client: Any, server: StubServer) -> None:
    server.reply(504, TIMEOUT_BODY)
    for _ in range(50):
        server.reply(202, PROCESSING)

    with pytest.raises(urlpipe.WaitTimeoutError) as info:
        make_client(wait_timeout=0.05).lighthouse("https://example.com")

    assert info.value.token == "tok_slow"
    assert info.value.timeout == 0.05
    assert server.requests[1].path == "/result/tok_slow"


def test_wait_polls_an_async_token(client: Any, server: StubServer) -> None:
    server.reply(202, PROCESSING).reply(200, "# Done", headers={"X-Result-Token": "tok_slow"})

    response = client.wait("tok_slow", operation="markdown", interval=0.01)

    assert response.data == "# Done"
    assert len(server.requests) == 2


def test_wait_timeout(client: Any, server: StubServer) -> None:
    for _ in range(50):
        server.reply(202, PROCESSING)

    with pytest.raises(urlpipe.WaitTimeoutError) as info:
        client.wait("tok_slow", timeout=0.05, interval=0.01)

    assert info.value.token == "tok_slow"
    assert "wait('tok_slow')" in info.value.message


def test_wait_raises_for_an_unknown_token(client: Any, server: StubServer) -> None:
    server.reply(404, {"error": "not_found"})
    with pytest.raises(urlpipe.NotFoundError):
        client.wait("nope", timeout=1)
