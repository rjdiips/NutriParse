# NutriParse

**LLM Nutrition & Recipe Service**

Turn free text about food into structured, validated nutrition data. A prompt-first web app and a command-line tool, with optional AI estimation and recipe generation from OpenRouter or any local OpenAI-compatible model.

## Features

- **Compose** — describe a meal in one line and get one editable row per food, with server-recomputed totals and the full call detail behind the result (`/api/parse`)
- **Cook** — list ingredients and get three recipe ideas with per-serving macros and optional local images (`/api/leftover-alchemist`); any idea can be seeded into the estimate table for review
- **Journal** — today's calories against your goal, history grouped by day with per-day totals, search, per-entry delete, and an editable daily goal
- **Manual entry** — add a row by hand when you already know the numbers, or when the model is unreachable
- Every parsed name and number stays editable, and totals are recomputed from the rows you can see
- Failures surface as typed messages with a retry; `?sample=1` previews a resolved result without a model call
- Seven-day daily summary with progress toward the goal in the CLI
- Data is persisted to `data.json` (CLI) or `localStorage` (web)

## Requirements

- Python 3.8+

No extra packages are required; the backend uses only the Python standard library. Recipe images are optional and use a separate local service (see below).

## Usage

### Command-line interface

```powershell
python nutriparse.py
```

Follow the on-screen menu to track your intake. The CLI keeps its own `data.json`; the web app keeps its entries in the browser's `localStorage`, so the two stores are independent. Option 6 (Suggest nutrition with AI) calls the backend server at `http://localhost:8000`, so start `server.py` first if you want to use it.

### Web interface

1. Start the backend server:

```powershell
python server.py
```

2. Open http://localhost:8000 in your browser.

The app has two views, switched from the top bar.

**Compose** is the prompt-first surface, with two intents sharing one input. **Estimate** turns a meal ("2 rotis, dal, and a glass of lassi") into one row per item; **Cook** turns an ingredient list into three recipe ideas with steps and per-serving macros. Every parsed name and number is editable, totals are summed server-side from the rows you can see, and **Request details** exposes the provider, model, latency, token counts, and the raw response JSON in both modes. Failures surface as typed messages with a retry, and images degrade to a labelled strip when the local service is off. **Add a row manually** seeds one blank editable row for numbers you already know; for that row the inspector reads *Pending save* and previews the payload the save will write, instead of implying a model call that never happened.

**Journal** is the read side of the same store: today's calories against your goal, protein/carbs/fat totals and entry count, an editable goal with presets, history grouped by day with per-day totals, a search box, and a per-entry delete.

Add `?sample=1` or `?sample=cook` to preview either resolved Compose state without a model call, and `?view=journal` to open the Journal view directly.

Saving writes entries to `localStorage` under `ct_data`. That is the same key and the same entry shape an earlier iteration of the app used, so the earlier editorial journal is retained as a working backup at http://localhost:8000/journal-legacy.html — it reads and writes the same store in both directions. Compose is the maintained surface; the legacy journal is there if you want the old layout back.

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

Each LLM request is recorded in `logs/llm.log`, including its request ID, model,
food and portion, duration, and success or failure. Logs rotate automatically
after reaching 2 MB, keeping up to five older files. API credentials and raw
provider payloads are not logged.

## File layout

- `nutriparse.py` — command-line application source
- `server.py` — stdlib HTTP server serving the app's public assets plus the AI and image endpoints
- `compose.html`, `compose.css`, `compose.js` — the app: the Compose and Journal views, served at `/`
- `journal-legacy.html`, `journal-legacy.css` — the earlier editorial journal, retained as a working backup at `/journal-legacy.html`
- `data.json` — persisted entries and goal for the CLI (created on first run)
- `.env` — your OpenRouter API key (create from `.env.example`; do not commit)
- `.env.example` — documented environment variables template
- `README.md` — this file
- `setup_image_generator.bat` / `start_image_generator.bat` — CUDA recipe image service (stable-diffusion.cpp + SDXL-Turbo)
- `.image-tools/`, `models/` — downloaded image runtime and models (ignored by Git)
