"""Optional local recipe-image generation and its content-addressed cache."""

import asyncio
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ...config import Settings
from ...logging_config import IMAGE_LOGGER
from ...services.images import (
    generate_local_recipe_image,
    recipe_image_cache_key,
    recipe_image_exists,
    recipe_image_path,
    store_recipe_image,
)
from ...services.transport import ProviderTransport
from ..dependencies import (
    cancel_on_disconnect,
    current_settings,
    http_transport,
    image_cache_dir,
    json_body,
)
from ..schemas import ApiError, ImageRequest, ImageResponse

router = APIRouter(prefix="/api", tags=["images"])

IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"
_IMAGE_HASH = re.compile(r"^[0-9a-f]{64}$")


def _image_url(image_hash: str) -> str:
    return f"/api/recipe-image/{image_hash}.png"


@router.post(
    "/recipe-image",
    response_model=ImageResponse,
    responses={400: {"model": ApiError}, 413: {"model": ApiError},
               415: {"model": ApiError}, 503: {"model": ApiError}},
    dependencies=[Depends(json_body)],
)
async def recipe_image(
    request: Request,
    payload: ImageRequest,
    settings: Settings = Depends(current_settings),
    transport: ProviderTransport = Depends(http_transport),
    cache_dir: Path = Depends(image_cache_dir),
):
    title = payload.title
    description = payload.description
    if not title.strip():
        raise HTTPException(400, "A recipe title and description are required")
    if len(title) > 120 or len(description) > 300:
        raise HTTPException(400, "Recipe title or description is too long")

    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    if not settings.local_image_generation_enabled:
        IMAGE_LOGGER.warning(
            "event=image_generation_skipped request_id=%s reason=disabled", request_id
        )
        raise HTTPException(503, "Local image generation is disabled")
    local_image_url = settings.local_image_api_url
    if not local_image_url:
        IMAGE_LOGGER.warning(
            "event=image_generation_skipped request_id=%s reason=endpoint_not_configured",
            request_id,
        )
        raise HTTPException(503, "Local image generation is unavailable")
    recipe = {"title": title.strip(), "description": description.strip()}
    image_hash = recipe_image_cache_key(recipe, settings)
    image_url = _image_url(image_hash)
    if recipe_image_exists(cache_dir, image_hash):
        IMAGE_LOGGER.info(
            "event=image_cache_hit request_id=%s duration_ms=%d "
            "width=%d height=%d steps=%d hash=%s",
            request_id, round((time.monotonic() - started) * 1000),
            settings.local_image_width, settings.local_image_height,
            settings.local_image_steps, image_hash,
        )
        return {"image": image_url, "cached": True}

    IMAGE_LOGGER.info(
        "event=image_generation_started request_id=%s width=%d height=%d steps=%d",
        request_id, settings.local_image_width, settings.local_image_height,
        settings.local_image_steps,
    )
    try:
        image = await cancel_on_disconnect(
            request,
            lambda: generate_local_recipe_image(
                recipe, local_image_url, settings, transport
            ),
        )
        await asyncio.to_thread(store_recipe_image, cache_dir, image_hash, image)
    except HTTPException:
        # A disconnected client is not an image failure; let its status through.
        raise
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
        request_id, round((time.monotonic() - started) * 1000), len(image),
    )
    return {"image": image_url, "cached": False}


@router.get(
    "/recipe-image/{image_hash}.png",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, 404: {"model": ApiError}},
)
async def recipe_image_file(
    image_hash: str,
    cache_dir: Path = Depends(image_cache_dir),
):
    """Serve one cached PNG for a year; the content hash makes it immutable."""
    if not _IMAGE_HASH.fullmatch(image_hash):
        raise HTTPException(404, "Recipe image was not found")
    image_path = recipe_image_path(cache_dir, image_hash)
    if not image_path.is_file():
        raise HTTPException(404, "Recipe image was not found")
    return FileResponse(
        image_path,
        media_type="image/png",
        headers={"Cache-Control": IMAGE_CACHE_CONTROL},
    )
