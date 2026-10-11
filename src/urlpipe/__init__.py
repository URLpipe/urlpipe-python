"""The official Python client for the URLpipe API: turn a URL into Markdown,
HTML, a screenshot, a PDF, metadata, a summary, keywords, data in a schema you
define, console errors, a Lighthouse audit or the technologies a site is built
with.

    import urlpipe

    client = urlpipe.Client()  # reads URLPIPE_API_KEY
    print(client.markdown("https://example.com").data)

Docs: https://urlpipe.dev/docs
"""

from . import errors
from ._client import AsyncClient, Client
from ._models import (
    ConsoleEntry,
    MetaAlternate,
    MetaAuthor,
    MetaFeed,
    MetaIcon,
    MetaImage,
    MetaOpenGraph,
    MetaRobots,
    MetaTwitter,
    MetaVideo,
    Operation,
    PageMeta,
    Pdf,
    Quota,
    Response,
    ResponseMeta,
    ResponseStatus,
    ScrapeOperationResult,
    ScrapeResult,
    Screenshot,
    Technologies,
    Technology,
    TechnologyCategory,
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
    "MetaAlternate",
    "MetaAuthor",
    "MetaFeed",
    "MetaIcon",
    "MetaImage",
    "MetaOpenGraph",
    "MetaRobots",
    "MetaTwitter",
    "MetaVideo",
    "NotFoundError",
    "Operation",
    "PageMeta",
    "Pdf",
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
    "Technologies",
    "Technology",
    "TechnologyCategory",
    "UrlpipeError",
    "WaitTimeoutError",
    "WebhookVerificationError",
    "__version__",
    "errors",
    "verify_webhook",
]
