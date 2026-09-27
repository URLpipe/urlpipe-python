from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

import urlpipe
from conftest import StubServer


def raised(client: Any, server: StubServer, status: int, body: Any,
           headers: Optional[Dict[str, str]] = None) -> urlpipe.UrlpipeError:
    server.reply(status, body, headers=headers)
    with pytest.raises(urlpipe.UrlpipeError) as info:
        client.markdown("https://example.com")
    return info.value


def test_401_is_an_authentication_error(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 401, {"error": "unauthorized"})
    assert type(error) is urlpipe.AuthenticationError
    assert error.status == 401
    assert error.code == "unauthorized"
    assert error.body == {"error": "unauthorized"}


def test_401_with_an_empty_body(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 401, "")
    assert type(error) is urlpipe.AuthenticationError
    assert error.body is None
    assert error.message == "The API key is missing or does not match an active project key."


def test_403_email_unverified(make_client: Any, server: StubServer) -> None:
    body = {
        "error": "email_unverified",
        "message": "Confirm the email address on this account before using the API.",
    }
    error = raised(make_client(), server, 403, body)
    assert type(error) is urlpipe.EmailUnverifiedError
    assert error.code == "email_unverified"
    assert error.message == "Confirm the email address on this account before using the API."


def test_403_email_unverified_without_a_message(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 403, {"error": "email_unverified"})
    assert type(error) is urlpipe.EmailUnverifiedError
    assert "Confirm the email address" in error.message


@pytest.mark.parametrize(
    "code",
    [
        "invalid_url",
        "invalid_max_age",
        "invalid_options",
        "invalid_labels",
        "invalid_idempotency_key",
        "idempotency_key_reused",
    ],
)
def test_422_validation_codes(make_client: Any, server: StubServer, code: str) -> None:
    body = {"error": code, "message": f"Something about {code}."}
    error = raised(make_client(), server, 422, body)
    assert type(error) is urlpipe.InvalidRequestError
    assert error.status == 422
    assert error.code == code
    assert error.message == f"Something about {code}."
    assert error.body == body


def test_422_report_to_refusal(make_client: Any, server: StubServer) -> None:
    sentence = "report_to must be a public http or https address on the default port."
    error = raised(make_client(), server, 422, {"error": sentence})
    assert type(error) is urlpipe.InvalidRequestError
    assert error.code is None
    assert error.message == sentence


def test_422_analysis_failure(make_client: Any, server: StubServer) -> None:
    error = raised(
        make_client(), server, 422, {"error": "The request timed out."},
        headers={"X-Result-Token": "tok_failed", "X-Quota-Cost": "0"},
    )
    assert type(error) is urlpipe.AnalysisFailedError
    assert error.message == "The request timed out."
    assert error.code is None
    assert error.token == "tok_failed"


def test_422_scrape_where_every_operation_failed(make_client: Any, server: StubServer) -> None:
    body = {
        "url": "https://example.com",
        "operations": {
            "markdown": {"success": False, "error": "The page could not be loaded.",
                         "cached": False},
            "meta": {"success": False, "error": "The page could not be loaded.",
                     "cached": False},
        },
    }
    server.reply(422, body)
    with pytest.raises(urlpipe.AnalysisFailedError) as info:
        make_client().scrape("https://example.com", ["markdown", "meta"])
    assert info.value.body == body
    assert info.value.message == (
        "Every operation failed: markdown: The page could not be loaded.; "
        "meta: The page could not be loaded."
    )


def test_429_quota_exceeded(make_client: Any, server: StubServer) -> None:
    body = {
        "error": "quota_exceeded",
        "message": "You have used this month's credits.",
        "limit": 1000,
        "used": 998,
        "needed": 5,
        "resets_at": "2026-10-01T00:00:00Z",
    }
    error = raised(make_client(), server, 429, body)
    assert type(error) is urlpipe.QuotaExceededError
    assert (error.limit, error.used, error.needed, error.resets_at) == (
        1000, 998, 5, "2026-10-01T00:00:00Z"
    )
    assert error.code == "quota_exceeded"


def test_429_concurrency_limit(make_client: Any, server: StubServer) -> None:
    body = {"error": "concurrency_limit", "message": "3 already running.", "limit": 3,
            "running": 3}
    error = raised(make_client(max_retries=0), server, 429, body)
    assert type(error) is urlpipe.ConcurrencyLimitError
    assert (error.limit, error.running) == (3, 3)


def test_429_rate_limited(make_client: Any, server: StubServer) -> None:
    body = {"error": "rate_limited", "message": "Slow down.", "retry_after": 12}
    error = raised(make_client(max_retries=0), server, 429, body, headers={"Retry-After": "7"})
    assert type(error) is urlpipe.RateLimitedError
    assert error.retry_after == 7


def test_429_rate_limited_falls_back_to_the_body(make_client: Any, server: StubServer) -> None:
    body = {"error": "rate_limited", "message": "Slow down.", "retry_after": 12}
    error = raised(make_client(max_retries=0), server, 429, body)
    assert isinstance(error, urlpipe.RateLimitedError)
    assert error.retry_after == 12


def test_404_not_found(make_client: Any, server: StubServer) -> None:
    server.reply(404, {"error": "not_found"})
    with pytest.raises(urlpipe.NotFoundError) as info:
        make_client().result("nope")
    assert info.value.code == "not_found"
    assert info.value.status == 404


def test_410_stale(make_client: Any, server: StubServer) -> None:
    body = {"error": "stale", "message": "This result is older than the 30-day retention window."}
    server.reply(410, body)
    with pytest.raises(urlpipe.StaleResultError) as info:
        make_client().result("old")
    assert info.value.code == "stale"
    assert info.value.message == body["message"]


def test_result_422_is_an_analysis_failure(make_client: Any, server: StubServer) -> None:
    server.reply(422, {"error": "The page could not be loaded."})
    with pytest.raises(urlpipe.AnalysisFailedError):
        make_client().result("tok")


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_5xx_is_a_server_error(make_client: Any, server: StubServer, status: int) -> None:
    error = raised(make_client(max_retries=0), server, status, "<html>Bad Gateway</html>",
                   headers={})
    assert type(error) is urlpipe.ServerError
    assert error.status == status
    assert error.body == "<html>Bad Gateway</html>"
    assert error.message == f"URLpipe answered HTTP {status}: a server error."


def test_a_body_that_is_not_json_does_not_mask_the_error(
    make_client: Any, server: StubServer
) -> None:
    server.reply(422, '{"error": broken', content_type="application/json")
    with pytest.raises(urlpipe.AnalysisFailedError) as info:
        make_client().markdown("https://example.com")
    assert info.value.status == 422
    assert info.value.body == '{"error": broken'


def test_connection_error(make_client: Any, unused_port: int) -> None:
    client = make_client(base_url=f"http://127.0.0.1:{unused_port}", max_retries=1)
    with pytest.raises(urlpipe.APIConnectionError) as info:
        client.markdown("https://example.com")
    assert info.value.status is None
    assert "Could not reach URLpipe" in info.value.message


def test_every_error_is_a_urlpipe_error() -> None:
    for name in urlpipe.errors.__all__:
        assert issubclass(getattr(urlpipe, name), urlpipe.UrlpipeError)
        assert getattr(urlpipe.errors, name) is getattr(urlpipe, name)


def test_str_includes_the_status() -> None:
    error = urlpipe.AnalysisFailedError("The request timed out.", status=422)
    assert str(error) == "The request timed out. (HTTP 422)"


# -- Resolved decisions ------------------------------------------------------ #


@pytest.mark.parametrize(
    "status, body, cls, message",
    [
        (401, "", urlpipe.AuthenticationError,
         "The API key is missing or does not match an active project key."),
        (403, {"error": "email_unverified"}, urlpipe.EmailUnverifiedError,
         "Confirm the email address on this account before using the API."),
        (422, {}, urlpipe.AnalysisFailedError, "The page could not be analysed."),
        (429, {"error": "quota_exceeded"}, urlpipe.QuotaExceededError,
         "This month's credits are spent."),
        (429, {"error": "concurrency_limit"}, urlpipe.ConcurrencyLimitError,
         "Too many of your requests are already running."),
        (429, {"error": "rate_limited"}, urlpipe.RateLimitedError,
         "Too many requests. Slow down and retry shortly."),
        (401, {"error": "unauthorized"}, urlpipe.AuthenticationError,
         "The API key is missing or does not match an active project key."),
        (422, {"error": "invalid_url"}, urlpipe.InvalidRequestError,
         "A parameter was refused, so nothing ran."),
        (404, {"error": "not_found"}, urlpipe.NotFoundError,
         "No result for this token under this project."),
        (503, {"error": "unavailable"}, urlpipe.ServerError,
         "URLpipe answered HTTP 503: a server error."),
        (404, "", urlpipe.NotFoundError, "No result for this token under this project."),
        (410, "", urlpipe.StaleResultError,
         "The result is older than the 30-day retention window. Run a new analysis."),
        (418, "", urlpipe.UrlpipeError, "URLpipe answered HTTP 418."),
    ],
)
def test_d2_a_bare_code_falls_back_to_a_default_per_kind(
    make_client: Any, server: StubServer, status: int, body: Any, cls: type, message: str
) -> None:
    error = raised(make_client(max_retries=0), server, status, body)
    assert type(error) is cls
    assert error.message == message


def test_d2_message_prefers_the_body_message(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 422,
                   {"error": "invalid_labels", "message": "labels.client must be a string."})
    assert (error.code, error.message) == ("invalid_labels", "labels.client must be a string.")


def test_d2_code_is_only_an_identifier(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 422, {"error": "Invalid_URL"})
    assert error.code is None
    assert error.message == "Invalid_URL"


def test_d3_an_unknown_429_is_the_base_error(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 429, {"error": "something_else"})
    assert type(error) is urlpipe.UrlpipeError
    assert error.code == "something_else"
    assert error.message == "URLpipe answered HTTP 429."
    assert len(server.requests) == 1


def test_d3_a_429_without_error_is_the_base_error(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 429, "Too Many Requests")
    assert type(error) is urlpipe.UrlpipeError
    assert len(server.requests) == 1


def test_d5_error_token_prefers_the_body(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 422,
                   {"error": "The request timed out.", "token": "tok_body"},
                   headers={"X-Result-Token": "tok_header"})
    assert error.token == "tok_body"


def test_d5_error_token_falls_back_to_the_header(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 422, {"error": "The request timed out."},
                   headers={"X-Result-Token": "tok_header"})
    assert error.token == "tok_header"


def test_d9_all_failed_scrape_keeps_the_body_order(make_client: Any, server: StubServer) -> None:
    body = {
        "url": "https://example.com",
        "operations": {
            "meta": {"success": False, "error": "B.", "cached": False},
            "html": {"success": False, "error": "A.", "cached": False},
        },
    }
    server.reply(422, body)
    with pytest.raises(urlpipe.AnalysisFailedError) as info:
        make_client().scrape("https://example.com", ["html", "meta"])
    assert info.value.message == "Every operation failed: meta: B.; html: A."
    assert info.value.body == body


def test_d10_other_403_is_the_base_error(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 403, {"error": "forbidden"})
    assert type(error) is urlpipe.UrlpipeError
    assert error.status == 403


@pytest.mark.parametrize("status, cls", [(404, urlpipe.NotFoundError),
                                          (410, urlpipe.StaleResultError)])
def test_d10_404_and_410_whatever_the_body(
    make_client: Any, server: StubServer, status: int, cls: type
) -> None:
    server.reply(status, "<html>gone</html>")
    with pytest.raises(cls):
        make_client().result("tok")


def test_d2_an_error_sentence_is_the_message(make_client: Any, server: StubServer) -> None:
    error = raised(make_client(), server, 422, {"error": "The page could not be loaded."})
    assert (error.code, error.message) == (None, "The page could not be loaded.")
