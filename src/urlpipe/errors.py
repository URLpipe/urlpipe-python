"""Every error the client raises. All of them subclass :class:`UrlpipeError`."""

from __future__ import annotations

from typing import Any, Optional


class UrlpipeError(Exception):
    """Base class for every URLpipe error.

    Attributes:
        status: the HTTP status, when the error came from a response.
        code: the body's ``error`` field when it is a machine-readable code
            (``invalid_url``, ``quota_exceeded`` …), otherwise ``None``.
        message: a human-readable explanation.
        body: the response body, parsed as JSON when it is JSON, else raw text.
        token: the result token, when the response carried one.
    """

    #: The message used when the response gives none. ``{status}`` is filled in.
    default_message = "URLpipe answered HTTP {status}."

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        body: Any = None,
        token: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.body = body
        self.token = token

    def __str__(self) -> str:
        if self.status is not None:
            return f"{self.message} (HTTP {self.status})"
        return self.message

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(message={self.message!r}, status={self.status!r}, "
            f"code={self.code!r})"
        )


class ConfigurationError(UrlpipeError):
    """The client was set up without something it needs, such as an API key."""


class AuthenticationError(UrlpipeError):
    """401: the API key is missing or does not match an active project key."""
    default_message = "The API key is missing or does not match an active project key."


class EmailUnverifiedError(UrlpipeError):
    """403 ``email_unverified``: confirm the email address on the account.

    The key itself is valid; rotating it will not help.
    """

    default_message = "Confirm the email address on this account before using the API."


class InvalidRequestError(UrlpipeError):
    """422 with a validation code: a parameter was refused before anything ran."""
    default_message = "A parameter was refused, so nothing ran."


class AnalysisFailedError(UrlpipeError):
    """422: the page could not be analysed. ``message`` says why.

    For a ``/scrape`` where every operation failed, ``body`` holds the scrape
    object with each operation's error.
    """

    default_message = "The page could not be analysed."


class NotFoundError(UrlpipeError):
    """404: no result for this token under this project."""
    default_message = "No result for this token under this project."


class StaleResultError(UrlpipeError):
    """410: the result is older than the 30-day retention window."""
    default_message = "The result is older than the 30-day retention window. Run a new analysis."


class QuotaExceededError(UrlpipeError):
    """429 ``quota_exceeded``: the Free plan's monthly credits are spent."""

    default_message = "This month's credits are spent."

    def __init__(
        self,
        message: str,
        *,
        limit: Optional[int] = None,
        used: Optional[int] = None,
        needed: Optional[int] = None,
        resets_at: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.limit = limit
        self.used = used
        self.needed = needed
        self.resets_at = resets_at


class ConcurrencyLimitError(UrlpipeError):
    """429 ``concurrency_limit``: too many of your requests are already running."""

    default_message = "Too many of your requests are already running."

    def __init__(
        self,
        message: str,
        *,
        limit: Optional[int] = None,
        running: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.limit = limit
        self.running = running


class RateLimitedError(UrlpipeError):
    """429 ``rate_limited``: sending too fast. Wait ``retry_after`` seconds."""

    default_message = "Too many requests. Slow down and retry shortly."

    def __init__(
        self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(UrlpipeError):
    """5xx: something went wrong on URLpipe's side."""

    default_message = "URLpipe answered HTTP {status}: a server error."


class APIConnectionError(UrlpipeError):
    """The request never got an HTTP answer: DNS, refused connection, timeout."""


class WaitTimeoutError(UrlpipeError):
    """The analysis was still running when the wait deadline passed.

    It keeps running: collect it later with ``client.wait(error.token)``.
    """

    def __init__(self, message: str, *, token: str, timeout: float) -> None:
        super().__init__(message, token=token)
        self.timeout = timeout


class WebhookVerificationError(UrlpipeError):
    """A webhook delivery failed signature or timestamp verification."""


__all__ = [
    "APIConnectionError",
    "AnalysisFailedError",
    "AuthenticationError",
    "ConcurrencyLimitError",
    "ConfigurationError",
    "EmailUnverifiedError",
    "InvalidRequestError",
    "NotFoundError",
    "QuotaExceededError",
    "RateLimitedError",
    "ServerError",
    "StaleResultError",
    "UrlpipeError",
    "WaitTimeoutError",
    "WebhookVerificationError",
]
