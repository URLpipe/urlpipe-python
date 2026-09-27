"""The values the client hands back: the Response, its meta, and typed results."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generic, Literal, Optional, TypedDict, TypeVar, Union

T = TypeVar("T")

Operation = Literal[
    "markdown",
    "html",
    "summarize",
    "screenshot",
    "meta",
    "keywords",
    "console",
    "lighthouse",
    "scrape",
]
"""An analysis endpoint. Pass one as the ``operation`` hint to ``result``/``wait``."""

ResponseStatus = Literal["completed", "accepted", "processing"]


class ConsoleEntry(TypedDict):
    """One message a page wrote to its console."""

    type: Literal["error", "warning", "exception"]
    text: str


class PageMeta(TypedDict, total=False):
    """What ``/meta`` returns. Any field can be ``None``."""

    title: Optional[str]
    description: Optional[str]
    language: Optional[str]
    main_image_url: Optional[str]
    favicon_url: Optional[str]
    author_name: Optional[str]
    feed_url: Optional[str]
    publication_date: Optional[str]
    additional_author_information: Optional[Dict[str, Any]]


class ScrapeOperationResult(TypedDict, total=False):
    """One operation's entry in a ``/scrape`` result."""

    success: bool
    result: Any
    error: Optional[str]
    cached: bool


class ScrapeResult(TypedDict):
    """What ``/scrape`` returns: one entry per requested operation.

    A screenshot inside a scrape stays Base64 text, exactly as the API sends it.
    """

    url: str
    operations: Dict[str, ScrapeOperationResult]


@dataclass(frozen=True)
class Quota:
    """Credit figures from the ``X-Quota-*`` headers.

    ``limit`` and ``remaining`` are the string ``"unlimited"`` on an unlimited plan.
    """

    cost: Optional[int] = None
    limit: Union[int, str, None] = None
    remaining: Union[int, str, None] = None
    overage: Optional[int] = None
    resets_at: Optional[str] = None


@dataclass(frozen=True)
class ResponseMeta:
    """The metadata headers of a response, parsed. A missing header is ``None``."""

    cache: Optional[str] = None
    cache_age: Optional[int] = None
    processing_time_ms: Optional[int] = None
    quota: Quota = field(default_factory=Quota)
    concurrency_limit: Union[int, str, None] = None
    result_url: Optional[str] = None
    idempotent_replayed: bool = False


@dataclass(frozen=True)
class Screenshot:
    """A decoded screenshot image."""

    data: bytes = field(repr=False)
    mime_type: str
    result_url: Optional[str] = None

    @property
    def size(self) -> int:
        """The image size in bytes."""
        return len(self.data)

    def save(self, path: Union[str, "os.PathLike[str]"]) -> Path:
        """Write the image to ``path`` and return it as a ``Path``."""
        target = Path(path)
        target.write_bytes(self.data)
        return target


@dataclass(frozen=True)
class Response(Generic[T]):
    """What every client method returns.

    ``status`` is ``"completed"`` (``data`` holds the result), ``"accepted"`` (an
    async request was taken; collect it with ``wait(token)``) or ``"processing"``
    (``result(token)`` found it still running).
    """

    status: ResponseStatus
    data: Optional[T]
    token: Optional[str]
    labels: Dict[str, str]
    meta: ResponseMeta
    http_status: int

    @property
    def completed(self) -> bool:
        return self.status == "completed"


__all__ = [
    "ConsoleEntry",
    "Operation",
    "PageMeta",
    "Quota",
    "Response",
    "ResponseMeta",
    "ResponseStatus",
    "ScrapeOperationResult",
    "ScrapeResult",
    "Screenshot",
]
