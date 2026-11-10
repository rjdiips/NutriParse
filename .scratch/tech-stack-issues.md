# Tech stack review — NutriParse

**Date:** 2026-11-06
**Scope:** backend (`app/`), browser app (`web/`), persistence, tooling, and the model/validation boundary.
**Method:** read the source, ran the suite (then 81 tests, `OK`), and dumped the generated OpenAPI document.

> **Status (same day):** Issues 3 (multi-process safety) and 4 (Pydantic/OpenAPI) are fixed. The
> suite is now 84 tests, `OK`. `store.number()` looked dead in `app/`, but `evals/run_parse_eval.py`
> imports it, so it stays. Issue text below is kept as the original finding, with a `Resolved` note
> where the code moved on.

> **Not covered:** front-end consolidation. Which page survives is an open product decision, so
> no remediation is proposed here for that issue. The duplication is recorded as an observation
> (Issue 1) without a chosen fix, because its remediation depends on that decision.

---

## Verdict

The stack is coherent and appropriately small for a local, single-user app. The weaknesses are
not in the framework choices — FastAPI/Uvicorn and a no-build frontend are correctly sized. They
are in three seams:

1. A JSON file used as a database. *(Fixed: writers now take a cross-process lock file.)*
2. Validation, configuration, and transport written by hand while FastAPI/Pydantic sit unused.
   *(Partly fixed: requests and responses are typed Pydantic models; config and transport remain hand-rolled.)*
3. No lockfile, lint, type-check, or CI gate around either language.

The single highest-leverage *product* change is separate from the web stack: ground nutrition in a
deterministic dataset instead of asking the LLM for calories directly (Issue 11).

---

## Strengths to preserve

- **Two runtime dependencies** (`fastapi`, `uvicorn`). The store and LLM transport use the
  standard library. Keep that instinct.
- **Clean backend seams:** `app/services/`, `app/web/routers/`, `app/journal/store.py` each own one
  concern.
- **Fail-closed persistence:** validation before write, atomic `os.replace`, corrupt files raise
  rather than reset (`app/journal/store.py`).
- **The evaluation harness** (`evals/`): fixed fixtures, per-item ranges, signed error/MAE, committed
  results. This is the most valuable part of the repo and should stay.
- **No-build frontend:** accessible markup, `textContent` for model output, fast load. Do not replace
  it with a SPA to solve the issues below.

---

## Issues

### 1. Two front ends duplicate the same client logic — *decision pending, no fix proposed*

**Severity:** high long-term maintenance; not urgent while the app is local.

`web/pages/nutriparse.html` loads eight scripts that share globals. `web/pages/food-journal.html`
loads `web/js/food-journal.js` (794 lines), which re-implements date formatting, number formatting,
fetch wrappers, error handling, recipe cards, and image loading. The two already disagree about
timeouts:

| Concern | Compose (`web/js/nutriparse.js`) | Food Journal (`web/js/food-journal.js`) | Server (`app/config.py`) |
| --- | --- | --- | --- |
| Parse timeout | 45 s (`:9`) | 185 s (`:55`) | 180 s local / 30 s OpenRouter (`:90`) |
| Cook timeout | 180 s (`:10`) | 750 s (`:72`) | 180 s local / 45 s OpenRouter |
| Image timeout | none | 300 s (`:85`) | 240 s (`app/services/images.py:40`) |

A cold local model that answers in ~90 s is reported as a timeout on the Compose page while the
Food Journal waits it out. This is Issue 8's timeout drift, made worse by duplication.

**Remediation:** intentionally deferred. Do not consolidate until the surviving page is chosen.
Until then, treat `food-journal.html` as frozen and avoid feature work in `food-journal.js`.

---

### 2. Ordered `<script>` tags with implicit globals — *fragility*

**Severity:** medium.

`web/pages/nutriparse.html:281-289` loads nine scripts in a required order. `nutriparse.js` declares
`state`, `el`, and shared helpers as globals; the other files reference them across file boundaries
(e.g. `web/js/nutriparse/journal.js:8` declares `journal` and `journalLoaded` at top level). A
misspelled key is a runtime error, not a build error. There is no lint or type-check on roughly
2,000 lines of JS.

**Remediation (no bundler required):**

- Move to native ES modules (`<script type="module">`) with explicit `import`/`export`. This removes
  load-order coupling while keeping the zero-build workflow.
- Add JSDoc + `// @ts-check` and run `tsc --noEmit` as a check.
- Add ESLint + Prettier.
- Only add a bundler (Vite) if the UI later justifies it; the same ES modules can be consumed then.

---

### 3. `data.json` is the weakest layer — *correctness under concurrency* — **RESOLVED (file lock)**

**Severity:** was high for anything beyond one process. Fixed without changing the storage format.

Evidence:

- Every mutation rewrites the whole document (`app/journal/store.py:147-168`).
- Every read returns the whole document (`app/journal/store.py:115-144`).
- Mutual exclusion was `_LOCK = threading.Lock()`, which only works inside one process.
- The README documented a second-process race as "last-write-wins."

Running `uvicorn --workers 2` made the thread lock meaningless.

**Resolved:** every mutation now nests the thread lock inside a sidecar file lock
(`data.json.lock`) using `msvcrt.locking` on Windows and `fcntl.flock` elsewhere, with a 10 s
timeout that raises `StoreBusy` → HTTP 503. Reads stay lock-free because `os.replace` is atomic.
`tests/test_store.py` covers four spawned processes writing the same file.

**Remaining option (not required):** stdlib `sqlite3` in WAL mode behind the existing response shape.

- `entries` table (id, name, portion, calories, protein, carbs, fat, meal, date) and a `settings`
  table (calorie goal).
- Real transactions, per-entry CRUD, concurrent readers with one writer, no new dependency.
- Keeps the door open to Postgres if this ever becomes multi-user.

The file lock shipped instead; a document version field is still worth adding if migrations matter.

---

### 4. Pydantic is installed but unused; the OpenAPI document is empty — **RESOLVED**

**Severity:** was medium — free functionality was being left on the table.

`pydantic==2.14.1` was installed and the README advertised "Pydantic underneath," but no `BaseModel`
existed in `app/`. Requests were raw dicts (`JSONBody = Annotated[dict, Depends(json_body)]`) and
validated by hand in every router. Responses were untyped dicts. The generated document had an
empty `requestBody` for every POST/PUT and no response schemas, so `/docs` could not send a body.

**Resolved:** `app/web/schemas.py` now holds the request/response models, routers declare
`response_model`, `response_model_exclude_none`, and typed error responses. `app.openapi()` reports
9 operations with request bodies for the 6 that take one (the other 3 are GET/DELETE). The JSON
envelope guard (`json_body`) stays so content-type, length, and oversized-body messages are
unchanged, and the store/service layer keeps the domain validation messages. `/api/*` and `/health`
retain `Cache-Control: no-store` and `X-Content-Type-Options: nosniff` through middleware.

**Original remediation (for the record):** define request/response models and use `response_model`:

- `EntryIn`, `GoalIn`, `ParseRequest`, `RecipeRequest`, `ImageRequest`
- `JournalDocument`, `JournalEntry`, `ParseResponse`, `RecipeList`, `ApiError`
- Length/number constraints via `Annotated[..., Field(max_length=…)]` (replaces manual `isinstance`
  checks in `app/web/routers/ai.py` and parts of `app/web/dependencies.py`).
- Keep the current `{"error": "..."}` envelope through the existing exception handlers.

Payoff: working `/docs`, one typed contract shared by Python and JS, less validation code.

---

### 5. Hand-rolled `.env` configuration

**Severity:** low–medium.

`load_env()` (`app/config.py:42-66`) is a bespoke parser with legacy aliases (`OPENROUTER_TOKEN`,
`OPEN_ROUTER_API_KEY`) and a string allowlist (`ENV_KEYS`). The result is cached in `app.state.env`
and reloaded by comparing file mtimes on every request (`app/web/dependencies.py:66-75`). Tests have
to pin `env_mtime` to stop the real `.env` leaking in (`tests/test_server_api.py:47-48`).

**Remediation:** `pydantic-settings` (already transitively present) for a typed `Settings` object.
Make reload explicit (or keep the mtime check inside the settings provider) rather than mutating
`app.state` from request handlers. This also makes tests instantiate settings directly instead of
patching global state.

---

### 6. Blocking `urllib` calls inside a threadpool — *scaling and cancellation*

**Severity:** medium for local use; high if image generation is enabled.

All routes are sync `def`, so FastAPI runs them in the AnyIO threadpool (40 tokens by default).
That hides the blocking I/O, but:

- A 240 s image request holds a thread; three recipe cards hold three.
- `urllib.request` (`app/services/llm.py:68-74`) pays a new connection per call — no reuse.
- No retry/backoff on 429/5xx; the only retry is image generation, with a blocking
  `time.sleep(1)` (`app/services/images.py:44-46`).
- No cancellation: when the browser aborts, the server keeps calling the provider.
- No streaming.

**Remediation:** `httpx` (already a dev dependency) with a shared `AsyncClient` created in the
`lifespan`; convert the AI and image routes to `async def`; cap concurrency with an
`asyncio.Semaphore` (1 for image generation, 2–4 for LLM calls). The `openai` SDK is an alternative
if you want retries and typed responses; it still targets Ollama/llama.cpp/LM Studio because they
are OpenAI-compatible.

---

### 7. Recipe images are base64 inside JSON, and never cached

**Severity:** medium.

`/api/recipe-image` returns `{"image": "data:image/png;base64,…"}` with a limit of 8 MB
(`app/services/images.py:62-71`, `app/web/routers/images.py:71`). The response goes through
`json_response`, which sets `Cache-Control: no-store` (`app/web/http.py:10-20`). Consequences:

- ~33% payload inflation on a multi-megabyte response.
- No browser or proxy caching; the same recipe regenerates the image on every render.
- A 240 s GPU job is pinned to a single HTTP request.
- Base64 decoding happens in the client on the main thread for each card.

**Remediation:**

- Write the PNG once to a content-addressed file (hash of prompt + dimensions + steps) and return a
  URL.
- Serve generated images with `Cache-Control: public, max-age=31536000, immutable`.
- For long jobs, return a job id and poll (or use SSE) instead of holding the request open.
- Add an in-memory/disk cache keyed by the prompt so re-renders are free.

---

### 8. Timeouts are configured in three places and disagree

**Severity:** medium — produces confusing, intermittent failures.

The client, the server, and the legacy page each pick their own numbers (table in Issue 1). Concrete
bug: a local provider gets 180 s (`app/config.py:90`) but Compose aborts parse at 45 s
(`web/js/nutriparse.js:9`). Cook has a literal client/server race (180 s vs 180 s). Images have no
client timeout on Compose.

**Remediation:** expose the effective timeouts from the server (e.g. `GET /api/config` returning
`{provider, parse_timeout_ms, cook_timeout_ms, image_timeout_ms}`) and have every client read them.
One value, one place. This also makes the values visible in the request-details panel.

---

### 9. Validation is duplicated across layers, and plausibility is unchecked

**Severity:** medium.

- Store rules (`normalize_entry`, `app/journal/store.py:72-112`) are mirrored in
  `web/js/journal-client.js` (`asRow`, `isMovable`) and in `web/js/food-journal.js`.
- Totals are computed in Python (`app/services/nutrition.py:99-102`) and again in JS for live editing.
  Both are necessary, but nothing keeps them aligned.
- `number_field` only checks finite and non-negative (`app/services/llm.py:128-136`). A roti at
  9,000 kcal passes. The eval's known failure modes (energy-dense food, portion counts) are not
  turned into validation failures.

**Remediation:**

- Generate the browser's API client/types from the OpenAPI schema (from Issue 4) so the contract has
  one source of truth.
- Add cross-field plausibility checks in the service layer: Atwater sanity
  (`|kcal − (4P + 4C + 9F)|` within a tolerance), per-item kcal ceiling, and portion-count guards.
  Fail closed with a typed error the UI can show.
- Keep the eval harness as the acceptance test for these thresholds.

---

### 10. No lockfile, lint, type-check, CI, or committed frontend tests

**Severity:** medium — this is what lets the other issues regress.

- `requirements.txt` uses `>=,<` ranges only; `requirements-dev.txt` adds just `httpx`.
- No `pyproject.toml`, no pinned transitive dependencies, no hashes.
- No `ruff`, `mypy`/`pyright`, or ESLint configuration.
- No CI. The README says the browser surfaces are "exercised with headless-browser runs … outside
  the repo" — that is a bus-factor risk with no regression net.
- Evidence that drift is already happening: the installed set resolves to Starlette 1.9 / httpx
  0.28 and emits a `StarletteDeprecationWarning` about the TestClient transport.
- Tests monkeypatch module globals (`recipes.request_ai = …`,
  `tests/test_server_api.py:361-370`), which is brittle compared with dependency injection or a
  `monkeypatch` fixture.

**Remediation:**

- `pyproject.toml` with project metadata and `[tool.ruff]`, `[tool.pytest.ini_options]`,
  `[tool.mypy]`.
- `uv lock` (or `pip-compile --generate-hashes`) for reproducible installs.
- GitHub Actions on 3.10 / 3.12 / 3.14: `ruff check`, `mypy`, `pytest`, plus
  `python evals/run_parse_eval.py --check-fixtures` (offline).
- Commit a small Playwright suite: Compose → save → Journal round trip, and Cook with images off.
- Add coverage reporting; 84 fast tests is a good base to build on.

---

### 11. LLM-only nutrition has no deterministic grounding

**Severity:** high for product accuracy — the biggest lever, and not a web-stack issue.

The eval shows the errors are concentrated in energy-dense food and portion counts ("one piece" for
two samosas). Refactoring FastAPI cannot fix this. Asking a language model for calorie numbers is
the root cause.

**Remediation:** add a nutrition data source as a lookup step:

- USDA FoodData Central, Open Food Facts, or IFCT 2017.
- Let the LLM do only parsing, item matching, and portion inference; take numbers from the dataset.
- Re-point the eval at "correct item → correct DB row → right portion" instead of grading raw
  guesses. The harness becomes a retrieval/portion benchmark, which is what actually matters.

This is a larger change and should follow the low-risk fixes below, but it is the one that will
most improve the product.

---

### 12. Localhost security and operations gaps

**Severity:** low today; high the moment the app leaves `localhost`.

- No authentication, and `HOST` is a module constant (`app/config.py:12`). Nothing prevents a future
  `0.0.0.0` bind with an open journal and an open LLM proxy.
- HTML responses have no CSP, `frame-ancestors`/`X-Frame-Options`, or `Referrer-Policy`; only JSON
  gets `X-Content-Type-Options` (`app/web/http.py:10-20`). Model-generated recipe text is rendered
  in the DOM; `innerHTML` is currently limited to static markup (`spinner`, `&times;`) but a CSP
  would enforce that.
- `require_same_origin` treats a missing `Origin` as allowed (`app/web/dependencies.py:54-63`).
  Correct for non-browser clients, but combined with no auth any local process can write.
- No HTTP access log, and request ids are not returned to the client, so a 502 cannot be correlated
  from the UI to `logs/llm.log`.

**Remediation:**

- Add security-header middleware for HTML responses (CSP, `frame-ancestors 'none'`,
  `Referrer-Policy: no-referrer`).
- Add an explicit startup guard: if `HOST` is not loopback and no auth token is configured, refuse
  to start (or require `NUTRIPARSE_ALLOW_REMOTE=1`).
- Add request-id middleware; log method/path/status/duration and return the id in error bodies.
- If remote use is ever intended, add a bearer token or basic auth in front of the journal and AI
  routes.

---

## What not to change

- **Do not add a SPA framework or bundler** to solve Issues 2 and 9. ES modules + JSDoc + generated
  types get most of the safety at a fraction of the cost.
- **Do not add Redis/Celery** for a single user. If images need backgrounding, FastAPI
  `BackgroundTasks` plus a SQLite job row is enough.
- **Do not replace FastAPI/Uvicorn.** They are the right size for this app.

---

## Prioritized plan

| Order | Change | Effort | Why |
| --- | --- | --- | --- |
| 1 | `pyproject.toml` + ruff + mypy + lockfile + CI; commit Playwright smoke tests | M | Stops regressions while everything else moves |
| 2 | One source of truth for timeouts via `/api/config` | S | Fixes real user-visible failures (Issue 8) |
| 3 | Native ES modules + JSDoc/`tsc --noEmit` | M | Removes global/load-order fragility |
| 4 | `httpx` async client + semaphore; file-based image cache | M | Fixes thread exhaustion, cancellation, and payload size |
| 5 | Deterministic nutrition lookup behind the LLM; tighten eval | L | Largest accuracy gain |
| — | ~~Pydantic request/response models; working `/docs`~~ | — | Done |
| — | ~~Cross-process write lock for `data.json`~~ | — | Done (file lock; SQLite optional later) |

Issue 1 (front-end consolidation) is deliberately absent: it is blocked on choosing the surviving
frontend.

---

## Open decisions

1. **Surviving frontend:** Compose page vs Food Journal. Until decided, no consolidation work is
   proposed, and `food-journal.js` should be treated as frozen.
2. **Storage target:** the file lock closed the immediate hole; SQLite (WAL) remains the option if
   row-level CRUD or true transactions are wanted. Postgres only if multi-user is a real near-term
   goal.
3. **Nutrition source:** USDA FoodData Central (broad, US-centric), Open Food Facts (barcode/packaged
   foods), or IFCT 2017 (Indian foods, matches the app's example meals). A hybrid — IFCT for home
   cooking, USDA/Open Food Facts for branded items — is likely best given the fixtures.
