# Changelog

## 0.1.0 — 2026-09-25

The first release.

- `Client` and `AsyncClient` with one method per operation: `markdown`, `html`, `summarize`, `screenshot`, `meta`, `keywords`, `console`, `lighthouse` and `scrape`, plus `result` and `wait` for tokens.
- Calls wait for their result by default; a call that outlives the API's 60-second sync window is polled to completion.
- Screenshots decoded to bytes, with the MIME type and the key-free image URL.
- Response metadata parsed from headers: cache status and age, processing time, credits spent and left, concurrency limit.
- Automatic retries for connection errors, rate and concurrency limits and 500/502/503, each call under one `Idempotency-Key`.
- A typed error for every failure the API reports.
- `verify_webhook` for signed webhook deliveries.
