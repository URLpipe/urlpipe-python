"""Everything the sync and async clients share, written without I/O.

A call is a generator ("flow") that yields :class:`Send` and :class:`Sleep`
actions and gets back the outcome of each. ``Client`` drives flows with blocking
calls and ``AsyncClient`` with awaits, so request building, retries, polling,
response parsing and error mapping exist exactly once.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Generator, Mapping, Optional, Type, Union
from urllib.parse import quote

import httpx

from . import errors
from ._models import Pdf, Quota, Response, ResponseMeta, Screenshot
from ._version import __version__

DEFAULT_BASE_URL = "https://urlpipe.dev"
DEFAULT_TIMEOUT = 90.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_WAIT_TIMEOUT = 300.0
USER_AGENT = f"urlpipe-python/{__version__}"

# Seconds between polls of GET /result/:token after a sync call answers 504.
POLL_INTERVAL = 2.0
# First backoff delay; doubles on each retry (1 s, 2 s, 4 s …).
BACKOFF_BASE = 1.0
# The longest any backoff delay grows to.
MAX_BACKOFF = 60.0
# The longest a Retry-After is honoured for.
MAX_RETRY_AFTER = 60.0
# The wait after a rate_limited answer that carries no Retry-After.
RATE_LIMIT_FALLBACK = 1.0

TEXT_OPERATIONS = frozenset({"markdown", "html", "summarize"})
JSON_OPERATIONS = frozenset({"meta", "keywords", "extract", "console", "technologies", "lighthouse", "scrape"})
RETRYABLE_STATUSES = frozenset({500, 502, 503})
INVALID_REQUEST_CODES = frozenset(
    {
        "invalid_url",
        "invalid_max_age",
        "invalid_options",
        "invalid_labels",
        "invalid_idempotency_key",
        "idempotency_key_reused",
    }
)
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# --------------------------------------------------------------------------- #
# Actions a flow yields
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    headers: Dict[str, str]
    json: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Send:
    """Perform ``request``; the flow receives an ``httpx.Response`` or the
    ``httpx.TransportError`` it failed with."""

    request: HttpRequest


@dataclass(frozen=True)
class Sleep:
    seconds: float


Action = Union[Send, Sleep]
Outcome = Union[httpx.Response, httpx.TransportError, None]
Flow = Generator[Action, Outcome, "Response[Any]"]
SendFlow = Generator[Action, Outcome, httpx.Response]


@dataclass(frozen=True)
class Config:
    api_key: str
    max_retries: int
    wait_timeout: float
    user_agent: str = USER_AGENT


# --------------------------------------------------------------------------- #
# Building requests
# --------------------------------------------------------------------------- #


def user_agent(product: Optional[str]) -> str:
    """The User-Agent: the calling program's product token, when given, in
    front of the client's own, as in ``my-app/1.2 urlpipe-python/0.2.0``."""
    product = (product or "").strip()
    return f"{product} {USER_AGENT}" if product else USER_AGENT


def base_headers(config: Config) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "User-Agent": config.user_agent,
        "Accept": "*/*",
    }


@dataclass(frozen=True)
class AnalysisCall:
    operation: str
    sync: bool
    request: HttpRequest


def build_analysis(
    config: Config,
    operation: str,
    url: str,
    *,
    params: Mapping[str, Any],
    idempotency_key: Optional[str],
    extra: Optional[Mapping[str, Any]],
) -> AnalysisCall:
    """The POST for one analysis. ``params`` holds every body option; ``None``
    values are left out so only what the caller gave is sent."""
    body: Dict[str, Any] = {"url": url}
    body.update({k: v for k, v in params.items() if v is not None})
    if extra:
        body.update(extra)

    headers = base_headers(config)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    elif config.max_retries > 0:
        # One key per call, reused by that call's retries: a retry can never
        # run or bill the work twice.
        headers["Idempotency-Key"] = str(uuid.uuid4())

    sync = body.get("sync") in (True, "true")
    return AnalysisCall(operation, sync, HttpRequest("POST", f"/{operation}", headers, body))


def build_result_request(config: Config, token: str) -> HttpRequest:
    if not token:
        raise ValueError("token must be a non-empty string")
    return HttpRequest("GET", f"/result/{quote(token, safe='')}", base_headers(config))


# --------------------------------------------------------------------------- #
# Parsing responses
# --------------------------------------------------------------------------- #


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _int_or_given(value: Optional[str]) -> Union[int, str, None]:
    """An integer, or the value as sent when it is not one (``"unlimited"``)."""
    if value is None:
        return None
    parsed = _int_or_none(value)
    return parsed if parsed is not None else value.strip()


def parse_meta(headers: httpx.Headers) -> ResponseMeta:
    replayed = headers.get("idempotent-replayed")
    return ResponseMeta(
        cache=headers.get("x-cache"),
        cache_age=_int_or_none(headers.get("x-cache-age")),
        processing_time_ms=_int_or_none(headers.get("x-processing-time-ms")),
        quota=Quota(
            cost=_int_or_none(headers.get("x-quota-cost")),
            limit=_int_or_given(headers.get("x-quota-limit")),
            remaining=_int_or_given(headers.get("x-quota-remaining")),
            overage=_int_or_none(headers.get("x-quota-overage")),
            resets_at=headers.get("x-quota-reset"),
        ),
        concurrency_limit=_int_or_given(headers.get("x-concurrency-limit")),
        result_url=headers.get("x-result-url"),
        final_url=headers.get("x-final-url"),
        idempotent_replayed=replayed is not None and replayed.strip().lower() == "true",
    )


def _parse_body(resp: httpx.Response) -> Any:
    """JSON when the body is JSON, the raw text otherwise. Never raises."""
    text = resp.text
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _labels(resp: httpx.Response, body: Any) -> Dict[str, str]:
    raw = resp.headers.get("x-labels")
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    if isinstance(body, dict) and isinstance(body.get("labels"), dict):
        return {str(k): str(v) for k, v in body["labels"].items()}
    return {}


def _token(resp: httpx.Response, body: Any) -> Optional[str]:
    token: Optional[str] = resp.headers.get("x-result-token")
    if token:
        return token
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return str(body["token"])
    return None


_MIME_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def detect_mime(data: bytes) -> str:
    for magic, mime in _MIME_SIGNATURES:
        if data.startswith(magic):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _decode_base64(text: str, what: str) -> bytes:
    try:
        return base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise errors.UrlpipeError(f"The {what} body is not valid Base64: {exc}") from exc


def decode_screenshot(text: str, result_url: Optional[str]) -> Screenshot:
    data = _decode_base64(text, "screenshot")
    return Screenshot(data=data, mime_type=detect_mime(data), result_url=result_url)


def decode_pdf(text: str, result_url: Optional[str]) -> Pdf:
    return Pdf(data=_decode_base64(text, "PDF"), result_url=result_url)


def decode_data(operation: Optional[str], resp: httpx.Response, meta: ResponseMeta) -> Any:
    """The typed result of a completed response, decided by operation."""
    if operation in TEXT_OPERATIONS:
        return resp.text
    if operation == "screenshot":
        return decode_screenshot(resp.text, meta.result_url)
    if operation == "pdf":
        return decode_pdf(resp.text, meta.result_url)
    content_type = resp.headers.get("content-type", "")
    # Without a hint, go by content type.
    if operation in JSON_OPERATIONS or (operation is None and "json" in content_type):
        try:
            return json.loads(resp.text)
        except ValueError as exc:
            raise errors.UrlpipeError(
                f"URLpipe sent a result that is not valid JSON: {exc}",
                status=resp.status_code,
                body=resp.text,
            ) from exc
    return resp.text


def completed_response(operation: Optional[str], resp: httpx.Response) -> Response[Any]:
    meta = parse_meta(resp.headers)
    return Response(
        status="completed",
        data=decode_data(operation, resp, meta),
        token=_token(resp, None),
        labels=_labels(resp, None),
        meta=meta,
        http_status=resp.status_code,
    )


def pending_response(resp: httpx.Response, status: str) -> Response[Any]:
    body = _parse_body(resp)
    return Response(
        status=status,  # type: ignore[arg-type]
        data=None,
        token=_token(resp, body),
        labels=_labels(resp, body),
        meta=parse_meta(resp.headers),
        http_status=resp.status_code,
    )


def is_processing_timeout(resp: httpx.Response) -> bool:
    if resp.status_code != 504:
        return False
    body = _parse_body(resp)
    return isinstance(body, dict) and body.get("error") == "processing_timeout"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def _retry_after(resp: httpx.Response, body: Any) -> Optional[float]:
    header = resp.headers.get("retry-after")
    if header is not None:
        try:
            return max(0.0, float(header.strip()))
        except ValueError:
            pass
    if isinstance(body, dict) and isinstance(body.get("retry_after"), (int, float)):
        return float(body["retry_after"])
    return None


def _scrape_failure_message(body: Mapping[str, Any]) -> str:
    ops = body.get("operations")
    parts = []
    if isinstance(ops, dict):
        for name, entry in ops.items():
            if isinstance(entry, dict) and entry.get("error"):
                parts.append(f"{name}: {entry['error']}")
    detail = "; ".join(parts)
    return f"Every operation failed: {detail}" if detail else "Every operation failed"


def error_from_response(resp: httpx.Response) -> errors.UrlpipeError:
    status = resp.status_code
    body = _parse_body(resp)
    data: Dict[str, Any] = body if isinstance(body, dict) else {}
    error_str = data.get("error") if isinstance(data.get("error"), str) else None
    code = error_str if error_str and _CODE_RE.match(error_str) else None

    cls: Type[errors.UrlpipeError] = errors.UrlpipeError
    fields: Dict[str, Any] = {}
    if status == 401:
        cls = errors.AuthenticationError
    elif status == 403 and error_str == "email_unverified":
        cls = errors.EmailUnverifiedError
    elif status == 422:
        if error_str and (error_str in INVALID_REQUEST_CODES or error_str.startswith("report_to")):
            cls = errors.InvalidRequestError
        else:
            cls = errors.AnalysisFailedError
    elif status == 429 and error_str == "quota_exceeded":
        cls = errors.QuotaExceededError
        fields = {k: data.get(k) for k in ("limit", "used", "needed", "resets_at")}
    elif status == 429 and error_str == "concurrency_limit":
        cls = errors.ConcurrencyLimitError
        fields = {"limit": data.get("limit"), "running": data.get("running")}
    elif status == 429 and error_str == "rate_limited":
        cls = errors.RateLimitedError
        fields = {"retry_after": _retry_after(resp, body)}
    elif status == 404:
        cls = errors.NotFoundError
    elif status == 410:
        cls = errors.StaleResultError
    elif status >= 500:
        cls = errors.ServerError

    if cls is errors.AnalysisFailedError and error_str is None and "operations" in data:
        message = _scrape_failure_message(data)
    elif isinstance(data.get("message"), str) and data["message"]:
        message = data["message"]
    elif error_str and code is None:
        # A sentence, such as an analysis failure; a bare code never is the message.
        message = error_str
    else:
        message = cls.default_message.format(status=status)

    token = data.get("token")
    if not isinstance(token, str):
        token = resp.headers.get("x-result-token")
    return cls(message, status=status, code=code, body=body, token=token, **fields)


def retry_delay(error: errors.UrlpipeError, attempt: int, max_retries: int) -> Optional[float]:
    """Seconds to wait before retrying after ``error``, or ``None`` not to retry.

    ``attempt`` counts the retries already made for this call.
    """
    if attempt >= max_retries:
        return None
    backoff = min(float(BACKOFF_BASE * (2**attempt)), MAX_BACKOFF)
    if isinstance(error, errors.RateLimitedError):
        after = error.retry_after if error.retry_after is not None else RATE_LIMIT_FALLBACK
        return min(after, MAX_RETRY_AFTER)
    if isinstance(error, (errors.ConcurrencyLimitError, errors.APIConnectionError)):
        return backoff
    if isinstance(error, errors.ServerError) and error.status in RETRYABLE_STATUSES:
        return backoff
    return None


# --------------------------------------------------------------------------- #
# Flows
# --------------------------------------------------------------------------- #


def send_with_retries(request: HttpRequest, max_retries: int) -> SendFlow:
    """Send ``request`` until it gets a non-error answer (or a 504
    ``processing_timeout``, which the caller handles), retrying what is safe."""
    attempt = 0
    while True:
        outcome = yield Send(request)
        if isinstance(outcome, httpx.Response):
            if outcome.status_code < 400 or is_processing_timeout(outcome):
                return outcome
            error = error_from_response(outcome)
        else:
            error = errors.APIConnectionError(
                f"Could not reach URLpipe: {outcome}" if str(outcome) else
                f"Could not reach URLpipe ({type(outcome).__name__})"
            )
            error.__cause__ = outcome
        delay = retry_delay(error, attempt, max_retries)
        if delay is None:
            raise error
        yield Sleep(delay)
        attempt += 1


def result_flow(config: Config, token: str, operation: Optional[str]) -> Flow:
    resp = yield from send_with_retries(build_result_request(config, token), config.max_retries)
    if resp.status_code == 200:
        return completed_response(operation, resp)
    if resp.status_code == 202 or is_processing_timeout(resp):
        response = pending_response(resp, "processing")
        if response.token is None:
            response = _with_token(response, token)
        return response
    raise error_from_response(resp)


def _with_token(response: Response[Any], token: str) -> Response[Any]:
    return Response(
        status=response.status,
        data=response.data,
        token=token,
        labels=response.labels,
        meta=response.meta,
        http_status=response.http_status,
    )


def wait_flow(
    config: Config,
    token: str,
    operation: Optional[str],
    timeout: Optional[float],
    interval: float,
) -> Flow:
    limit = config.wait_timeout if timeout is None else timeout
    deadline = time.monotonic() + limit
    while True:
        response = yield from result_flow(config, token, operation)
        if response.status == "completed":
            return response
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise errors.WaitTimeoutError(
                f"The analysis was still running after {limit:g}s. It keeps running: "
                f"collect it with wait({token!r}).",
                token=token,
                timeout=limit,
            )
        yield Sleep(min(interval, remaining))


def analysis_flow(config: Config, call: AnalysisCall) -> Flow:
    resp = yield from send_with_retries(call.request, config.max_retries)
    if is_processing_timeout(resp):
        token = _token(resp, _parse_body(resp))
        if token is None:
            raise error_from_response(resp)
        # Still running: poll for it, so the caller sees one call.
        return (yield from wait_flow(config, token, call.operation, None, POLL_INTERVAL))
    if call.sync:
        return completed_response(call.operation, resp)
    return pending_response(resp, "accepted")
