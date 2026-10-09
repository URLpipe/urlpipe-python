# urlpipe

Turn any URL into clean Markdown, rendered HTML, a full-page screenshot, metadata, a summary, keywords, console errors, a Lighthouse audit or the technologies it is built with — from Python, in one call. Pages are rendered in real Chrome, so JavaScript-heavy sites come back complete.

This is the official Python client for the [URLpipe API](https://urlpipe.dev/docs). It works sync or async, is fully typed, and depends only on `httpx`.

## Install

```sh
pip install urlpipe
```

Python 3.9 or later.

## Quickstart

Create a project in the [dashboard](https://urlpipe.dev) and copy its API key. The Free plan gives you 1,000 credits a month, no card needed.

```sh
export URLPIPE_API_KEY=your_project_key
```

```python
import urlpipe

client = urlpipe.Client()  # reads URLPIPE_API_KEY

page = client.markdown("https://example.com")
print(page.data)  # "# Example Domain\n\nThis domain is for use in …"
```

Every method waits for the result and returns a `Response`:

| Field | What it holds |
|---|---|
| `status` | `"completed"`, `"accepted"` (an async request was taken) or `"processing"` (still running) |
| `data` | the result, typed per operation; `None` unless completed |
| `token` | the request's token — fetch the result again for free with `client.result(token)` |
| `labels` | the labels the request was made with |
| `meta` | `cache`, `cache_age`, `processing_time_ms`, `quota` (`cost`, `limit`, `remaining`, `overage`, `resets_at`), `concurrency_limit`, `result_url`, `final_url` (where the page ended up, after its redirects), `idempotent_replayed` |

```python
page.meta.cache             # "hit" — served from cache, cost nothing
page.meta.quota.remaining   # 943, or "unlimited"
```

## Operations

Every method takes the URL first; everything else is an optional keyword.

```python
client.markdown("https://example.com").data      # str: the main content as Markdown
client.html("https://example.com").data          # str: the HTML after JavaScript ran
client.summarize("https://example.com").data     # str: an AI summary, in Markdown
client.meta("https://example.com").data          # dict: title, description, image, authors, published_at, …
client.keywords("https://example.com").data      # list[str], most relevant first
client.console("https://example.com").data       # [{"type": "error", "text": "…"}, …]
client.technologies("https://example.com").data  # dict: {"final_url", "technologies": [{"name", "version", …}]}
client.lighthouse("https://example.com", device="desktop", include_audits=True).data
```

### Screenshots

```python
shot = client.screenshot(
    "https://example.com/pricing",
    screenshot_options={"viewport_width": 390, "format": "webp"},
).data

shot.save("pricing.webp")
shot.mime_type    # "image/webp", read from the image bytes
shot.result_url   # a link to the image that needs no API key, for an <img> tag
shot.data         # the decoded bytes
```

### Several operations off one page visit

```python
result = client.scrape("https://example.com", ["markdown", "meta", "screenshot"]).data
result["operations"]["meta"]["result"]["title"]
```

Each operation has its own `success`, `result`, `error` and `cached`; one failing never affects the others. A screenshot inside a scrape is Base64 text, as the API returns it.

### Options every method takes

```python
client.markdown(
    "https://example.com/blog",
    max_age="1 hour",                     # or seconds; 0 skips the cache
    labels={"client": "acme"},            # your own ids, returned with the result
    residential=True,                     # fetch from a home broadband address
    page_options={"block_cookie_banners": True, "remove_selectors": [".promo"]},
    idempotency_key="import-2026-09-25-17",
)
```

`page_options` is not accepted by `lighthouse`. Options the API adds after this release can be sent with `extra`, which is merged into the request body as given:

```python
client.markdown("https://example.com", extra={"some_option": True})
```

The client passes option values through unchanged; the API validates them and answers `InvalidRequestError` naming what to change.

## Async requests and `wait`

Pass `sync=False` and the call returns straight away with a token, while the work carries on. Collect the result by polling, or have it POSTed to a webhook with `report_to`.

```python
accepted = client.lighthouse("https://example.com", sync=False)
accepted.status  # "accepted"

report = client.wait(accepted.token, operation="lighthouse")  # polls every 2 s
report.data["categories"]["performance"]["score"]
```

`client.result(token)` makes a single check instead: it returns a `"processing"` Response while the work is running.

`GET /result` does not say which operation made a token, so pass `operation=` to get typed `data`. Without it, JSON comes back parsed and text as a string — a screenshot stays Base64 until you ask for `wait(token, operation="screenshot")`.

A synchronous call that runs past the API's 60-second window is not an error: the client polls for the result itself and returns it, for up to `wait_timeout` seconds (5 minutes by default) before raising `WaitTimeoutError`. The work keeps running either way, so `client.wait(error.token)` picks it up later.

### asyncio

`AsyncClient` has the same methods, as coroutines:

```python
import asyncio
import urlpipe

async def main() -> None:
    async with urlpipe.AsyncClient() as client:
        pages = await asyncio.gather(
            client.markdown("https://example.com/a"),
            client.markdown("https://example.com/b"),
        )
        print([p.data for p in pages])

asyncio.run(main())
```

## Webhooks

With webhook signing on (project **Settings → Webhook Signing**), check each delivery came from URLpipe before you trust it. `verify_webhook` needs no client:

```python
import os
import urlpipe
from flask import Flask, request, abort

app = Flask(__name__)

@app.post("/webhooks/urlpipe")
def urlpipe_webhook():
    try:
        delivery = urlpipe.verify_webhook(
            request.get_data(),          # the raw body bytes
            request.headers,
            os.environ["URLPIPE_WEBHOOK_SECRET"],  # whsec_…
        )
    except urlpipe.WebhookVerificationError:
        abort(401)
    enqueue(delivery["token"], delivery["result"])
    return "", 200
```

Give it the **raw request body** exactly as received (`request.get_data()` in Flask, `await request.body()` in FastAPI, `request.body` in Django). Parsed and re-serialised JSON has different bytes, and the signature will not match. Header names are matched case-insensitively; deliveries signed more than `tolerance` seconds ago (300 by default) are refused, and during a secret rotation either signature is accepted.

It returns the payload: `token`, `operation`, `labels`, `success`, `result`, `result_url`, `final_url`, `error` and `meta`.

## Errors

Every error is a `urlpipe.UrlpipeError`, with `status`, `code`, `message`, `body` and `token`.

| Error | When |
|---|---|
| `AuthenticationError` | 401: the API key is missing or wrong |
| `EmailUnverifiedError` | 403: confirm the email address on the account |
| `InvalidRequestError` | 422: a parameter was refused (`invalid_url`, `invalid_options`, …); nothing ran |
| `AnalysisFailedError` | 422: the page could not be analysed; `message` says why |
| `QuotaExceededError` | 429: the Free plan's credits are spent (`limit`, `used`, `needed`, `resets_at`) |
| `ConcurrencyLimitError` | 429: too many of your requests running (`limit`, `running`) |
| `RateLimitedError` | 429: sending too fast (`retry_after`) |
| `NotFoundError` | 404: no result for this token |
| `StaleResultError` | 410: the result is past the 30-day window |
| `ServerError` | 5xx |
| `APIConnectionError` | no HTTP answer at all |
| `WaitTimeoutError` | the result was not ready within the wait timeout (`token`) |

```python
try:
    page = client.markdown(url)
except urlpipe.AnalysisFailedError as error:
    print("Could not read the page:", error.message)
except urlpipe.QuotaExceededError as error:
    print("Out of credits until", error.resets_at)
```

A failed analysis costs nothing, and neither does a cache hit.

## Identifying your program

If you build a library or a tool on this client, pass its name, and your requests carry both:

```python
client = urlpipe.Client(user_agent="my-tool/1.4")  # User-Agent: my-tool/1.4 urlpipe-python/0.2.0
```

## Retries and idempotency

The client retries connection errors, rate limits (after `Retry-After`, up to 60 s), concurrency limits and 500/502/503 responses — twice by default, with exponential backoff. It never retries a 4xx other than those, or a spent quota.

A retry is only safe if it cannot run the work twice, so every analysis the client may retry carries an `Idempotency-Key`: yours if you pass `idempotency_key=`, otherwise one generated for that call and reused by all of its retries. The API answers a repeated key with the first request's result — one run, one charge, one webhook. When you retry across processes yourself (a job that ran twice), pass the same key each time.

```python
client = urlpipe.Client(
    api_key="…",          # default: URLPIPE_API_KEY
    timeout=90,           # seconds per HTTP request
    max_retries=2,        # 0 turns retries off
    wait_timeout=300,     # how long a slow sync call keeps polling
)
```

For a proxy, custom TLS or test transports, pass your own `httpx.Client` (or `httpx.AsyncClient`) as `http_client=`. You keep ownership of it; closing the URLpipe client leaves it open.

## Links

- API docs: https://urlpipe.dev/docs
- Pricing: https://urlpipe.dev/pricing
- MCP server, for using URLpipe from AI assistants: https://github.com/URLpipe/mcp

## License

MIT © Aliat Partner S.L.
