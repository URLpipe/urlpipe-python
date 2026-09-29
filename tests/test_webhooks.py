from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

import urlpipe

SECRET = "whsec_test_secret"
PAYLOAD = {
    "token": "tok_1",
    "operation": "markdown",
    "labels": {"client": "acme"},
    "success": True,
    "result": "# Example Domain",
    "result_url": None,
    "final_url": "https://example.com/",
    "error": None,
    "meta": {"cache": "miss", "cache_age": None, "processing_time_ms": 4182, "quota": {}},
}
BODY = json.dumps(PAYLOAD, separators=(",", ":")).encode()


def sign(body: bytes, timestamp: int, secret: str = SECRET) -> str:
    signed = str(timestamp).encode() + b"." + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def headers(signature: str, timestamp: int) -> dict:
    return {"X-URLpipe-Timestamp": str(timestamp), "X-URLpipe-Signature": signature}


def test_a_valid_delivery_returns_the_payload() -> None:
    now = int(time.time())
    assert urlpipe.verify_webhook(BODY, headers(f"v1={sign(BODY, now)}", now), SECRET) == PAYLOAD


def test_the_body_may_be_a_string_and_headers_any_case() -> None:
    now = int(time.time())
    lowered = {"x-urlpipe-timestamp": str(now), "X-URLPIPE-SIGNATURE": f"v1={sign(BODY, now)}"}
    assert urlpipe.verify_webhook(BODY.decode(), lowered, SECRET)["token"] == "tok_1"


def test_a_tampered_body_is_refused() -> None:
    now = int(time.time())
    tampered = BODY.replace(b"acme", b"evil")
    with pytest.raises(urlpipe.WebhookVerificationError, match="No signature matches"):
        urlpipe.verify_webhook(tampered, headers(f"v1={sign(BODY, now)}", now), SECRET)


def test_re_serialised_json_is_refused() -> None:
    now = int(time.time())
    reserialised = json.dumps(PAYLOAD, indent=2).encode()
    with pytest.raises(urlpipe.WebhookVerificationError):
        urlpipe.verify_webhook(reserialised, headers(f"v1={sign(BODY, now)}", now), SECRET)


def test_the_wrong_secret_is_refused() -> None:
    now = int(time.time())
    with pytest.raises(urlpipe.WebhookVerificationError):
        urlpipe.verify_webhook(BODY, headers(f"v1={sign(BODY, now)}", now), "whsec_other")


@pytest.mark.parametrize("offset", [-301, 301, -3600])
def test_a_timestamp_outside_the_tolerance_is_refused(offset: int) -> None:
    then = int(time.time()) + offset
    with pytest.raises(urlpipe.WebhookVerificationError, match="tolerance"):
        urlpipe.verify_webhook(BODY, headers(f"v1={sign(BODY, then)}", then), SECRET)


def test_a_custom_tolerance() -> None:
    then = int(time.time()) - 1000
    signed = headers(f"v1={sign(BODY, then)}", then)
    assert urlpipe.verify_webhook(BODY, signed, SECRET, tolerance=2000)["success"] is True


def test_rotation_accepts_when_only_the_second_signature_matches() -> None:
    now = int(time.time())
    signature = f"v1={sign(BODY, now, 'whsec_new')},v1={sign(BODY, now)}"
    assert urlpipe.verify_webhook(BODY, headers(signature, now), SECRET) == PAYLOAD


def test_unknown_schemes_are_ignored() -> None:
    now = int(time.time())
    signature = f"v2={sign(BODY, now)}, v1={sign(BODY, now)}"
    assert urlpipe.verify_webhook(BODY, headers(signature, now), SECRET) == PAYLOAD


def test_only_unknown_schemes_is_refused() -> None:
    now = int(time.time())
    with pytest.raises(urlpipe.WebhookVerificationError, match="no v1"):
        urlpipe.verify_webhook(BODY, headers(f"v2={sign(BODY, now)}", now), SECRET)


@pytest.mark.parametrize(
    "hdrs, reason",
    [
        ({"X-URLpipe-Signature": "v1=abc"}, "Timestamp header is missing"),
        ({"X-URLpipe-Timestamp": "1756568400"}, "Signature header is missing"),
        ({"X-URLpipe-Timestamp": "soon", "X-URLpipe-Signature": "v1=abc"}, "Unix seconds"),
    ],
)
def test_missing_or_malformed_headers(hdrs: dict, reason: str) -> None:
    with pytest.raises(urlpipe.WebhookVerificationError, match=reason):
        urlpipe.verify_webhook(BODY, hdrs, SECRET)


def test_webhook_errors_are_urlpipe_errors() -> None:
    assert issubclass(urlpipe.WebhookVerificationError, urlpipe.UrlpipeError)
