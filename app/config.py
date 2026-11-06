#!/usr/bin/env python3
"""Runtime configuration for NutriParse.

Paths, request limits, and the rules for reading ``.env`` live here so the
server and tests agree on the same values.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
HOST = "localhost"
PORT = 8100
ENV_FILE = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "llm.log"
IMAGE_LOG_FILE = LOG_DIR / "image_generation.log"

MAX_REQUEST_BYTES = 16 * 1024
MAX_TEXT_LENGTH = 500
MAX_MEAL_ITEMS = 15
RECIPE_COUNT = 3
MIN_RECIPE_STEPS = 4
MAX_RECIPE_STEPS = 6

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "qwen3.5:4b"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"

ENV_KEYS = (
    "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_TIMEOUT",
    "LLM_REASONING_EFFORT", "LLM_JSON_MODE",
    "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
    "LOCAL_IMAGE_API_URL",
    "LOCAL_IMAGE_GENERATION_ENABLED",
    "LOCAL_IMAGE_WIDTH", "LOCAL_IMAGE_HEIGHT", "LOCAL_IMAGE_STEPS",
    "OPENROUTER_TOKEN", "OPEN_ROUTER_API_KEY",
)


def load_env():
    """Read local settings, with process environment variables taking priority."""
    env = {}
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")

    for key in ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            env[key] = value

    if not env.get("OPENROUTER_API_KEY"):
        env["OPENROUTER_API_KEY"] = (
            env.get("OPENROUTER_TOKEN") or env.get("OPEN_ROUTER_API_KEY") or ""
        )
    return env


def env_file_mtime():
    try:
        return ENV_FILE.stat().st_mtime_ns
    except OSError:
        return None


def resolve_llm(env, default_timeout):
    """Return the active LLM provider settings.

    ``LLM_PROVIDER=local`` targets any OpenAI-compatible server (Ollama by
    default; llama.cpp, LM Studio, vLLM and similar all work); the default
    keeps using OpenRouter.
    """
    provider = env.get("LLM_PROVIDER", "openrouter").strip().lower() or "openrouter"
    if provider == "local":
        base_url = env.get("LLM_BASE_URL", DEFAULT_LOCAL_BASE_URL).strip().rstrip("/")
        base_url = base_url or DEFAULT_LOCAL_BASE_URL
        model = env.get("LLM_MODEL", DEFAULT_LOCAL_MODEL).strip() or DEFAULT_LOCAL_MODEL
        api_key = env.get("LLM_API_KEY", "").strip()
        label = "Local model"
        timeout = 180.0
    else:
        provider = "openrouter"
        base_url = (
            env.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)
            .strip()
            .rstrip("/")
        )
        base_url = base_url or DEFAULT_OPENROUTER_BASE_URL
        model = (
            env.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
            or DEFAULT_OPENROUTER_MODEL
        )
        api_key = env.get("OPENROUTER_API_KEY", "").strip()
        label = "OpenRouter"
        timeout = float(default_timeout)

    raw_timeout = env.get("LLM_TIMEOUT", "").strip()
    if raw_timeout:
        try:
            parsed = float(raw_timeout)
        except ValueError:
            parsed = 0.0
        if parsed > 0:
            timeout = parsed

    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "timeout": timeout,
        "label": label,
    }
