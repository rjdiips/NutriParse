#!/usr/bin/env python3
"""FastAPI application factory and server entry point."""

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import HOST, PORT, env_file_mtime, load_env, resolve_llm
from .journal import store
from .logging_config import configure_logging
from .web.http import register_api_headers, register_error_handlers
from .web.routers import ai, health, images, journal
from .web.static import register_static_routes


@asynccontextmanager
async def lifespan(_app):
    configure_logging()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="NutriParse",
        description="Nutrition parsing, recipe ideas, and the shared journal.",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.env = load_env()
    application.state.env_mtime = env_file_mtime()
    application.state.store_path = store.DEFAULT_PATH

    register_api_headers(application)
    register_error_handlers(application)
    application.include_router(health.router)
    application.include_router(journal.router)
    application.include_router(ai.router)
    application.include_router(images.router)
    register_static_routes(application)
    return application


app = create_app()


def main():
    demo = "--demo" in sys.argv[1:]
    app.state.store_path = store.BASE_DIR / "data.demo.json" if demo else store.DEFAULT_PATH
    app.state.env = load_env()
    app.state.env_mtime = env_file_mtime()
    llm = resolve_llm(app.state.env, 30)
    if llm["provider"] == "openrouter" and not llm["api_key"]:
        print("Warning: OPENROUTER_API_KEY is not configured; AI features will fail.")
    print(f"LLM provider: {llm['provider']} ({llm['model']})")
    if demo:
        print(f"Demo journal: {app.state.store_path.name} (run python scripts/seed_demo.py to refresh it)")
    print(f"Serving NutriParse at http://{HOST}:{PORT}/")
    try:
        uvicorn.run(app, host=HOST, port=PORT)
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
