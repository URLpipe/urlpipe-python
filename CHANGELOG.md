# Changelog

## Unreleased

- `ResponseMeta.final_url` is the address the page ended on, after its redirects (the `X-Final-Url` header). A `/meta` result and a `/scrape` result carry it as `final_url` too, and so does a webhook payload.
- `meta` returns the fixed shape of `/meta`: every key always present — `canonical_url`, `title`, `description`, `site_name`, `type`, `language`, `locale`, `authors`, `published_at`, `modified_at`, `image`, `video`, `favicon_url`, `icons`, `logo_url`, `feeds`, `keywords`, `theme_color`, `generator`, `manifest_url`, `robots`, `open_graph`, `twitter`, `alternates`, `oembed_url`, `structured_data_types`. `PageMeta` describes it, with a typed dict for each nested object (`MetaImage`, `MetaAuthor`, …). `main_image_url`, `author_name`, `publication_date`, `feed_url` and `additional_author_information` are gone: read `image["url"]`, `authors`, `published_at` and `feeds`.

## 0.2.0

- `user_agent=` on `Client` and `AsyncClient` names the program making the requests; the User-Agent then reads `<product> urlpipe-python/<version>`.

## 0.1.0 — 2026-09-25

The first release.

- `Client` and `AsyncClient` with one method per operation: `markdown`, `html`, `summarize`, `screenshot`, `meta`, `keywords`, `console`, `lighthouse` and `scrape`, plus `result` and `wait` for tokens.
- Calls wait for their result by default; a call that outlives the API's 60-second sync window is polled to completion.
- Screenshots decoded to bytes, with the MIME type and the key-free image URL.
- Response metadata parsed from headers: cache status and age, processing time, credits spent and left, concurrency limit.
- Automatic retries for connection errors, rate and concurrency limits and 500/502/503, each call under one `Idempotency-Key`.
- A typed error for every failure the API reports.
- `verify_webhook` for signed webhook deliveries.
