# 02: Server-driven AI timeouts

**What to build:** A configuration endpoint reports the active provider, model, and effective parse, cook, and image timeouts. Both browser pages read those values at startup and wait slightly longer than the server, so the server's own error wins instead of the client aborting first. A cold local model that needs more than the old 45-second client limit now completes.

**Blocked by:** 01 — Typed settings with live reload

**Status:** done

**Decisions locked:**
- The config endpoint returns provider, model, and parse/cook/image timeouts as integer milliseconds.
- The response is not cached.
- Clients wait the server timeout plus 10 seconds.
- If the config call fails, clients use a 300-second safety net and show a clear message; the journal remains usable.
- Effective values appear in the request-details panel.

- [x] The config endpoint returns the effective provider, model, and all three timeouts, and the values change when the provider or `LLM_TIMEOUT` changes.
- [x] Compose parse waits the server timeout plus 10 seconds rather than a hard-coded 45 seconds; a local model answering after 45 seconds succeeds.
- [x] Cook's client timeout is longer than the server timeout, so the 180-versus-180 race is gone.
- [x] Food Journal uses the same config values as Compose.
- [x] When the config call fails, AI calls use the 300-second safety net, show a clear message, and journal reads and writes still work.
- [x] Request details show the effective timeout values.
- [x] Tests cover the endpoint and the client fallback; the full suite and lint pass.
