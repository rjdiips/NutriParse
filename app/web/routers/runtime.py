"""Effective runtime configuration reported to the browser.

Both pages read these values at startup so their request timeouts follow the
active provider instead of keeping their own copies. The response is one
snapshot of the settings the next AI call will use.
"""

from fastapi import APIRouter, Depends

from ...config import (
    DEFAULT_COOK_TIMEOUT,
    DEFAULT_PARSE_TIMEOUT,
    Settings,
)
from ..dependencies import current_settings
from ..schemas import RuntimeConfigResponse

router = APIRouter(prefix="/api", tags=["config"])


def _milliseconds(seconds: float) -> int:
    """Round a settings timeout to the integer milliseconds the browser reads."""
    return int(round(seconds * 1000))


@router.get("/config", response_model=RuntimeConfigResponse)
def config(settings: Settings = Depends(current_settings)):
    # Resolve each feature separately: the OpenRouter defaults differ, and an
    # LLM_TIMEOUT override applies to both.
    parse = settings.llm(DEFAULT_PARSE_TIMEOUT)
    cook = settings.llm(DEFAULT_COOK_TIMEOUT)
    return {
        "provider": parse.provider,
        "model": parse.model,
        "parse_timeout_ms": _milliseconds(parse.timeout),
        "cook_timeout_ms": _milliseconds(cook.timeout),
        "image_timeout_ms": _milliseconds(settings.local_image_timeout),
    }
