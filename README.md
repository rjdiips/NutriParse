# NutriParse

**LLM Nutrition & Recipe Service**

Turn free text about food into structured, validated nutrition data. A prompt-first web app with optional AI estimation and recipe generation from OpenRouter or any local OpenAI-compatible model.

<p align="center">
  <img src="screenshots/compose-estimate.png" alt="NutriParse Compose view: the meal '2 rotis, dal, and a glass of lassi' parsed into three editable rows — Roti, Dal and Lassi — with calories, protein, carbs and fat, totalling 470 kcal">
</p>

<p align="center"><sub><b>Compose → Estimate.</b> One line in, one editable row per food out, totals recomputed from the rows you can see.</sub></p>

Jump to: [Features](#features) · [Tech stack](#tech-stack) · [Configuration](#configuration) · [Web interface](#web-interface) · [Local models](#local-models-no-cloud-calls) · [Tests](#tests) · [Model evaluation](#model-evaluation) · [File layout](#file-layout)

## Features

- **Compose** — describe a meal in one line and get one editable row per food, with server-recomputed totals and the full call detail behind the result (`/api/parse`)
- **Cook** — list ingredients and get three recipe ideas with per-serving macros and optional local images (`/api/leftover-alchemist`); any idea can be seeded into the estimate table for review
- **Journal** — today's calories against your goal, history grouped by day with per-day totals, search, per-entry delete, and an editable daily goal
- **Manual entry** — add a row by hand when you already know the numbers, or when the model is unreachable
- Every parsed name and number stays editable, and totals are recomputed from the rows you can see
- Failures surface as typed messages with a retry; `?sample=1` previews a resolved result without a model call
- One journal store: the Compose view and the Food Journal both read and write the same `data.json` through `app/journal/store.py`
- A committed evaluation harness scores `/api/parse` against reference calorie ranges, so claims about the model's accuracy carry a table and a date

## Tech stack

| Layer | What NutriParse uses |
| --- | --- |
| Language | Python 3.10+ for the API, store, and evaluation harness; vanilla JavaScript in the browser |
| Backend | FastAPI on Uvicorn, with Starlette and Pydantic underneath; one shared `httpx` async client for provider calls |
| Frontend | HTML5, CSS, and plain JavaScript — no framework, bundler, or build step |
| API surface | REST/JSON endpoints for parsing, cooking, recipe images, and journal CRUD |
| LLM providers | OpenRouter by default; any OpenAI-compatible endpoint for local inference — Ollama (default), llama.cpp, LM Studio, vLLM |
| Image generation | stable-diffusion.cpp CUDA build serving SDXL-Turbo through an AUTOMATIC1111-compatible `/sdapi/v1/txt2img` API |
| Persistence | One local JSON document (`data.json`) with validation, atomic `os.replace` writes, and a cross-process lock file — no database |
| Configuration | One typed `pydantic-settings` object for `.env` and the process environment, with process variables taking priority and mtime-based live reload |
| Testing | Python `unittest` for the store and FastAPI routes, plus Node's built-in runner for the browser config loader and TypeScript's `checkJs` mode for the browser scripts; `httpx` provides the `TestClient` transport |
| Evaluation | A committed harness in `evals/` with fixed meal fixtures, reference calorie ranges, and Markdown/JSON results |
| Logging | Python `logging` with a 2 MB rotating handler at `logs/llm.log`, keeping five backups |
| Tooling | pip with `requirements.txt` / `requirements-dev.txt`; npm with a committed lockfile for the dev-only JavaScript type check; Windows batch scripts for the optional CUDA image service |

## Requirements

- Python 3.10+
- FastAPI, Uvicorn, and httpx
- Node.js 18+ and npm, only for the optional JavaScript type check

Install the backend dependencies once:

```powershell
python -m pip install -r requirements.txt
```

The journal store needs nothing beyond the standard library. Recipe images are optional and use a separate local service (see below). The Node packages are development tooling only: neither the server nor the pages load them at runtime.

## Configuration

Runtime settings live in `.env` (start from `.env.example`) and are parsed into one typed `app.config.Settings` object. Process environment variables override the file for every setting, including the image options and the legacy `OPENROUTER_TOKEN` / `OPEN_ROUTER_API_KEY` key aliases. The server compares the file's mtime on each request, so an edit applies to the next request without a restart. Invalid values — an unknown provider, a non-numeric image size, an out-of-range dimension — stop startup with a message naming the setting. `LLM_TIMEOUT` is the exception: a missing, invalid, or non-positive value falls back to the provider default (30 seconds for parsing and 45 for recipes on OpenRouter, 180 for a local model).

Both pages read the effective parse, cook, and image timeouts from `GET /api/config` at startup; the same endpoint also reports the active provider and model. Each client waits 10 seconds longer than the server's value, so a slow provider gets the server's error rather than a premature client abort, and the request-details panel shows the timeout it used. If the config call fails, AI calls fall back to a 300-second safety net and the page says so; journal reads and writes are unaffected. `LOCAL_IMAGE_TIMEOUT` overrides the image service's 240-second per-call limit, and the reported image timeout follows it.

Model and image calls share one `httpx` async client, created when the server starts. At most three model calls and one image generation run at a time, so a slow image job cannot hold a model slot and concurrent Cook runs do not starve the rest of the app. A 429 or 5xx response is retried up to three total attempts with 0.5 s and then 1.5 s between them; any other 4xx is not retried. Closing the browser tab cancels the in-flight upstream call. Journal routes stay synchronous and use their own store lock.

## Usage

### Web interface

1. Start the backend server from the repository root:

```powershell
python -m app.main
```

That entry point prints the startup banner and a warning when no API key is configured, and it accepts `--demo`. To iterate on the backend with automatic reloads, run Uvicorn directly instead:

```powershell
python -m uvicorn app.main:app --reload --port 8100
```

The `uvicorn` form imports the module-level `app` directly, so it skips `main()` — and with it the banner, the missing-key warning, and the `--demo` flag. Bind with the command-line flags: Uvicorn does not read the `HOST`/`PORT` constants from `app/config.py`. The app still loads `.env` itself for journals, providers, and image settings.

2. Open http://localhost:8100 in your browser. The same app also serves interactive API documentation at http://localhost:8100/docs.

The app has two views, switched from the top bar.

**Compose** is the prompt-first surface, with two intents sharing one input. **Estimate** turns a meal ("2 rotis, dal, and a glass of lassi") into one row per item; **Cook** turns an ingredient list into three recipe ideas with steps and per-serving macros. Every parsed name and number is editable, totals are summed server-side from the rows you can see, and **Request details** exposes the provider, model, latency, token counts, and the raw response JSON in both modes. Failures surface as typed messages with a retry, and images degrade to a labelled strip when the local service is off. **Add a row manually** seeds one blank editable row for numbers you already know; for that row the inspector reads *Pending save* and previews the payload the save will write, instead of implying a model call that never happened.

<p align="center">
  <img src="screenshots/cook-ideas.png" alt="NutriParse Cook view: the ingredients 'chai, chappati, dahi, ice-cream' turned into three recipe cards, each with a generated image, per-serving calories and macros, ingredient list and numbered steps">
</p>

<p align="center"><sub><b>Compose → Cook.</b> The other intent on the same surface: three ideas with per-serving macros and steps, plus the same call detail.</sub></p>

**Journal** is the read side of the same store: today's calories against your goal, protein/carbs/fat totals and entry count, an editable goal with presets, history grouped by day with per-day totals, a search box, and a per-entry delete.

<p align="center">
  <img src="screenshots/journal.png" alt="NutriParse Journal view: 1,925 of 2,200 kcal for today with protein, carbs and fat totals, an editable daily goal, and history grouped by day with per-day totals">
</p>

<p align="center"><sub><b>Journal.</b> Today against the goal, macros to the gram, and history grouped by day — reading the same store Compose writes to.</sub></p>

Add `?sample=1` or `?sample=cook` to preview either resolved Compose state without a model call, and `?view=journal` to open the Journal view directly.

### Demo data for screenshots

`scripts/seed_demo.py` writes a week of sample entries to `data.demo.json`, dated relative to today, so the Journal view has a populated today card and several days of history — including one day over the goal and one light day. Your real `data.json` is never read or written. The Journal screenshot above came from this demo file.

```powershell
python scripts/seed_demo.py
python -m app.main --demo
```

Open http://localhost:8100/?view=journal. `--demo` only changes which file the journal API serves; AI, Cook and images behave as usual. Re-run `scripts/seed_demo.py` whenever you want the sample dates to move up to the current day, and delete `data.demo.json` when you are done. Start the server without `--demo` to go back to your real journal.

### Where the journal lives

The server owns `data.json`; the browser keeps no copy of its own. Saving in Compose posts to the server, every mutation answers with the whole updated document, and both views render from that answer. `app/journal/store.py` holds the rules the API applies — validation, id assignment, atomic writes.

| Endpoint | Body | Returns |
| --- | --- | --- |
| `GET /api/journal` | — | the whole document |
| `POST /api/journal/entries` | `{"entries": [ … ]}` | the document including the new rows, each with a server-assigned id |
| `PUT /api/journal/entries/<id>` | `{"entries": [ … ]}` | the document with that row replaced; the first new row keeps the id |
| `DELETE /api/journal/entries/<id>` | — | the document without that row |
| `POST /api/journal/goal` | `{"calorie_goal": 2200}` | the document with the new goal |

Writes are validated before they touch the file and then swapped in atomically, so a crash mid-write cannot leave a half-written journal behind. A `data.json` that cannot be parsed is reported as an HTTP 500 rather than quietly replaced with a fresh one. Journal writes also check the request's `Origin` and refuse cross-site ones with 403; reads stay open because they change nothing.

Writers are serialised twice: a thread lock covers requests inside one server process, and a sidecar lock file (`data.json.lock`, created next to the journal and ignored by Git) covers separate processes — two Uvicorn workers, or a server and a script. A writer that cannot take the file lock within 10 seconds fails with HTTP 503 instead of overwriting another process's rows. Readers take no lock, because `os.replace` only ever exposes a complete document. The lock file stays behind with a single byte in it; delete it while no server is running if you want a clean directory.

Entries saved by an earlier version of the web app, in `localStorage` under `ct_data`, are moved up once on the first page load: valid rows are posted to the server and removed from the browser, and any row the server would reject is left in the browser rather than dropped. The Food Journal is available at http://localhost:8100/food-journal.html and reads and writes the same store. One caveat worth stating: the migration assumes one tab is open, so two tabs loading at the same instant can each claim the same browser rows and you may see duplicates once.

### Local recipe images (NVIDIA CUDA)

Recipe images use an AUTOMATIC1111-compatible `/sdapi/v1/txt2img` endpoint. On an NVIDIA GPU, run `scripts/setup_image_generator.bat` once. It downloads the stable-diffusion.cpp CUDA build (about 900 MB including the CUDA runtime) and Stability AI's SDXL-Turbo checkpoint (6.9 GB). Then launch `scripts/start_image_generator.bat` before using Cook mode. The service binds to `127.0.0.1:7860`, uses the GPU, and produces 640×480 images in 6 steps, typically in a few seconds each on an 8 GB laptop GPU. First startup loads the checkpoint and can take 20–40 seconds.

Turbo checkpoints expect CFG 1 and few sampling steps; the start script passes both. It also enables `--offload-to-cpu` so model weights can move through system RAM instead of reserving nearly all GPU memory; this reduces peak VRAM use at the cost of some speed. Image size and steps are read from `.env` (`LOCAL_IMAGE_WIDTH`, `LOCAL_IMAGE_HEIGHT`, `LOCAL_IMAGE_STEPS`). If you replace SDXL-Turbo with a regular checkpoint such as SD 1.5, set `LOCAL_IMAGE_STEPS=20` in `.env` and adjust `--cfg-scale` in the start script. Binaries and model files live in `.image-tools/` and `models/`, both excluded by `.gitignore`.

The image service is optional: if it is stopped, recipe ideas still load without images. Set `LOCAL_IMAGE_GENERATION_ENABLED=false` in `.env` to disable image requests entirely, or override `LOCAL_IMAGE_API_URL` to use another address.

Generated PNGs are written once under a SHA-256 hash of the normalized prompt, width, height, and steps, and reused by later Cook runs for the same recipe and settings. `POST /api/recipe-image` answers with a small body — `{"image": "/api/recipe-image/<hash>.png", "cached": false}` — and the image route serves the PNG with `Cache-Control: public, max-age=31536000, immutable`, because a content hash never changes. Both Compose and the Food Journal render that URL. Files live in `image-cache/`, which is ignored by Git; there is no automatic eviction, so delete that directory while the server is stopped to clear the cache.

## AI suggestions setup

AI nutrition suggestions require an OpenRouter API key. The key is read by the backend from `.env` — never exposed to the browser or end user.

1. Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

2. Fill in `OPENROUTER_API_KEY` with your OpenRouter key. Optionally set `OPENROUTER_MODEL` (defaults to `openrouter/free`). To run without cloud calls, see "Local models" below. Recipe images do not use this key; they are generated locally by the image service.

3. Start the server with `python -m app.main` and compose a meal in the browser.

### Local models (no cloud calls)

Set `LLM_PROVIDER=local` and point `LLM_BASE_URL` at any server that speaks the OpenAI `/chat/completions` API. Nothing in the backend is tied to one runtime: llama.cpp, Ollama, LM Studio, vLLM, and hosted gateways all receive the same request, and the app reads `choices[0].message.content`.

```env
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3.5:4b
```

The URL above is Ollama's default; the alternatives are listed below. `LLM_MODEL` is the tag you pulled for Ollama; with llama.cpp keep it equal to `--alias`. Local servers usually need no key; set `LLM_API_KEY` only for a gateway that enforces one.

#### llama.cpp (alternative local setup)

`scripts/start_llm.bat` wraps the server command and serves `http://localhost:8080/v1`.

**1. Install llama.cpp.** The simplest route is the `llama` CLI installer, which also gives you `llama serve`:

```powershell
irm https://llama.app/install.ps1 | iex
```

Or download a Windows build from the [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases). On an NVIDIA GPU take `llama-<build>-bin-win-cuda-x64.zip` **and** the matching `cudart-<build>-bin-win-cuda-x64.zip`; on CPU-only machines take `llama-<build>-bin-win-cpu-x64.zip`. Extract so `llama-server.exe` lands at `.llm-tools\llama-server.exe` (or add it to `PATH`); `.llm-tools/` is gitignored. `scripts/start_llm.bat` uses the `llama` CLI when a llama.cpp build of it is on `PATH`, and otherwise falls back to `llama-server.exe`.

**2. Fetch a GGUF model.** Any instruct model that follows the prompt and emits JSON works. A `Q4_K_M` quant is the usual starting point — roughly 5–6 GB for a 9B model, and small enough for an 8 GB laptop GPU. Put the file under `models\<model-name>\` (or a shared `D:\models\<model-name>\`); GGUF embeds the tokenizer and chat template, so the one file is all the app needs.

```powershell
New-Item -ItemType Directory -Force models\qwen3.5-9b | Out-Null
curl.exe -L -o models\qwen3.5-9b\qwen3.5-9b-Q4_K_M.gguf `
  "https://huggingface.co/<org>/<repo>/resolve/main/<file>.gguf?download=true"
```

Replace the `<…>` placeholders with the repository and filename you chose. `scripts/start_llm.bat` looks for `models\qwen3.5-9b\*.gguf`, then `D:\models\qwen3.5-9b\*.gguf`, then any model in `models\`; it skips `mmproj` projectors. Set `LLM_MODEL_FILE` in `.env` (or the shell) to a full path to use a file somewhere else.

**3. Start the server.** Run `.\scripts\start_llm.bat`, or the same command by hand:

```powershell
llama serve -m models\qwen3.5-9b\qwen3.5-9b-Q4_K_M.gguf `
  --alias qwen3.5-9b -c 8192 -ngl 99 --host 127.0.0.1 --port 8080 `
  --jinja --reasoning off
```

If you installed from a release zip instead of the CLI, run `.llm-tools\llama-server.exe` with the same flags. `--alias` is the name the UI reports for the model. `-ngl 99` offloads every layer to the GPU; drop it on a CPU-only build, or lower the number when VRAM is tight. `--reasoning off` matters with thinking models: without it Qwen3.5 spends thousands of tokens before answering, which turned a 7-second parse into a 100-second one in testing. Leave the server running in its own terminal.

**4. Point `.env` at it.**

```env
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:8080/v1
LLM_MODEL=qwen3.5-9b
LLM_REASONING_EFFORT=
```

`LLM_REASONING_EFFORT` is empty on purpose here: llama.cpp does not read it, so there is no reason to send it.

**5. Verify.** Check that the server answers, then start the app:

```powershell
curl http://localhost:8080/v1/models
python -m app.main
```

Open http://localhost:8100/, compose a meal, and check the request-details panel. A healthy call shows provider `local`, your alias, a latency in seconds, token counts, and the parsed items. `/api/parse` is what the Compose surface and the Food Journal's Log a meal tab use, so both exercise the same path.

#### Ollama

```powershell
ollama pull qwen3.5:9b
ollama serve
```

```env
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3.5:9b
```

Ollama serves the same OpenAI-compatible path on port 11434 and keeps the model loaded between calls. Model names keep their `name:tag` form. If an older build rejects `response_format`, set `LLM_JSON_MODE=false`.

#### LM Studio, vLLM, and other servers

| Server | Base URL |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp | `http://localhost:8080/v1` |
| vLLM | `http://localhost:8000/v1` |

Load the model in the server, then set `LLM_BASE_URL`. Set `LLM_MODEL` to the ID the server reports at `/v1/models` when it routes by name (vLLM, LM Studio); with a single-model llama.cpp server the value is only a label. Hosted or self-hosted gateways work the same way — use their `https://…/v1` URL and `LLM_API_KEY` if they require one.

#### Tuning local inference

| Symptom | Lever |
| --- | --- |
| First call is slow, later ones are fast | Expected — the first request loads the model. Watch warm latency in the inspector. |
| `context overflow` or truncated JSON | Raise the context size (`-c` on llama.cpp; the context setting in LM Studio or Ollama). 4096 covers these prompts; 8192 leaves headroom. |
| Out of VRAM | llama.cpp: lower `-ngl`, lower `-c`, add `--cache-type-k q8_0 --cache-type-v q8_0`, or use a smaller quant. Ollama: a smaller quant or `num_gpu` in a Modelfile. |
| A thinking model returns empty content | Stop reasoning at the server: `--reasoning off` (or `-rea off`) on current builds, `--reasoning-budget 0` if yours only has the budget flag, `--chat-template-kwargs '{"enable_thinking":false}'` for Qwen-style templates, or `LLM_REASONING_EFFORT=none` on servers that honour it. |
| Parsing takes ~100 s and reports thousands of completion tokens | Thinking is still on. Restart the server with `--reasoning off`; the same meal then parses in ~7 s and ~200 tokens. |
| HTTP 400 mentioning `response_format` | Set `LLM_JSON_MODE=false`; the prompt still asks for JSON and fenced output is stripped. |
| HTTP 404 from the model call | `LLM_BASE_URL` is missing `/v1`. |
| HTTP 502 — “Could not reach Local model” | The server is not running, or the port in `.env` does not match the one the server bound. |

Local providers do not need an API key. `LLM_TIMEOUT` overrides the request timeout (defaults: 30 for nutrition and 45 for recipes on OpenRouter, 180 for local models — generous because a cold load can take a while). Recipe images are unaffected and still use the local image service. Because `evals/results.json` is a snapshot of one model on one date, re-run `python evals/run_parse_eval.py` after changing the model or quant.

<details>
<summary><b>What a local call looks like in the inspector</b> — click to open</summary>

<p align="center">
  <img src="screenshots/request-details.png" alt="Request details panel: provider local, model qwen3.5:9b, 9,283 ms latency, 154 prompt tokens, 196 completion tokens, three items returned, and the raw response JSON">
</p>

Every Estimate and Cook result carries this panel: which provider answered, the model, the latency, both token counts, and the raw JSON. Nothing here is inferred from the UI state — it is the call as it happened.

</details>

Text-model requests are recorded in `logs/llm.log`; image-generation requests
are recorded separately in `logs/image_generation.log`. Entries include a
request ID, model or image dimensions and steps, duration, and outcome. A failed
model call also records the upstream status and a truncated, sanitised excerpt
of the provider's error response so a 502 can be diagnosed; that excerpt can
still contain fragments of the prompt. Prompts are not logged on the success
path, and image data and API credentials are never logged. Each log rotates at
2 MB, keeping up to five older files.

## Tests

The journal store has a stdlib suite covering validation, portions, atomic writes, entry updates, legacy numeric ids, corrupt files, and concurrent writers in both threads and separate processes. The FastAPI surface has a second suite covering the static allowlist, the journal round trip and update path, body validation, same-origin checks on writes, the OpenAPI request/response schemas, the `/api/config` timeouts and headers, and the rules that trim and validate model output. The async transport is tested with a stubbed `httpx.MockTransport` for 429/5xx retries, the stated backoff, no retry on other 4xx, the three-model and one-image concurrency caps, and disconnect cancellation. The recipe-image cache is tested for its first write, repeat hits, dimension-aware hashes, immutable response headers, and unknown hashes. The browser config loader's client-side waits and 300-second fallback run under Node's built-in test runner; that test skips only when Node is not installed.

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
```

Both browser surfaces are also exercised with headless-browser runs of the Compose, Journal and Cook views during development; those live outside the repo.

### JavaScript type check

The browser code has no build step, so a misspelled import or shared global is a runtime error rather than a build error. TypeScript's `checkJs` mode closes that gap without adding a bundler.

```powershell
npm ci
npm run check:js
```

`npm ci` installs the committed `package-lock.json`. Compose loads one native ES-module graph rooted at `web/js/nutriparse/boot.js`; Food Journal still loads classic scripts for now. The check runs each page as its own program, because the two pages never share a module graph. `web/js/shared-globals.d.ts` declares the names the classic Food Journal scripts share across files — `Config`, `JournalStore`, and `window.__toastTid` — along with the document types they exchange, so the check can tell a real typo from a cross-file reference. The Node packages are dev-only; the Python runtime and the served pages are unaffected. `python -m unittest discover -s tests` runs the check when `npm ci` has installed the tooling, and skips it otherwise.

`tests/test_assets.py` also resolves every relative ES-module import to a real file, since the browser has no bundler to fail on a broken path. The 10 November 2026 smoke check of Compose used a headless Edge run against a temporary journal: sample Estimate and Cook views, manual row save, Journal view, search match and no-match states, goal editing, entry deletion, and a clean browser console. Food Journal was checked in the same run and loaded through its classic client unchanged.

## Model evaluation

`evals/` holds a committed harness that scores `/api/parse` against fixed meals with reference calorie ranges. It exists because "the model under-counts" is an anecdote until it is measured, and because a prompt change needs something to compare against.

```powershell
python -m app.main                  # in one terminal
python evals/run_parse_eval.py      # in another
python evals/run_parse_eval.py --check-fixtures   # offline: validate the cases only
```

Thirteen cases, twelve with a calorie reference and one non-food refusal check. Each case carries per-item ranges and a `basis` naming the composition data behind them, and rows that a model splits are summed before comparison, so a correct split is not punished. The runner reports within-range rate, mean signed error (the bias), mean absolute error, item detection, refusals, latency and tokens, and writes `evals/results.md` plus the raw `evals/results.json`. See `evals/README.md` for the method and its limits.

The committed run is a snapshot of the local model (`qwen3.5:9b`, 21 October 2026): 10 of 12 scored meals landed inside their reference range, with a mean signed error of −4.4%. The aggregate hides the useful part, though. The errors are concentrated in energy-dense food — two slices of pepperoni pizza at 300 kcal against 450–700, two samosas and a chai at 240 against 310–530 — and a meal can total in range while an item inside it is wrong: "2 rotis, dal, and a lassi" lands at 470 kcal against 420–650, with the roti row at 140 kcal against 180–260. The same run also returned `one piece` for "two samosas", which is a portion bug rather than a calorie-estimate bug. Those per-item rows are the reason the harness exists.

## File layout

The application is a package (`app/`) with the browser app under `web/`. Each
folder owns one concern, so a change to recipes does not sit in the same file as
a change to static routes.

```text
app/
  config.py            paths, request limits, typed settings, live .env reload
  logging_config.py    rotating model and image logs
  main.py              FastAPI factory, router wiring, server entry point
  journal/store.py     shared journal: validation, atomic writes, cross-process lock
  services/            llm.py, nutrition.py, recipes.py, images.py, transport.py
  web/
    dependencies.py    JSON body rules, same-origin guard, journal/LLM helpers
    http.py            one JSON response shape, API headers, exception handlers
    schemas.py         Pydantic request/response models behind /docs
    static.py          /assets mount plus explicit page and legacy asset routes
    routers/           health.py, runtime.py, journal.py, ai.py, images.py
web/
  pages/               nutriparse.html, food-journal.html
  css/nutriparse/      base, compose, results, recipes, journal
  css/food-journal/    base, layout, compose, journal, responsive
  js/nutriparse.js     Compose module: DOM refs, state, copy, mode and view switches
  js/nutriparse/       boot entry plus request, estimate, recipes, inspector, journal, samples
  js/food-journal.js   the second page's behaviour (classic script)
  js/journal-store.js  shared journal API as ES modules; Compose imports it
  js/journal-client.js classic-script shim that forwards window.JournalStore to journal-store.js
  js/config-client.js  server-driven AI timeouts shared by both pages
  js/config-module.js  ES-module interface to config-client.js
  js/shared-globals.d.ts  declarations for the globals the classic scripts share
  assets/              favicon files
scripts/
  seed_demo.py         writes data.demo.json for screenshots
  setup_image_generator.bat / start_image_generator.bat  CUDA image service
  start_llm.bat        starts a local llama.cpp server with the expected settings
tests/                 store, asset-link, settings, FastAPI, browser config-loader, and JS type-check tests
evals/                 parse evaluation harness, fixtures, and committed results
screenshots/           the screenshots used in this README
requirements.txt       backend dependencies (FastAPI, Uvicorn, pydantic-settings, httpx)
requirements-dev.txt   installs the runtime requirements for the test suite
package.json           dev-only Node manifest for the JavaScript type check
package-lock.json      committed lockfile for the type-check toolchain
tsconfig.json          the Compose page's script graph
tsconfig.base.json     shared TypeScript options for checking JavaScript
tsconfig.food-journal.json  the Food Journal's script graph
data.json              the journal, shared by the Compose view and the Food Journal (created on first write; ignored by Git)
image-cache/           generated recipe PNGs keyed by content hash (ignored by Git; delete to clear)
.env                   your OpenRouter API key (create from `.env.example`; do not commit)
.image-tools/, models/ downloaded image runtime and models (ignored by Git)
.llm-tools/            downloaded llama.cpp runtime (ignored by Git)
```

The public asset URLs are stable: pages still load at `/` and
`/food-journal.html`, and the older `/nutriparse.js`, `/nutriparse.css`,
`/journal-client.js`, and `/food-journal.css` URLs remain as compatibility
aliases. New files are served from `/assets/`, which mounts only `web/`; source,
`.env`, and journals stay outside the reachable tree.
