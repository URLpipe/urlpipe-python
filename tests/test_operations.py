from __future__ import annotations

import base64
import re
from typing import Any

import pytest

import urlpipe
from conftest import API_KEY, META_HEADERS, StubServer

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16
PDF = b"%PDF-1.4\n" + b"\x00" * 16


def assert_standard_request(server: StubServer, path: str) -> dict:
    [req] = server.requests
    assert req.method == "POST"
    assert req.path == path
    assert req.headers["authorization"] == f"Bearer {API_KEY}"
    assert req.headers["user-agent"] == f"urlpipe-python/{urlpipe.__version__}"
    assert req.headers["content-type"] == "application/json"
    return req.json


@pytest.mark.parametrize("operation", ["markdown", "html", "summarize"])
def test_text_operations(client: Any, server: StubServer, operation: str) -> None:
    server.reply(200, "# Example Domain\n", headers=META_HEADERS)

    response = getattr(client, operation)("https://example.com")

    assert assert_standard_request(server, f"/{operation}") == {
        "url": "https://example.com",
        "sync": True,
    }
    assert response.status == "completed"
    assert response.data == "# Example Domain\n"
    assert response.token == "tok_123"
    assert response.http_status == 200


@pytest.mark.parametrize(
    "operation, payload",
    [
        (
            "meta",
            {
                "final_url": "https://example.com/",
                "canonical_url": "https://example.com/",
                "title": "Example Domain",
                "description": "Illustrative examples.",
                "site_name": None,
                "type": "website",
                "language": "en",
                "locale": "en",
                "authors": [],
                "published_at": None,
                "modified_at": None,
                "image": {
                    "url": "https://example.com/cover.jpg",
                    "width": 1200,
                    "height": 630,
                    "alt": None,
                    "type": None
                },
                "video": None,
                "favicon_url": "https://example.com/favicon.ico",
                "icons": [
                    {
                        "url": "https://example.com/favicon.ico",
                        "rel": "icon",
                        "sizes": None,
                        "type": None
                    }
                ],
                "logo_url": None,
                "feeds": [],
                "keywords": [],
                "theme_color": None,
                "generator": None,
                "manifest_url": None,
                "robots": {
                    "index": True,
                    "follow": True
                },
                "open_graph": {
                    "title": "Example Domain",
                    "description": None,
                    "image": "https://example.com/cover.jpg",
                    "url": None,
                    "type": "website",
                    "site_name": None,
                    "locale": None
                },
                "twitter": {
                    "card": None,
                    "site": None,
                    "creator": None,
                    "title": None,
                    "description": None,
                    "image": None
                },
                "alternates": [],
                "oembed_url": None,
                "structured_data_types": []
            },
        ),
        ("keywords", ["example domain", "documentation"]),
        ("console", [{"type": "error", "text": "boom"}, {"type": "exception", "text": "x"}]),
        (
            "technologies",
            {
                "final_url": "https://example.com/",
                "technologies": [
                    {
                        "name": "WordPress",
                        "slug": "wordpress",
                        "version": "6.4.2",
                        "confidence": 100,
                        "categories": [{"slug": "cms", "name": "CMS"}],
                        "website": "https://wordpress.org",
                        "description": None,
                        "cpe": None,
                        "detected_by": ["meta"],
                        "implied_by": []
                    }
                ]
            },
        ),
        ("lighthouse", {"url": "https://example.com", "categories": {"seo": {"score": 0.9}}}),
    ],
)
def test_json_operations(client: Any, server: StubServer, operation: str, payload: Any) -> None:
    server.reply(200, payload, headers=META_HEADERS)

    response = getattr(client, operation)("https://example.com")

    assert assert_standard_request(server, f"/{operation}") == {
        "url": "https://example.com",
        "sync": True,
    }
    assert response.status == "completed"
    assert response.data == payload


def test_scrape(client: Any, server: StubServer) -> None:
    payload = {
        "url": "https://example.com",
        "final_url": "https://example.com/",
        "operations": {
            "markdown": {"success": True, "result": "# Hi", "cached": False},
            "meta": {"success": False, "error": "The page is too big to be processed.",
                     "cached": False},
        },
    }
    server.reply(200, payload, headers={**META_HEADERS, "X-Cache": "partial", "X-Cache-Age": "60"})

    response = client.scrape(
        "https://example.com",
        ["markdown", "meta"],
        device="desktop",
        include_audits=True,
        screenshot_options={"format": "webp"},
        pdf_options={"landscape": True},
        fields=[{"name": "price", "type": "number"}],
        instructions="Prices in euros.",
    )

    assert assert_standard_request(server, "/scrape") == {
        "url": "https://example.com",
        "operations": ["markdown", "meta"],
        "device": "desktop",
        "include_audits": True,
        "screenshot_options": {"format": "webp"},
        "pdf_options": {"landscape": True},
        "fields": [{"name": "price", "type": "number"}],
        "instructions": "Prices in euros.",
        "sync": True,
    }
    assert response.data == payload
    assert response.meta.cache == "partial"
    assert response.meta.cache_age == 60


def test_scrape_accepts_comma_separated_operations(client: Any, server: StubServer) -> None:
    server.reply(200, {"url": "https://example.com", "operations": {}})
    client.scrape("https://example.com", "markdown,meta")
    assert server.requests[0].json["operations"] == "markdown,meta"


def test_lighthouse_options(client: Any, server: StubServer) -> None:
    server.reply(200, {"url": "https://example.com"})
    client.lighthouse("https://example.com", device="desktop", include_audits=True)
    assert server.requests[0].json == {
        "url": "https://example.com",
        "device": "desktop",
        "include_audits": True,
        "sync": True,
    }


def test_common_options_are_sent_as_given(client: Any, server: StubServer) -> None:
    server.reply(200, "ok")
    page_options = {"block_ads": True, "remove_selectors": [".promo"], "delay": 500}

    client.markdown(
        "https://example.com",
        max_age="3 days",
        labels={"client": "acme"},
        residential=True,
        report_to="https://hooks.example.com/urlpipe",
        page_options=page_options,
    )

    assert server.requests[0].json == {
        "url": "https://example.com",
        "max_age": "3 days",
        "labels": {"client": "acme"},
        "residential": True,
        "report_to": "https://hooks.example.com/urlpipe",
        "page_options": page_options,
        "sync": True,
    }


def test_max_age_as_integer_seconds(client: Any, server: StubServer) -> None:
    server.reply(200, "ok")
    client.html("https://example.com", max_age=0)
    assert server.requests[0].json["max_age"] == 0


def test_extra_params_are_merged_into_the_body(client: Any, server: StubServer) -> None:
    server.reply(200, "ok")
    client.markdown("https://example.com", extra={"future_option": {"a": 1}})
    assert server.requests[0].json == {
        "url": "https://example.com",
        "sync": True,
        "future_option": {"a": 1},
    }


def test_idempotency_key_is_a_header_not_a_body_param(client: Any, server: StubServer) -> None:
    server.reply(200, "ok")
    client.markdown("https://example.com", idempotency_key="my-key-1")
    req = server.requests[0]
    assert req.headers["idempotency-key"] == "my-key-1"
    assert "idempotency_key" not in req.json


def test_an_idempotency_key_is_generated_when_retries_are_on(
    client: Any, server: StubServer
) -> None:
    server.reply(200, "ok").reply(200, "ok")
    client.markdown("https://example.com")
    client.markdown("https://example.com")
    first, second = (r.headers["idempotency-key"] for r in server.requests)
    uuid4 = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    assert re.match(uuid4, first)
    assert first != second


def test_no_idempotency_key_is_invented_when_retries_are_off(
    make_client: Any, server: StubServer
) -> None:
    server.reply(200, "ok")
    make_client(max_retries=0).markdown("https://example.com")
    assert sorted(server.requests[0].headers) == [
        "accept",
        "accept-encoding",
        "authorization",
        "connection",
        "content-length",
        "content-type",
        "host",
        "user-agent",
    ]


def test_response_meta_from_headers(client: Any, server: StubServer) -> None:
    server.reply(
        200,
        "ok",
        headers={
            "X-Result-Token": "tok_meta",
            "X-Cache": "hit",
            "X-Cache-Age": "5400",
            "X-Processing-Time-Ms": "12",
            "X-Quota-Cost": "0",
            "X-Quota-Limit": "unlimited",
            "X-Quota-Remaining": "unlimited",
            "X-Quota-Overage": "7",
            "X-Quota-Reset": "2026-08-31T23:59:59Z",
            "X-Concurrency-Limit": "unlimited",
            "X-Labels": '{"client":"acme","city":"M\\u00e1laga"}',
            "X-Final-Url": "https://www.example.com/en/",
            "Idempotent-Replayed": "true",
        },
    )

    response = client.markdown("https://example.com")

    assert response.token == "tok_meta"
    assert response.labels == {"client": "acme", "city": "Málaga"}
    assert response.meta == urlpipe.ResponseMeta(
        cache="hit",
        cache_age=5400,
        processing_time_ms=12,
        quota=urlpipe.Quota(
            cost=0,
            limit="unlimited",
            remaining="unlimited",
            overage=7,
            resets_at="2026-08-31T23:59:59Z",
        ),
        concurrency_limit="unlimited",
        result_url=None,
        final_url="https://www.example.com/en/",
        idempotent_replayed=True,
    )


def test_numeric_quota_headers(client: Any, server: StubServer) -> None:
    server.reply(200, "ok", headers=META_HEADERS)
    meta = client.markdown("https://example.com").meta
    assert meta.quota == urlpipe.Quota(
        cost=1, limit=1000, remaining=943, overage=0, resets_at="2026-08-31T23:59:59Z"
    )
    assert meta.concurrency_limit == 3
    assert meta.processing_time_ms == 4182


def test_missing_headers_are_none(client: Any, server: StubServer) -> None:
    server.reply(200, "ok")
    response = client.markdown("https://example.com")
    assert response.token is None
    assert response.labels == {}
    assert response.meta == urlpipe.ResponseMeta()
    assert response.meta.quota.limit is None


@pytest.mark.parametrize(
    "image, mime",
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp"), (b"GIF89a....", "image/png")],
)
def test_screenshot_is_decoded(client: Any, server: StubServer, image: bytes, mime: str) -> None:
    encoded = base64.b64encode(image).decode()
    server.reply(
        200,
        encoded[:10] + "\n" + encoded[10:] + "\n",
        headers={**META_HEADERS, "X-Result-Url": "https://cdn.urlpipe.dev/s/abc.png"},
    )

    response = client.screenshot("https://example.com", screenshot_options={"format": "jpeg"})

    assert server.requests[0].json == {
        "url": "https://example.com",
        "screenshot_options": {"format": "jpeg"},
        "sync": True,
    }
    shot = response.data
    assert isinstance(shot, urlpipe.Screenshot)
    assert shot.data == image
    assert shot.mime_type == mime
    assert shot.result_url == "https://cdn.urlpipe.dev/s/abc.png"
    assert response.meta.result_url == "https://cdn.urlpipe.dev/s/abc.png"


def test_pdf_is_decoded(client: Any, server: StubServer) -> None:
    encoded = base64.b64encode(PDF).decode()
    server.reply(
        200,
        encoded[:10] + "\n" + encoded[10:] + "\n",
        headers={**META_HEADERS, "X-Result-Url": "https://cdn.urlpipe.dev/s/abc.pdf"},
    )

    response = client.pdf("https://example.com", pdf_options={"paper_size": "letter"})

    assert assert_standard_request(server, "/pdf") == {
        "url": "https://example.com",
        "pdf_options": {"paper_size": "letter"},
        "sync": True,
    }
    pdf = response.data
    assert isinstance(pdf, urlpipe.Pdf)
    assert pdf.data == PDF
    assert pdf.size == len(PDF)
    assert pdf.mime_type == "application/pdf"
    assert pdf.result_url == "https://cdn.urlpipe.dev/s/abc.pdf"
    assert response.meta.result_url == "https://cdn.urlpipe.dev/s/abc.pdf"


def test_pdf_save(tmp_path: Any) -> None:
    pdf = urlpipe.Pdf(data=PDF)
    path = pdf.save(tmp_path / "page.pdf")
    assert path.read_bytes() == PDF
    assert "data=" not in repr(pdf)


def test_result_with_pdf_hint_decodes(client: Any, server: StubServer) -> None:
    server.reply(200, base64.b64encode(PDF).decode(), headers={"X-Result-Url": "https://u/x"})
    pdf = client.result("tok", operation="pdf").data
    assert pdf.data == PDF
    assert pdf.result_url == "https://u/x"


def test_extract(client: Any, server: StubServer) -> None:
    fields = [
        {"name": "name", "type": "string", "description": "The product's name"},
        {"name": "price", "type": "number"},
        {"name": "sizes", "type": "array", "items": "string"},
    ]
    payload = {"name": "Trail Shoe", "price": 89.5, "sizes": None}
    server.reply(200, payload, headers=META_HEADERS)

    response = client.extract(
        "https://example.com/shoe", fields, instructions="Prices in euros."
    )

    assert assert_standard_request(server, "/extract") == {
        "url": "https://example.com/shoe",
        "fields": fields,
        "instructions": "Prices in euros.",
        "sync": True,
    }
    assert response.data == payload
    assert list(response.data) == ["name", "price", "sizes"]


def test_screenshot_save(tmp_path: Any) -> None:
    shot = urlpipe.Screenshot(data=PNG, mime_type="image/png")
    path = shot.save(tmp_path / "page.png")
    assert path.read_bytes() == PNG
    assert "data=" not in repr(shot)


@pytest.mark.parametrize("operation", ["markdown", "screenshot", "meta", "lighthouse"])
def test_async_mode_returns_an_accepted_response(
    client: Any, server: StubServer, operation: str
) -> None:
    server.reply(
        200,
        {"token": "tok_async", "status": "accepted", "labels": {"client": "acme"}},
        headers={"X-Cache": "miss", "X-Quota-Cost": "1"},
    )

    response = getattr(client, operation)(
        "https://example.com", sync=False, labels={"client": "acme"}
    )

    assert server.requests[0].json["sync"] is False
    assert response.status == "accepted"
    assert response.data is None
    assert response.token == "tok_async"
    assert response.labels == {"client": "acme"}
    assert response.meta.cache == "miss"
    assert response.meta.processing_time_ms is None


def test_result_completed_with_operation_hint(client: Any, server: StubServer) -> None:
    server.reply(200, ["a", "b"], headers={"X-Result-Token": "tok_r"})

    response = client.result("tok_r", operation="keywords")

    [req] = server.requests
    assert (req.method, req.path) == ("GET", "/result/tok_r")
    assert req.headers["authorization"] == f"Bearer {API_KEY}"
    assert req.headers["user-agent"] == f"urlpipe-python/{urlpipe.__version__}"
    assert response.status == "completed"
    assert response.data == ["a", "b"]


def test_result_without_hint_goes_by_content_type(client: Any, server: StubServer) -> None:
    encoded = base64.b64encode(PNG).decode()
    server.reply(200, {"title": "x"}).reply(200, encoded)

    assert client.result("t1").data == {"title": "x"}
    assert client.result("t2").data == encoded  # a screenshot stays Base64 without the hint


def test_result_with_screenshot_hint_decodes(client: Any, server: StubServer) -> None:
    server.reply(200, base64.b64encode(PNG).decode(), headers={"X-Result-Url": "https://u/x"})
    shot = client.result("tok", operation="screenshot").data
    assert shot.data == PNG
    assert shot.result_url == "https://u/x"


def test_result_still_processing(client: Any, server: StubServer) -> None:
    server.reply(202, {"status": "processing", "token": "tok_p", "labels": {"k": "v"}})

    response = client.result("tok_p")

    assert response.status == "processing"
    assert response.data is None
    assert response.token == "tok_p"
    assert response.labels == {"k": "v"}
    assert response.http_status == 202


def test_result_token_is_escaped_in_the_path(client: Any, server: StubServer) -> None:
    server.reply(200, "ok")
    client.result("a/b c")
    assert server.requests[0].path == "/result/a%2Fb%20c"


def test_d6_result_504_processing_timeout_is_a_processing_response(
    client: Any, server: StubServer
) -> None:
    server.reply(504, {"error": "processing_timeout", "token": "tok_p"})
    response = client.result("tok_p")
    assert response.status == "processing"
    assert response.token == "tok_p"
    assert response.data is None


def test_d13_extra_overrides_sync(client: Any, server: StubServer) -> None:
    server.reply(200, {"token": "tok_x", "status": "accepted", "labels": {}})
    response = client.markdown("https://example.com", extra={"sync": False})
    assert server.requests[0].json["sync"] is False
    assert response.status == "accepted"
    assert response.token == "tok_x"


def test_d7_concurrency_limit_numeric_and_unlimited(client: Any, server: StubServer) -> None:
    server.reply(200, "ok", headers={"X-Concurrency-Limit": "20"})
    server.reply(200, "ok", headers={"X-Concurrency-Limit": "unlimited"})
    assert client.markdown("https://example.com").meta.concurrency_limit == 20
    assert client.markdown("https://example.com").meta.concurrency_limit == "unlimited"


def test_d1_idempotent_replayed_is_false_without_the_header(
    client: Any, server: StubServer
) -> None:
    server.reply(200, "ok")
    assert client.markdown("https://example.com").meta.idempotent_replayed is False


def test_user_agent_names_the_calling_program(make_client: Any, server: StubServer) -> None:
    server.reply(200, "# Example Domain\n", headers=META_HEADERS)

    make_client(user_agent="langchain-urlpipe/0.1.1").markdown("https://example.com")

    [req] = server.requests
    assert req.headers["user-agent"] == f"langchain-urlpipe/0.1.1 urlpipe-python/{urlpipe.__version__}"


def test_a_blank_user_agent_keeps_the_default(make_client: Any, server: StubServer) -> None:
    server.reply(200, "# Example Domain\n", headers=META_HEADERS)

    make_client(user_agent="  ").markdown("https://example.com")

    [req] = server.requests
    assert req.headers["user-agent"] == f"urlpipe-python/{urlpipe.__version__}"
