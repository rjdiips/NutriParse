# NutriParse

**LLM Nutrition & Recipe Service**

Turn free text about food into structured, validated nutrition data. A prompt-first web app and a command-line tool, with optional AI estimation and recipe generation from OpenRouter or any local OpenAI-compatible model.

<p align="center">
  <img src="screenshots/compose-estimate.png" alt="NutriParse Compose view: the meal '2 rotis, dal, and a glass of lassi' parsed into three editable rows — Roti, Dal and Lassi — with calories, protein, carbs and fat, totalling 470 kcal">
</p>

<p align="center"><sub><b>Compose → Estimate.</b> One line in, one editable row per food out, totals recomputed from the rows you can see.</sub></p>

Jump to: [Features](#features) · [Tech stack](#tech-stack) · [Web interface](#web-interface) · [Local models](#local-models-no-cloud-calls) · [Tests](#tests) · [Model evaluation](#model-evaluation) · [File layout](#file-layout)

## Features

- **Compose** — describe a meal in one line and get one editable row per food, with server-recomputed totals and the full call detail behind the result (`/api/parse`)
- **Cook** — list ingredients and get three recipe ideas with per-serving macros and optional local images (`/api/leftover-alchemist`); any idea can be seeded into the estimate table for review
- **Journal** — today's calories against your goal, history grouped by day with per-day totals, search, per-entry delete, and an editable daily goal
- **Manual entry** — add a row by hand when you already know the numbers, or when the model is unreachable
- Every parsed name and number stays editable, and totals are recomputed from the rows you can see
- Failures surface as typed messages with a retry; `?sample=1` previews a resolved result without a model call
- Seven-day daily summary with progress toward the goal in the CLI
- One journal store: the web app, the CLI, and the retained legacy journal all read and write the same `data.json` through `store.py`
- A committed evaluation harness scores `/api/parse` against reference calorie ranges, so claims about the model's accuracy carry a table and a date

## Tech stack

| Layer | What NutriParse uses |
| --- | --- |
| Language | Python 3.10+ for the API, CLI, store, and evaluation harness; vanilla JavaScript in the browser |
| Backend | FastAPI on Uvicorn, with Starlette and Pydantic underneath |
| Frontend | HTML5, CSS, and plain JavaScript — no framework, bundler, or build step |
| API surface | REST/JSON endpoints for parsing, cooking, suggestions, recipe images, and journal CRUD |
| LLM providers | OpenRouter by default; any OpenAI-compatible endpoint, including Ollama, LM Studio, and llama.cpp |
| Image generation | stable-diffusion.cpp CUDA build serving SDXL-Turbo through an AUTOMATIC1111-compatible `/sdapi/v1/txt2img` API |
| Persistence | One local JSON document (`data.json`) with validation, atomic `os.replace` writes, and a process-level lock — no database |
| Configuration | `.env` read by the backend, with process environment variables taking priority |
| Testing | Python `unittest` for the store and FastAPI routes; `httpx` provides the `TestClient` transport |
| Evaluation | A committed harness in `evals/` with fixed meal fixtures, reference calorie ranges, and Markdown/JSON results |
| Logging | Python `logging` with a 2 MB rotating handler at `logs/llm.log`, keeping five backups |
| Tooling | pip with `requirements.txt` / `requirements-dev.txt`; Windows batch scripts for the optional CUDA image service |

## Requirements

- Python 3.10+
- FastAPI and Uvicorn

Install the backend dependencies once:

```powershell
python -m pip install -r requirements.txt
```

The journal store and CLI need nothing beyond the standard library. Recipe images are optional and use a separate local service (see below).

## Usage

### Command-line interface

```powershell
python nutriparse.py
```

Follow the on-screen menu to track your intake. The CLI and the web app share one journal (`data.json`, in this folder), so an entry saved in the browser shows up here and the other way round. Entries are read fresh on every command rather than held in memory, which is what makes that true. Option 6 (Suggest nutrition with AI) calls the backend server at `http://localhost:8100`, so start `server.py` first if you want to use it.

### Web interface

1. Start the backend server:

```powershell
python server.py
```

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

<p align="center"><sub><b>Journal.</b> Today against the goal, macros to the gram, and history grouped by day — reading the same store the CLI writes to.</sub></p>

Add `?sample=1` or `?sample=cook` to preview either resolved Compose state without a model call, and `?view=journal` to open the Journal view directly.

### Demo data for screenshots

`seed_demo.py` writes a week of sample entries to `data.demo.json`, dated relative to today, so the Journal view has a populated today card and several days of history — including one day over the goal and one light day. Your real `data.json` is never read or written. The Journal screenshot above came from this demo file.

```powershell
python seed_demo.py
python server.py --demo
```

Open http://localhost:8100/?view=journal. `server.py --demo` only changes which file the journal API serves; AI, Cook and images behave as usual. Re-run `seed_demo.py` whenever you want the sample dates to move up to the current day, and delete `data.demo.json` when you are done. Start `server.py` without `--demo` to go back to your real journal.

### Where the journal lives

The server owns `data.json`; the browser keeps no copy of its own. Saving in Compose posts to the server, every mutation answers with the whole updated document, and both views render from that answer. `store.py` holds the rules both front ends share — validation, id assignment, atomic writes — and the CLI calls it directly because it runs on the same machine as the file.

| Endpoint | Body | Returns |
| --- | --- | --- |
| `GET /api/journal` | — | the whole document |
| `POST /api/journal/entries` | `{"entries": [ … ]}` | the document including the new rows, each with a server-assigned id |
| `DELETE /api/journal/entries/<id>` | — | the document without that row |
| `POST /api/journal/goal` | `{"calorie_goal": 2200}` | the document with the new goal |

Writes are validated before they touch the file and then swapped in atomically, so a crash mid-write cannot leave a half-written journal behind. A `data.json` that cannot be parsed is reported — HTTP 500 from the API, exit 1 from the CLI — rather than quietly replaced with a fresh one. Journal writes also check the request's `Origin` and refuse cross-site ones with 403; reads stay open because they change nothing.

Entries saved by an earlier version of the web app, in `localStorage` under `ct_data`, are moved up once on the first page load: valid rows are posted to the server and removed from the browser, and any row the server would reject is left in the browser rather than dropped. The earlier editorial journal is retained as a working backup at http://localhost:8100/journal-legacy.html and reads and writes the same store, so the old layout is still there if you want it. Two caveats worth stating: the migration assumes one tab is open, so two tabs loading at the same instant can each claim the same browser rows and you may see duplicates once; and the write lock is held per process, so a CLI save racing a browser save is last-write-wins rather than a transaction.

`/api/suggest` (single-food estimation, once behind the journal's "Suggest with AI" button) is still served and is still used by CLI option 6. The Compose surface uses `/api/parse` instead.

### Local recipe images (NVIDIA CUDA)

Recipe images use an AUTOMATIC1111-compatible `/sdapi/v1/txt2img` endpoint. On an NVIDIA GPU, run `setup_image_generator.bat` once. It downloads the stable-diffusion.cpp CUDA build (about 900 MB including the CUDA runtime) and Stability AI's SDXL-Turbo checkpoint (6.9 GB). Then launch `start_image_generator.bat` before using Cook mode. The service binds to `127.0.0.1:7860`, uses the GPU, and produces 512×512 images in 6 steps, typically in a few seconds each on an 8 GB laptop GPU. First startup loads the checkpoint and can take 20–40 seconds.

Turbo checkpoints expect CFG 1 and few sampling steps; the start script passes both. Image size and steps are read from `.env` (`LOCAL_IMAGE_WIDTH`, `LOCAL_IMAGE_HEIGHT`, `LOCAL_IMAGE_STEPS`). If you replace SDXL-Turbo with a regular checkpoint such as SD 1.5, set `LOCAL_IMAGE_STEPS=20` in `.env` and adjust `--cfg-scale` in the start script. Binaries and model files live in `.image-tools/` and `models/`, both excluded by `.gitignore`.

The image service is optional: if it is stopped, recipe ideas still load without images. Set `LOCAL_IMAGE_GENERATION_ENABLED=false` in `.env` to disable image requests entirely, or override `LOCAL_IMAGE_API_URL` to use another address.

## AI suggestions setup

AI nutrition suggestions require an OpenRouter API key. The key is read by the backend from `.env` — never exposed to the browser or end user.

1. Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

2. Fill in `OPENROUTER_API_KEY` with your OpenRouter key. Optionally set `OPENROUTER_MODEL` (defaults to `openrouter/free`). To run without cloud calls, see "Local models" below. Recipe images do not use this key; they are generated locally by the image service.

3. Start `server.py` and compose a meal in the browser, or use CLI option 6.

### Local models (no cloud calls)

Set `LLM_PROVIDER=local` to send AI requests to any OpenAI-compatible server instead of OpenRouter:

```env
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3.5:9b
```

`LLM_BASE_URL` works with Ollama (`11434`), LM Studio (`1234`), and llama.cpp (`8080`). Local providers do not need an API key. `LLM_TIMEOUT` optionally overrides the request timeout in seconds (defaults: 30 for nutrition and 45 for recipes on OpenRouter, 180 for local models). Local requests disable thinking via `LLM_REASONING_EFFORT=none` and enable JSON mode through `response_format`, which keeps replies fast; set `LLM_REASONING_EFFORT=` empty or `LLM_JSON_MODE=false` if your server does not support them. Recipe images are unaffected and still use the local image service.

<details>
<summary><b>What a local call looks like in the inspector</b> — click to open</summary>

<p align="center">
  <img src="screenshots/request-details.png" alt="Request details panel: provider local, model qwen3.5:9b, 9,283 ms latency, 154 prompt tokens, 196 completion tokens, three items returned, and the raw response JSON">
</p>

Every Estimate and Cook result carries this panel: which provider answered, the model, the latency, both token counts, and the raw JSON. Nothing here is inferred from the UI state — it is the call as it happened.

</details>

Each LLM request is recorded in `logs/llm.log`, including its request ID, model,
food and portion, duration, and success or failure. Logs rotate automatically
after reaching 2 MB, keeping up to five older files. API credentials and raw
provider payloads are not logged.

## Tests

The journal store has a stdlib suite covering validation, atomic writes, legacy numeric ids, corrupt files, and concurrent writers. The FastAPI surface has a second suite covering the route allowlist, the journal round trip, body validation, and the same-origin check on writes:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
```

Both front ends are also exercised with headless-browser runs of the Compose, Journal and Cook surfaces during development; those live outside the repo.

## Model evaluation

`evals/` holds a committed harness that scores `/api/parse` against fixed meals with reference calorie ranges. It exists because "the model under-counts" is an anecdote until it is measured, and because a prompt change needs something to compare against.

```powershell
python server.py                    # in one terminal
python evals/run_parse_eval.py      # in another
python evals/run_parse_eval.py --check-fixtures   # offline: validate the cases only
```

Thirteen cases, twelve with a calorie reference and one non-food refusal check. Each case carries per-item ranges and a `basis` naming the composition data behind them, and rows that a model splits are summed before comparison, so a correct split is not punished. The runner reports within-range rate, mean signed error (the bias), mean absolute error, item detection, refusals, latency and tokens, and writes `evals/results.md` plus the raw `evals/results.json`. See `evals/README.md` for the method and its limits.

The committed run is a snapshot of the local model (`qwen3.5:9b`, 21 October 2026): 10 of 12 scored meals landed inside their reference range, with a mean signed error of −4.4%. The aggregate hides the useful part, though. The errors are concentrated in energy-dense food — two slices of pepperoni pizza at 300 kcal against 450–700, two samosas and a chai at 240 against 310–530 — and a meal can total in range while an item inside it is wrong: "2 rotis, dal, and a lassi" lands at 470 kcal against 420–650, with the roti row at 140 kcal against 180–260. The same run also returned `one piece` for "two samosas", which is a portion bug rather than a calorie-estimate bug. Those per-item rows are the reason the harness exists.

## File layout

- `nutriparse.py` — command-line application source
- `store.py` — the shared journal store: validation, atomic writes, totals, used by both the CLI and the server
- `server.py` — FastAPI app serving the public assets plus the journal, AI and image endpoints
- `requirements.txt` — backend dependencies (FastAPI, Uvicorn)
- `requirements-dev.txt` — adds the HTTP test transport (`httpx`)
- `compose.html`, `compose.css`, `compose.js` — the app: the Compose and Journal views, served at `/`
- `journal-client.js` — the browser side of the journal API, including the one-time `localStorage` migration
- `journal-legacy.html`, `journal-legacy.css` — the earlier editorial journal, retained as a working backup at `/journal-legacy.html`
- `seed_demo.py` — writes `data.demo.json`, sample entries for screenshots; `server.py --demo` serves it instead of the real journal
- `tests/` — store and FastAPI tests (`python -m unittest discover -s tests`)
- `evals/` — the parse evaluation harness, its case fixtures, and the committed results
- `screenshots/` — the screenshots used in this README
- `data.json` — the journal, shared by the CLI and the web app (created on first write; ignored by Git)
- `.env` — your OpenRouter API key (create from `.env.example`; do not commit)
- `.env.example` — documented environment variables template
- `README.md` — this file
- `setup_image_generator.bat` / `start_image_generator.bat` — CUDA recipe image service (stable-diffusion.cpp + SDXL-Turbo)
- `.image-tools/`, `models/` — downloaded image runtime and models (ignored by Git)
