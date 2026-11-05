"""Optional local recipe-image generation route."""

import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from ...logging_config import IMAGE_LOGGER
from ...services.images import generate_local_recipe_image, image_int
from ..dependencies import JSONBody, current_env
from ..http import json_response

router = APIRouter(prefix="/api", tags=["images"])


@router.post("/recipe-image")
def recipe_image(request: Request, payload: JSONBody):
    title = payload.get("title")
    description = payload.get("description", "")
    if (not isinstance(title, str) or not title.strip()
            or not isinstance(description, str)):
        raise HTTPException(400, "A recipe title and description are required")
    if len(title) > 120 or len(description) > 300:
        raise HTTPException(400, "Recipe title or description is too long")

    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    env = current_env(request)
    enabled = env.get("LOCAL_IMAGE_GENERATION_ENABLED", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        IMAGE_LOGGER.warning(
            "event=image_generation_skipped request_id=%s reason=disabled", request_id
        )
        raise HTTPException(503, "Local image generation is disabled")
    local_image_url = env.get(
        "LOCAL_IMAGE_API_URL", "http://127.0.0.1:7860/sdapi/v1/txt2img"
    ).strip()
    if not local_image_url:
        IMAGE_LOGGER.warning(
            "event=image_generation_skipped request_id=%s reason=endpoint_not_configured",
            request_id,
        )
        raise HTTPException(503, "Local image generation is unavailable")
    recipe = {"title": title.strip(), "description": description.strip()}
    width = image_int(env, "LOCAL_IMAGE_WIDTH", 640, 64, 2048)
    height = image_int(env, "LOCAL_IMAGE_HEIGHT", 480, 64, 2048)
    steps = image_int(env, "LOCAL_IMAGE_STEPS", 20, 1, 100)
    IMAGE_LOGGER.info(
        "event=image_generation_started request_id=%s width=%d height=%d steps=%d",
        request_id, width, height, steps,
    )
    try:
        image = generate_local_recipe_image(recipe, local_image_url, env)
    except RuntimeError as error:
        IMAGE_LOGGER.warning(
            "event=image_generation_failed request_id=%s duration_ms=%d error=%r",
            request_id, round((time.monotonic() - started) * 1000), str(error),
        )
        raise HTTPException(503, "Recipe image could not be generated") from error
    except Exception as error:
        IMAGE_LOGGER.error(
            "event=image_generation_failed request_id=%s duration_ms=%d error_type=%s",
            request_id, round((time.monotonic() - started) * 1000), type(error).__name__,
        )
        raise HTTPException(503, "Recipe image could not be generated") from error
    IMAGE_LOGGER.info(
        "event=image_generation_succeeded request_id=%s duration_ms=%d image_bytes=%d",
        request_id, round((time.monotonic() - started) * 1000),
        len(image.partition(",")[2]) * 3 // 4,
    )
    return json_response({"image": image})
