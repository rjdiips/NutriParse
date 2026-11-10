# 01: Typed settings with live reload

**What to build:** Every runtime setting is parsed and validated into one typed settings object that the server and tests share. Process environment variables override the local environment file for every known setting, including the image and legacy API-key settings. Editing the local environment file still takes effect without restarting the server. Invalid values fail with a clear, early message instead of surfacing mid-request.

**Blocked by:** None (can start immediately)

**Status:** done

**Decisions locked:**
- Use `pydantic-settings` with one typed settings object.
- Cover provider, base URL, model, API key, timeout, reasoning effort, JSON mode, OpenRouter key/model/base URL, and image URL/enabled/width/height/steps.
- Preserve the legacy API-key aliases and the `LLM_TIMEOUT` override.
- Keep the mtime-based live reload.
- Remove the hardcoded environment-key allowlist.

- [x] A setting supplied only by the process environment overrides the local environment file for every field, including image settings and both legacy API-key aliases.
- [x] `LLM_TIMEOUT` still overrides the provider default, and invalid or non-positive values fall back to the documented default.
- [x] Editing the local environment file while the server runs changes the next request's behavior without a restart.
- [x] Tests build settings directly from a temporary file or mapping; no test mutates global application state to isolate configuration.
- [x] The full test suite passes and the lint check is clean.
