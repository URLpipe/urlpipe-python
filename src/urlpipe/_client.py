"""``Client`` and ``AsyncClient``.

Both only drive the flows in ``_core``: one performs each action with blocking
calls, the other awaits it. The method signatures are written out twice so each
class is fully typed; the bodies are one line each.
"""

from __future__ import annotations

import asyncio
import os
import time
from types import TracebackType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Type, TypeVar, Union

import httpx

from . import _core
from ._core import AnalysisCall, Config, Flow, HttpRequest, Sleep
from ._models import (
    ConsoleEntry,
    Operation,
    PageMeta,
    Pdf,
    Response,
    ScrapeResult,
    Screenshot,
    Technologies,
)
from .errors import ConfigurationError

MaxAge = Union[int, str]
Labels = Mapping[str, str]
Options = Mapping[str, Any]
Fields = Sequence[Mapping[str, Any]]

_C = TypeVar("_C", bound="Client")
_A = TypeVar("_A", bound="AsyncClient")


class _BaseClient:
    def __init__(
        self,
        api_key: Optional[str],
        base_url: str,
        timeout: float,
        max_retries: int,
        wait_timeout: float,
        user_agent: Optional[str] = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("URLPIPE_API_KEY")
        if not key:
            raise ConfigurationError(
                "No URLpipe API key: pass api_key=... or set the URLPIPE_API_KEY "
                "environment variable. Each project's key is in its dashboard settings."
            )
        if max_retries < 0:
            raise ConfigurationError("max_retries must be 0 or more.")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.max_retries = max_retries
        self.wait_timeout = float(wait_timeout)
        self._config = Config(
            api_key=key,
            max_retries=max_retries,
            wait_timeout=self.wait_timeout,
            user_agent=_core.user_agent(user_agent),
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r})"

    def _url(self, request: HttpRequest) -> str:
        return self.base_url + request.path

    def _analysis(
        self,
        operation: str,
        url: str,
        idempotency_key: Optional[str],
        extra: Optional[Options],
        **params: Any,
    ) -> Flow:
        call: AnalysisCall = _core.build_analysis(
            self._config,
            operation,
            url,
            params=params,
            idempotency_key=idempotency_key,
            extra=extra,
        )
        return _core.analysis_flow(self._config, call)

    def _result(self, token: str, operation: Optional[str]) -> Flow:
        return _core.result_flow(self._config, token, operation)

    def _wait(
        self, token: str, operation: Optional[str], timeout: Optional[float], interval: float
    ) -> Flow:
        return _core.wait_flow(self._config, token, operation, timeout, interval)


class Client(_BaseClient):
    """The URLpipe API client.

    >>> client = urlpipe.Client()  # reads URLPIPE_API_KEY
    >>> client.markdown("https://example.com").data
    '# Example Domain ...'

    Every analysis method waits for its result (``sync=True``) unless you pass
    ``sync=False``, which returns an accepted Response with a ``token`` for
    :meth:`wait`. Failures raise a subclass of :class:`urlpipe.UrlpipeError`.

    Args:
        api_key: a project API key. Defaults to ``URLPIPE_API_KEY``.
        base_url: the API origin.
        timeout: seconds per HTTP request. The API holds a sync request for up
            to 60 s, so keep it above that.
        max_retries: automatic retries for connection errors, rate limits,
            concurrency limits and 500/502/503. Every retried analysis carries
            one ``Idempotency-Key``, so a retry never runs or bills twice.
        wait_timeout: how long a call that outlives the API's 60 s sync window
            keeps polling for its result, and the default for :meth:`wait`.
        user_agent: your program's product token, such as ``"my-app/1.2"``.
            It goes in front of the client's own, so requests identify both:
            ``my-app/1.2 urlpipe-python/0.3.0``.
        http_client: an ``httpx.Client`` to send requests with. You keep
            ownership: :meth:`close` leaves it open.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _core.DEFAULT_BASE_URL,
        timeout: float = _core.DEFAULT_TIMEOUT,
        max_retries: int = _core.DEFAULT_MAX_RETRIES,
        wait_timeout: float = _core.DEFAULT_WAIT_TIMEOUT,
        user_agent: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(api_key, base_url, timeout, max_retries, wait_timeout, user_agent)
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.Client()

    # -- plumbing ---------------------------------------------------------- #

    def _drive(self, flow: Flow) -> Response[Any]:
        outcome: _core.Outcome = None
        try:
            while True:
                action = flow.send(outcome)
                if isinstance(action, Sleep):
                    time.sleep(action.seconds)
                    outcome = None
                else:
                    outcome = self._send(action.request)
        except StopIteration as stop:
            response: Response[Any] = stop.value
            return response

    def _send(self, request: HttpRequest) -> Union[httpx.Response, httpx.TransportError]:
        try:
            return self._http.request(
                request.method,
                self._url(request),
                headers=request.headers,
                json=request.json,
                timeout=self.timeout,
            )
        except httpx.TransportError as exc:
            return exc

    def close(self) -> None:
        """Close the connection pool (unless you passed your own ``http_client``)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self: _C) -> _C:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    # -- operations -------------------------------------------------------- #

    def markdown(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[str]:
        """The page's main content as Markdown."""
        return self._drive(self._analysis(
            "markdown", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def html(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[str]:
        """The page's HTML after JavaScript has run."""
        return self._drive(self._analysis(
            "html", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def summarize(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[str]:
        """An AI summary of the page, as Markdown."""
        return self._drive(self._analysis(
            "summarize", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def screenshot(
        self,
        url: str,
        *,
        screenshot_options: Optional[Options] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Screenshot]:
        """A screenshot, full-page PNG by default, decoded to bytes."""
        return self._drive(self._analysis(
            "screenshot", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            screenshot_options=screenshot_options,
        ))

    def pdf(
        self,
        url: str,
        *,
        pdf_options: Optional[Options] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Pdf]:
        """The whole rendered page as a PDF, decoded to bytes."""
        return self._drive(self._analysis(
            "pdf", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            pdf_options=pdf_options,
        ))

    def meta(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[PageMeta]:
        """Title, description, language, author, dates, feed and images."""
        return self._drive(self._analysis(
            "meta", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def keywords(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[List[str]]:
        """5-15 keywords and key phrases, most relevant first."""
        return self._drive(self._analysis(
            "keywords", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def extract(
        self,
        url: str,
        fields: Fields,
        *,
        instructions: Optional[str] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Dict[str, Any]]:
        """Data from the page in the schema ``fields`` describes: one key per
        field, in order, ``None`` where the page gives no value."""
        return self._drive(self._analysis(
            "extract", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            fields=fields, instructions=instructions,
        ))

    def console(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[List[ConsoleEntry]]:
        """The console errors, warnings and uncaught exceptions of a page load."""
        return self._drive(self._analysis(
            "console", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def technologies(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Technologies]:
        """What a page is built with: its CMS, frameworks, analytics, CDN, with versions."""
        return self._drive(self._analysis(
            "technologies", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    def lighthouse(
        self,
        url: str,
        *,
        device: Optional[str] = None,
        include_audits: Optional[bool] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Dict[str, Any]]:
        """A Lighthouse audit: category scores and key metrics."""
        return self._drive(self._analysis(
            "lighthouse", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, device=device,
            include_audits=include_audits,
        ))

    def scrape(
        self,
        url: str,
        operations: Union[Sequence[str], str],
        *,
        device: Optional[str] = None,
        include_audits: Optional[bool] = None,
        screenshot_options: Optional[Options] = None,
        pdf_options: Optional[Options] = None,
        fields: Optional[Fields] = None,
        instructions: Optional[str] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[ScrapeResult]:
        """Several operations off one page visit."""
        return self._drive(self._analysis(
            "scrape", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            operations=_operations(operations), device=device, include_audits=include_audits,
            screenshot_options=screenshot_options, pdf_options=pdf_options,
            fields=fields, instructions=instructions,
        ))

    def result(self, token: str, *, operation: Optional[Operation] = None) -> Response[Any]:
        """Fetch a result by token, once. A ``"processing"`` Response means it is
        still running. Pass the original ``operation`` to type ``data``."""
        return self._drive(self._result(token, operation))

    def wait(
        self,
        token: str,
        *,
        operation: Optional[Operation] = None,
        timeout: Optional[float] = None,
        interval: float = 2.0,
    ) -> Response[Any]:
        """Poll a token until its result is ready.

        Raises :class:`urlpipe.WaitTimeoutError` after ``timeout`` seconds
        (default: the client's ``wait_timeout``). Pass the original
        ``operation`` to type ``data`` — ``operation="screenshot"`` or ``"pdf"``
        decodes the file, which otherwise stays Base64 text.
        """
        return self._drive(self._wait(token, operation, timeout, interval))


class AsyncClient(_BaseClient):
    """The URLpipe API client for asyncio. Same methods as :class:`Client`, as
    coroutines.

    >>> async with urlpipe.AsyncClient() as client:
    ...     page = await client.markdown("https://example.com")

    ``http_client`` takes an ``httpx.AsyncClient``; you keep ownership of it.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _core.DEFAULT_BASE_URL,
        timeout: float = _core.DEFAULT_TIMEOUT,
        max_retries: int = _core.DEFAULT_MAX_RETRIES,
        wait_timeout: float = _core.DEFAULT_WAIT_TIMEOUT,
        user_agent: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(api_key, base_url, timeout, max_retries, wait_timeout, user_agent)
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.AsyncClient()

    # -- plumbing ---------------------------------------------------------- #

    async def _drive(self, flow: Flow) -> Response[Any]:
        outcome: _core.Outcome = None
        try:
            while True:
                action = flow.send(outcome)
                if isinstance(action, Sleep):
                    await asyncio.sleep(action.seconds)
                    outcome = None
                else:
                    outcome = await self._send(action.request)
        except StopIteration as stop:
            response: Response[Any] = stop.value
            return response

    async def _send(self, request: HttpRequest) -> Union[httpx.Response, httpx.TransportError]:
        try:
            return await self._http.request(
                request.method,
                self._url(request),
                headers=request.headers,
                json=request.json,
                timeout=self.timeout,
            )
        except httpx.TransportError as exc:
            return exc

    async def close(self) -> None:
        """Close the connection pool (unless you passed your own ``http_client``)."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self: _A) -> _A:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    # -- operations -------------------------------------------------------- #

    async def markdown(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[str]:
        """The page's main content as Markdown."""
        return await self._drive(self._analysis(
            "markdown", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def html(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[str]:
        """The page's HTML after JavaScript has run."""
        return await self._drive(self._analysis(
            "html", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def summarize(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[str]:
        """An AI summary of the page, as Markdown."""
        return await self._drive(self._analysis(
            "summarize", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def screenshot(
        self,
        url: str,
        *,
        screenshot_options: Optional[Options] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Screenshot]:
        """A screenshot, full-page PNG by default, decoded to bytes."""
        return await self._drive(self._analysis(
            "screenshot", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            screenshot_options=screenshot_options,
        ))

    async def pdf(
        self,
        url: str,
        *,
        pdf_options: Optional[Options] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Pdf]:
        """The whole rendered page as a PDF, decoded to bytes."""
        return await self._drive(self._analysis(
            "pdf", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            pdf_options=pdf_options,
        ))

    async def meta(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[PageMeta]:
        """Title, description, language, author, dates, feed and images."""
        return await self._drive(self._analysis(
            "meta", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def keywords(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[List[str]]:
        """5-15 keywords and key phrases, most relevant first."""
        return await self._drive(self._analysis(
            "keywords", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def extract(
        self,
        url: str,
        fields: Fields,
        *,
        instructions: Optional[str] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Dict[str, Any]]:
        """Data from the page in the schema ``fields`` describes: one key per
        field, in order, ``None`` where the page gives no value."""
        return await self._drive(self._analysis(
            "extract", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            fields=fields, instructions=instructions,
        ))

    async def console(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[List[ConsoleEntry]]:
        """The console errors, warnings and uncaught exceptions of a page load."""
        return await self._drive(self._analysis(
            "console", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def technologies(
        self,
        url: str,
        *,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Technologies]:
        """What a page is built with: its CMS, frameworks, analytics, CDN, with versions."""
        return await self._drive(self._analysis(
            "technologies", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
        ))

    async def lighthouse(
        self,
        url: str,
        *,
        device: Optional[str] = None,
        include_audits: Optional[bool] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[Dict[str, Any]]:
        """A Lighthouse audit: category scores and key metrics."""
        return await self._drive(self._analysis(
            "lighthouse", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, device=device,
            include_audits=include_audits,
        ))

    async def scrape(
        self,
        url: str,
        operations: Union[Sequence[str], str],
        *,
        device: Optional[str] = None,
        include_audits: Optional[bool] = None,
        screenshot_options: Optional[Options] = None,
        pdf_options: Optional[Options] = None,
        fields: Optional[Fields] = None,
        instructions: Optional[str] = None,
        sync: bool = True,
        max_age: Optional[MaxAge] = None,
        labels: Optional[Labels] = None,
        residential: Optional[bool] = None,
        report_to: Optional[str] = None,
        page_options: Optional[Options] = None,
        idempotency_key: Optional[str] = None,
        extra: Optional[Options] = None,
    ) -> Response[ScrapeResult]:
        """Several operations off one page visit."""
        return await self._drive(self._analysis(
            "scrape", url, idempotency_key, extra, sync=sync, max_age=max_age, labels=labels,
            residential=residential, report_to=report_to, page_options=page_options,
            operations=_operations(operations), device=device, include_audits=include_audits,
            screenshot_options=screenshot_options, pdf_options=pdf_options,
            fields=fields, instructions=instructions,
        ))

    async def result(self, token: str, *, operation: Optional[Operation] = None) -> Response[Any]:
        """Fetch a result by token, once. A ``"processing"`` Response means it is
        still running. Pass the original ``operation`` to type ``data``."""
        return await self._drive(self._result(token, operation))

    async def wait(
        self,
        token: str,
        *,
        operation: Optional[Operation] = None,
        timeout: Optional[float] = None,
        interval: float = 2.0,
    ) -> Response[Any]:
        """Poll a token until its result is ready. See :meth:`Client.wait`."""
        return await self._drive(self._wait(token, operation, timeout, interval))


def _operations(operations: Union[Sequence[str], str]) -> Union[List[str], str]:
    return operations if isinstance(operations, str) else list(operations)
