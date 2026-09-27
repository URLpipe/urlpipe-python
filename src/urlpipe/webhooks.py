"""Verifying signed webhook deliveries."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Mapping, Optional, Union

from .errors import WebhookVerificationError

TIMESTAMP_HEADER = "X-URLpipe-Timestamp"
SIGNATURE_HEADER = "X-URLpipe-Signature"
DEFAULT_TOLERANCE = 300


def _header(headers: Mapping[str, Any], name: str) -> Optional[str]:
    wanted = name.lower()
    for key, value in headers.items():
        if isinstance(key, bytes):
            key = key.decode("latin-1")
        if str(key).lower() != wanted:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if isinstance(value, bytes):
            value = value.decode("latin-1")
        return None if value is None else str(value)
    return None


def compute_signature(secret: str, timestamp: Union[int, str], raw_body: Union[bytes, str]) -> str:
    """The hex HMAC-SHA256 of ``"<timestamp>.<raw_body>"`` keyed with ``secret``."""
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    signed = str(timestamp).encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_webhook(
    raw_body: Union[bytes, str],
    headers: Mapping[str, Any],
    secret: str,
    tolerance: int = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Check a webhook delivery came from URLpipe and return its payload.

    Pass the raw request body exactly as received — ``request.get_data()`` in
    Flask, ``await request.body()`` in Starlette/FastAPI, ``request.body`` in
    Django. Parsing the JSON and serialising it again changes the bytes, and the
    signature with them.

    ``headers`` is any mapping of the request headers; names are matched
    case-insensitively. ``secret`` is the project's signing secret (``whsec_…``).
    Deliveries signed more than ``tolerance`` seconds ago (or ahead) are refused.

    Returns the parsed payload: ``token``, ``operation``, ``labels``,
    ``success``, ``result``, ``result_url``, ``error`` and ``meta``.

    Raises:
        WebhookVerificationError: with the reason the delivery was refused.
    """
    if not secret:
        raise WebhookVerificationError("No webhook signing secret was given.")

    timestamp = _header(headers, TIMESTAMP_HEADER)
    signature_header = _header(headers, SIGNATURE_HEADER)
    if not timestamp:
        raise WebhookVerificationError(f"The {TIMESTAMP_HEADER} header is missing.")
    if not signature_header:
        raise WebhookVerificationError(f"The {SIGNATURE_HEADER} header is missing.")

    timestamp = timestamp.strip()
    if not timestamp.isdigit():
        raise WebhookVerificationError(f"The {TIMESTAMP_HEADER} header is not Unix seconds.")
    if abs(time.time() - int(timestamp)) > tolerance:
        raise WebhookVerificationError(
            f"The delivery was signed outside the {tolerance}s tolerance."
        )

    expected = compute_signature(secret, timestamp, raw_body)
    candidates = []
    for part in signature_header.split(","):
        scheme, _, value = part.strip().partition("=")
        if scheme.strip() == "v1" and value:
            candidates.append(value.strip())
    if not candidates:
        raise WebhookVerificationError("The signature header carries no v1 signature.")

    # Check every candidate, so timing doesn't reveal which one matched.
    matched = False
    for candidate in candidates:
        if hmac.compare_digest(candidate.encode("ascii", "replace"), expected.encode("ascii")):
            matched = True
    if not matched:
        raise WebhookVerificationError("No signature matches the body and secret.")

    try:
        payload = json.loads(raw_body)
    except ValueError as exc:
        raise WebhookVerificationError("The body is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise WebhookVerificationError("The body is not a JSON object.")
    return payload


__all__ = ["compute_signature", "verify_webhook"]
