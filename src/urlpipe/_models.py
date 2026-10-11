"""The values the client hands back: the Response, its meta, and typed results."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generic, List, Literal, Optional, TypedDict, TypeVar, Union

T = TypeVar("T")

Operation = Literal[
    "markdown",
    "html",
    "summarize",
    "screenshot",
    "pdf",
    "meta",
    "keywords",
    "extract",
    "console",
    "technologies",
    "lighthouse",
    "scrape",
]
"""An analysis endpoint. Pass one as the ``operation`` hint to ``result``/``wait``."""

ResponseStatus = Literal["completed", "accepted", "processing"]


class ConsoleEntry(TypedDict):
    """One message a page wrote to its console."""

    type: Literal["error", "warning", "exception"]
    text: str


class TechnologyCategory(TypedDict):
    """A kind of technology: ``{"slug": "cms", "name": "CMS"}``."""

    slug: str
    name: str


class Technology(TypedDict):
    """One technology a page is built with."""

    name: str
    slug: str
    version: Optional[str]
    confidence: int
    categories: List[TechnologyCategory]
    website: Optional[str]
    description: Optional[str]
    cpe: Optional[str]
    detected_by: List[str]
    implied_by: List[str]


class Technologies(TypedDict):
    """The ``/technologies`` result: every technology detected, most certain first."""

    final_url: Optional[str]
    technologies: List[Technology]


class MetaAuthor(TypedDict):
    """One author of the page."""

    name: str
    url: Optional[str]
    profiles: List[str]


class MetaImage(TypedDict):
    """The page's share image, with what the page declares about it."""

    url: str
    width: Optional[int]
    height: Optional[int]
    alt: Optional[str]
    type: Optional[str]


class MetaVideo(TypedDict):
    """The page's video."""

    url: str
    type: Optional[str]
    width: Optional[int]
    height: Optional[int]


class MetaIcon(TypedDict):
    """An icon the page declares."""

    url: str
    rel: str
    sizes: Optional[str]
    type: Optional[str]


class MetaFeed(TypedDict):
    """An RSS, Atom or JSON feed."""

    url: str
    type: Optional[str]
    title: Optional[str]


class MetaRobots(TypedDict):
    """Whether search engines may index the page and follow its links."""

    index: bool
    follow: bool


class MetaOpenGraph(TypedDict):
    """The page's og: tags, as declared."""

    title: Optional[str]
    description: Optional[str]
    image: Optional[str]
    url: Optional[str]
    type: Optional[str]
    site_name: Optional[str]
    locale: Optional[str]


class MetaTwitter(TypedDict):
    """The page's twitter: tags, as declared."""

    card: Optional[str]
    site: Optional[str]
    creator: Optional[str]
    title: Optional[str]
    description: Optional[str]
    image: Optional[str]


class MetaAlternate(TypedDict):
    """The page in another language."""

    hreflang: str
    url: str


class PageMeta(TypedDict):
    """What ``/meta`` returns. Every key is always present; a value the page
    doesn't declare is ``None`` or an empty list. URLs are absolute, dates ISO 8601.

    ``final_url`` is the address the page ended on, after its redirects; the
    page's relative URLs are resolved against it."""

    final_url: Optional[str]
    canonical_url: Optional[str]
    title: Optional[str]
    description: Optional[str]
    site_name: Optional[str]
    type: Optional[str]
    language: Optional[str]
    locale: Optional[str]
    authors: List[MetaAuthor]
    published_at: Optional[str]
    modified_at: Optional[str]
    image: Optional[MetaImage]
    video: Optional[MetaVideo]
    favicon_url: Optional[str]
    icons: List[MetaIcon]
    logo_url: Optional[str]
    feeds: List[MetaFeed]
    keywords: List[str]
    theme_color: Optional[str]
    generator: Optional[str]
    manifest_url: Optional[str]
    robots: MetaRobots
    open_graph: MetaOpenGraph
    twitter: MetaTwitter
    alternates: List[MetaAlternate]
    oembed_url: Optional[str]
    structured_data_types: List[str]


class ScrapeOperationResult(TypedDict, total=False):
    """One operation's entry in a ``/scrape`` result."""

    success: bool
    result: Any
    error: Optional[str]
    cached: bool


class ScrapeResult(TypedDict):
    """What ``/scrape`` returns: one entry per requested operation.

    A screenshot or a PDF inside a scrape stays Base64 text, exactly as the API
    sends it.
    """

    url: str
    final_url: Optional[str]
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
    final_url: Optional[str] = None
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
class Pdf:
    """A decoded PDF of the page."""

    data: bytes = field(repr=False)
    mime_type: str = "application/pdf"
    result_url: Optional[str] = None

    @property
    def size(self) -> int:
        """The PDF size in bytes."""
        return len(self.data)

    def save(self, path: Union[str, "os.PathLike[str]"]) -> Path:
        """Write the PDF to ``path`` and return it as a ``Path``."""
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
    "Pdf",
    "Quota",
    "Response",
    "ResponseMeta",
    "ResponseStatus",
    "ScrapeOperationResult",
    "ScrapeResult",
    "Technologies",
    "Technology",
    "TechnologyCategory",
    "Screenshot",
]
