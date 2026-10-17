# Calorie Tracker

A calorie intake tracking app with a command-line interface and a web interface, plus optional AI-powered nutrition suggestions via OpenRouter.

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

No extra packages are required; the backend uses only the Python standard library.

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

The "Add Entry" tab now includes a **Portion** field and a **Suggest with AI** button. Type a food name (and optional portion like "1 slice", "100g", "250ml", "1 cup") and click **Suggest with AI** to have OpenRouter estimate calories + macros, which prefill the editable fields before you save.

The **Leftover Alchemist** tab accepts a free-text ingredient list and an optional "use soon" note. It returns three playful recipe ideas with practical steps and approximate nutrition per serving; the recipes appear as soon as the text response is ready, while local AI food images load in the background when the OpenVINO service is running. **Add to tracker** prefills the Add Entry form for review; it never saves automatically. Only the submitted ingredients and note are sent to OpenRouter, not tracker entries or the calorie goal. Recipe images use a local OpenVINO service at `http://127.0.0.1:7860` by default; no image-generation API is called or charged. OpenRouter currently has no free image-generation models.

### Local recipe images (Intel OpenVINO)

On Windows with the Python install manager (`py`) available, run `setup_local_image_generator.bat` once. It installs a project-local Python runtime and OpenVINO GenAI environment, then downloads Intel's pre-converted, quantized Stable Diffusion 1.5 model (about 2.3 GB). Launch `start_local_image_generator.bat` before using the Alchemist. The service binds to `127.0.0.1:7860`, uses the Intel GPU when available (otherwise CPU), and produces 512×512 images in sequence after the recipe ideas have already appeared. First startup and model compilation can take several minutes. The app calls only this local service by default; if it is stopped, recipe ideas still load without images. Set `LOCAL_IMAGE_GENERATION_ENABLED=false` in `.env` to disable image requests entirely, or override `LOCAL_IMAGE_API_URL` to use another address. Model files, runtime, and virtual environments stay local and are excluded by `.gitignore`.

## AI suggestions setup

AI nutrition suggestions require an OpenRouter API key. The key is read by the backend from `.env` â€” never exposed to the browser or end user.

1. Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

2. Fill in `OPENROUTER_API_KEY` with your OpenRouter key. Optionally set `OPENROUTER_MODEL` (defaults to `openrouter/free`). Recipe images do not use this key; they are generated locally by OpenVINO.

3. Start `server.py` and use the web "Suggest with AI" button or CLI option 6.

Each LLM request is recorded in `logs/llm.log`, including its request ID, model,
food and portion, duration, and success or failure. Logs rotate automatically
after reaching 2 MB, keeping up to five older files. API credentials and raw
provider payloads are not logged.

## File layout

- `calorie_tracker.py` â€” command-line application source
- `server.py` â€” stdlib HTTP server serving static files + `/api/suggest` and `/api/leftover-alchemist` OpenRouter endpoints
- `index.html` â€” static web app (served by `server.py`)
- `data.json` â€” persisted entries and goal (created on first CLI run)
- `.env` â€” your OpenRouter API key (create from `.env.example`; do not commit)
- `.env.example` â€” documented environment variables template
- `README.md` â€” this file
