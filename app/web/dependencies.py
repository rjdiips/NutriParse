"""Shared FastAPI dependencies and route-level guards."""

import json
import threading
import time
import uuid
from typing import Annotated, Callable
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request

from ..config import MAX_REQUEST_BYTES, env_file_mtime, load_env, resolve_llm
from ..journal import store
from ..logging_config import LOGGER
from ..services.llm import LLMRequestError
from .http import json_response

_ENV_LOCK = threading.Lock()


async def json_body(request: Request):
    """Read and validate a JSON object body exactly as the old handler did."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Content-Type must be application/json")

    raw_length = request.headers.get("content-length")
    if raw_length is None:
        raise HTTPException(411, "Content-Length is required")
    try:
        length = int(raw_length)
    except ValueError:
        raise HTTPException(400, "Invalid Content-Length") from None
    if length < 0:
        raise HTTPException(411, "Content-Length is required")
    if length > MAX_REQUEST_BYTES:
        raise HTTPException(413, "Request body is too large")

    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        raise HTTPException(413, "Request body is too large")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid JSON body") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON body must be an object")
    return payload


JSONBody = Annotated[dict, Depends(json_body)]


def require_same_origin(request):
    """Refuse a journal write that some other site asked the browser to make."""
    origin = request.headers.get("origin")
    if not origin:
        # Same-origin requests may omit it, and the CLI never sends one.
        return
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    allowed = {f"localhost:{port}", f"127.0.0.1:{port}", f"[::1]:{port}"}
    if urlsplit(origin).netloc.lower() not in allowed:
        raise HTTPException(403, "Journal writes must come from the NutriParse app")


def current_env(request):
    """Reload .env when the file changes so settings apply without a restart."""
    state = request.app.state
    mtime = env_file_mtime()
    if state.env_mtime != mtime:
        with _ENV_LOCK:
            if state.env_mtime != mtime:
                state.env = load_env()
                state.env_mtime = mtime
    return state.env


def write_journal(request, operation, missing_is_404=False):
    try:
        document = operation()
    except store.EntryNotFound as error:
        if not missing_is_404:
            raise HTTPException(400, str(error)) from error
        raise HTTPException(404, str(error)) from error
    except store.StoreError as error:
        raise HTTPException(400, str(error)) from error
    except OSError as error:
        LOGGER.warning("event=journal_write_failed error=%s", error)
        raise HTTPException(500, "The journal could not be written") from error
    return json_response(document)


def run_ai_feature(feature, operation: Callable[[], dict], env):
    """Run one model-backed feature with the same structured logging as before."""
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    llm = resolve_llm(env, 30)
    # Keep user-provided ingredients, credentials, and provider payloads out of logs.
    LOGGER.info(
        "event=llm_call_started request_id=%s feature=%s provider=%s model=%s",
        request_id, feature, llm["provider"], llm["model"],
    )
    try:
        result = operation()
    except RuntimeError as error:
        LOGGER.warning(
            "event=llm_call_failed request_id=%s feature=%s duration_ms=%d error=%s%s",
            request_id, feature, round((time.monotonic() - started) * 1000), error,
            f" diagnostic={error.diagnostic}" if isinstance(error, LLMRequestError) else "",
        )
        raise HTTPException(502, str(error)) from error
    except Exception as error:
        LOGGER.exception(
            "event=llm_call_failed request_id=%s feature=%s duration_ms=%d error=unexpected_exception",
            request_id, feature, round((time.monotonic() - started) * 1000),
        )
        raise HTTPException(502, "AI request failed unexpectedly") from error
    LOGGER.info(
        "event=llm_call_succeeded request_id=%s feature=%s duration_ms=%d",
        request_id, feature, round((time.monotonic() - started) * 1000),
    )
    return result
