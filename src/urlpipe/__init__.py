"""The official Python client for the URLpipe API: turn a URL into Markdown,
HTML, a screenshot, metadata, a summary, keywords, console errors or a
Lighthouse audit.

    import urlpipe

    client = urlpipe.Client()  # reads URLPIPE_API_KEY
    print(client.markdown("https://example.com").data)

Docs: https://urlpipe.dev/docs
"""

from . import errors
from ._client import AsyncClient, Client
from ._models import (
    ConsoleEntry,
    Operation,
    PageMeta,
    Quota,
    Response,
    ResponseMeta,
    ResponseStatus,
    ScrapeOperationResult,
    ScrapeResult,
    Screenshot,
)
from ._version import __version__
from .errors import (
    AnalysisFailedError,
    APIConnectionError,
    AuthenticationError,
    ConcurrencyLimitError,
    ConfigurationError,
    EmailUnverifiedError,
    InvalidRequestError,
    NotFoundError,
    QuotaExceededError,
    RateLimitedError,
    ServerError,
    StaleResultError,
    UrlpipeError,
    WaitTimeoutError,
    WebhookVerificationError,
)
from .webhooks import verify_webhook

__all__ = [
    "APIConnectionError",
    "AnalysisFailedError",
    "AsyncClient",
    "AuthenticationError",
    "Client",
    "ConcurrencyLimitError",
    "ConfigurationError",
    "ConsoleEntry",
    "EmailUnverifiedError",
    "InvalidRequestError",
    "NotFoundError",
    "Operation",
    "PageMeta",
    "Quota",
    "QuotaExceededError",
    "RateLimitedError",
    "Response",
    "ResponseMeta",
    "ResponseStatus",
    "ScrapeOperationResult",
    "ScrapeResult",
    "Screenshot",
    "ServerError",
    "StaleResultError",
    "UrlpipeError",
    "WaitTimeoutError",
    "WebhookVerificationError",
    "__version__",
    "errors",
    "verify_webhook",
]
