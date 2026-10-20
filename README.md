# Calorie Tracker

A calorie intake tracking app with a command-line interface and a web interface, plus optional AI-powered nutrition suggestions from OpenRouter or a local LLM.

## Features

- Add food entries with calories, protein, carbs, and fat
- Conjure three recipe ideas from leftover ingredients with AI
- Categorize entries by meal (breakfast, lunch, dinner, snack)
- View recent entries
- View a 7-day daily summary with progress toward your calorie goal
- Set and update your daily calorie goal
- Delete entries
- Data is persisted to `data.json` (CLI) or `localStorage` (web)

## Requirements

- Python 3.8+

No extra packages are required; the backend uses only the Python standard library. Recipe images are optional and use a separate local service (see below).

## Usage

### Command-line interface

```powershell
python calorie_tracker.py
```

Follow the on-screen menu to track your intake. Option 6 (Suggest nutrition with AI) calls the backend server at `http://localhost:8000`, so start `server.py` first if you want to use it.

### Web interface

1. Start the backend server:

```powershell
python server.py
```

2. Open http://localhost:8000 in your browser.

The "Add Entry" tab now includes a **Portion** field and a **Suggest with AI** button. Type a food name (and optional portion like "1 slice", "100g", "250ml", "1 cup") and click **Suggest with AI** to have the configured AI model estimate calories + macros, which prefill the editable fields before you save.

The **Leftover Alchemist** tab accepts a free-text ingredient list and an optional "use soon" note. It returns three playful recipe ideas with practical steps and approximate nutrition per serving; the recipes appear as soon as the text response is ready, while local AI food images load in the background when the image service is running. **Add to tracker** prefills the Add Entry form for review; it never saves automatically. Only the submitted ingredients and note are sent to the configured LLM provider, not tracker entries or the calorie goal. Recipe images use a local service at `http://127.0.0.1:7860` by default; no image-generation API is called or charged.

### Local recipe images (NVIDIA CUDA, recommended)

Recipe images use an AUTOMATIC1111-compatible `/sdapi/v1/txt2img` endpoint. On an NVIDIA GPU, run `setup_image_generator.bat` once. It downloads the stable-diffusion.cpp CUDA build (about 900 MB including the CUDA runtime) and Stability AI's SDXL-Turbo checkpoint (6.9 GB). Then launch `start_image_generator.bat` before using the Alchemist. The service binds to `127.0.0.1:7860`, uses the GPU, and produces 512×512 images in 6 steps, typically in a few seconds each on an 8 GB laptop GPU. First startup loads the checkpoint and can take 20–40 seconds.

Turbo checkpoints expect CFG 1 and few sampling steps; the start script passes both. Image size and steps are read from `.env` (`LOCAL_IMAGE_WIDTH`, `LOCAL_IMAGE_HEIGHT`, `LOCAL_IMAGE_STEPS`). If you replace SDXL-Turbo with a regular checkpoint such as SD 1.5, set `LOCAL_IMAGE_STEPS=20` in `.env` and adjust `--cfg-scale` in the start script. Binaries and model files live in `.image-tools/` and `models/`, both excluded by `.gitignore`.

### Local recipe images (Intel OpenVINO, alternative)

On Windows with the Python install manager (`py`) available, run `setup_local_image_generator.bat` once. It installs a project-local Python runtime and OpenVINO GenAI environment, then downloads Intel's pre-converted, quantized Stable Diffusion 1.5 model (about 2.3 GB). Launch `start_local_image_generator.bat` before using the Alchemist. The service binds to `127.0.0.1:7860`, uses the Intel GPU when available (otherwise CPU), and produces 512×512 images in sequence after the recipe ideas have already appeared. First startup and model compilation can take several minutes. This path is Intel-specific; on AMD GPUs it falls back to CPU.

Either image service is optional: if it is stopped, recipe ideas still load without images. Set `LOCAL_IMAGE_GENERATION_ENABLED=false` in `.env` to disable image requests entirely, or override `LOCAL_IMAGE_API_URL` to use another address. Model files, runtime, and virtual environments stay local and are excluded by `.gitignore`.

## AI suggestions setup

AI nutrition suggestions require an OpenRouter API key. The key is read by the backend from `.env` â€” never exposed to the browser or end user.

1. Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

2. Fill in `OPENROUTER_API_KEY` with your OpenRouter key. Optionally set `OPENROUTER_MODEL` (defaults to `openrouter/free`). To run without cloud calls, see "Local models" below. Recipe images do not use this key; they are generated locally by the image service.

3. Start `server.py` and use the web "Suggest with AI" button or CLI option 6.

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

- `calorie_tracker.py` â€” command-line application source
- `server.py` â€” stdlib HTTP server serving static files plus the AI and image endpoints
- `index.html` â€” static web app (served by `server.py`)
- `data.json` â€” persisted entries and goal (created on first CLI run)
- `.env` â€” your OpenRouter API key (create from `.env.example`; do not commit)
- `.env.example` â€” documented environment variables template
- `README.md` â€” this file
- `setup_image_generator.bat` / `start_image_generator.bat` â€” CUDA recipe image service (stable-diffusion.cpp + SDXL-Turbo)
- `setup_local_image_generator.bat` / `start_local_image_generator.bat` â€” Intel OpenVINO alternative
- `.image-tools/`, `models/` â€” downloaded image runtime and models (ignored by Git)
