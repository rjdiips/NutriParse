"""Public frontend assets.

Only the browser application under ``web/`` is reachable. Everything else in
the repository — source, ``.env``, journals — stays outside the mounted tree.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import BASE_DIR

WEB_DIR = BASE_DIR / "web"

PAGE_ROUTES = {
    "/": "web/pages/nutriparse.html",
    "/index.html": "web/pages/nutriparse.html",
    "/food-journal.html": "web/pages/food-journal.html",
}

# Stable top-level asset URLs kept for bookmarks and older clients. New pages
# load assets from /assets/... so files can be reorganised without breaking URL.
LEGACY_ASSET_ROUTES = {
    "/nutriparse.css": "web/css/nutriparse.css",
    "/food-journal.css": "web/css/food-journal.css",
    "/nutriparse.js": "web/js/nutriparse-legacy.js",
    "/journal-client.js": "web/js/journal-client.js",
    "/food-journal.js": "web/js/food-journal.js",
    "/favicon.svg": "web/assets/favicon.svg",
    "/favicon.ico": "web/assets/favicon.ico",
}

MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def register_static_routes(application: FastAPI):
    """Mount the browser assets and serve each page from an explicit route."""
    application.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    for route, relative_path in {**PAGE_ROUTES, **LEGACY_ASSET_ROUTES}.items():
        path = Path(BASE_DIR / relative_path)

        async def serve_static(path=path):
            return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix))

        application.add_api_route(
            route,
            serve_static,
            methods=["GET"],
            include_in_schema=False,
            name=f"static:{route}",
        )
