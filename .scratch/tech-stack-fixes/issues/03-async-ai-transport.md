# 03: Non-blocking AI and image transport

**What to build:** AI and image calls run on a shared asynchronous HTTP client with bounded concurrency. A slow image generation no longer occupies a worker thread that the rest of the app needs; concurrent Cook runs do not starve journal requests; closing the browser tab cancels the upstream call; transient provider failures retry with backoff.

**Blocked by:** 01 — Typed settings with live reload

**Status:** done

**Decisions locked:**
- Add `httpx` as a runtime dependency and create one async client in the application lifespan.
- Convert AI and image routes to async; leave journal routes synchronous.
- Cap concurrency at three LLM calls and one image generation.
- Retry up to three total attempts on 429/5xx with 0.5 s then 1.5 s backoff; never retry 4xx.
- Take per-call timeouts from the typed settings.
- Cancel the upstream call when the client disconnects.

- [x] Concurrent Cook and image requests do not exhaust the worker pool; journal reads respond while images generate.
- [x] Aborting a browser request cancels the upstream provider or image call.
- [x] 429/5xx responses retry up to three total attempts with the stated backoff; 4xx responses do not retry.
- [x] Image generation never runs more than one call at a time; LLM calls never exceed three.
- [x] Existing error envelopes, status codes, and log fields are preserved.
- [x] Tests use a stubbed transport; the full suite and lint pass.
