"""One JSON response shape and the shared exception handlers."""

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..logging_config import LOGGER


def json_response(content, status_code=200):
    """One response shape for every API route, matching the browser's reader."""
    return JSONResponse(
        content=content,
        status_code=status_code,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def register_error_handlers(app):
    """Install the API's typed error envelope on the application."""

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request, error):
        detail = error.detail if isinstance(error.detail, str) else "Request failed"
        return json_response({"error": detail}, error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request, _error):
        return json_response({"error": "Invalid request"}, 400)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request, error):
        LOGGER.error("event=unhandled_error path=%s", request.url.path, exc_info=error)
        return json_response({"error": "The server hit an unexpected error"}, 500)
