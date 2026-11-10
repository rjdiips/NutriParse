"""Client and content-addressed cache for the optional local image generator."""

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path

import httpx

from ..config import Settings
from .transport import ProviderTransport


def recipe_image_prompt(recipe) -> str:
    """Build the one prompt sent to the image generator."""
    return (
        "Photorealistic editorial food photograph of a finished dish: "
        f"{recipe['title']}. {recipe['description']} Plated naturally, warm soft daylight, "
        "three-quarter close view, simple uncluttered kitchen background, no text."
    )


def _normalize_prompt(prompt: str) -> str:
    """Collapse whitespace so cosmetic differences reuse the same file."""
    return " ".join(prompt.split())


def recipe_image_cache_key(recipe, settings: Settings) -> str:
    """Hash the normalized prompt together with the generation settings."""
    seed = (
        f"{_normalize_prompt(recipe_image_prompt(recipe))}\n"
        f"width={settings.local_image_width}\n"
        f"height={settings.local_image_height}\n"
        f"steps={settings.local_image_steps}"
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def recipe_image_path(cache_dir: Path, image_hash: str) -> Path:
    """Return the PNG path for one content hash."""
    return Path(cache_dir) / f"{image_hash}.png"


def recipe_image_exists(cache_dir: Path, image_hash: str) -> bool:
    """Say whether a content hash is already stored."""
    return recipe_image_path(cache_dir, image_hash).is_file()


def store_recipe_image(cache_dir: Path, image_hash: str, image_bytes: bytes) -> None:
    """Store one PNG without ever replacing an already-served file.

    The URL is immutable for a year, so a concurrent request that loses the
    race keeps the first stored bytes instead of overwriting them. The temp
    file and hardlink keep readers from observing a partial write.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = recipe_image_path(cache_dir, image_hash)
    handle, temporary = tempfile.mkstemp(
        prefix=f"{image_hash}.", suffix=".tmp", dir=cache_dir
    )
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(image_bytes)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            pass
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


async def generate_local_recipe_image(recipe, endpoint, settings: Settings,
                                      transport: ProviderTransport) -> bytes:
    """Ask the local A1111-compatible API to render a recipe image."""
    request_payload = {
        "prompt": recipe_image_prompt(recipe),
        "steps": settings.local_image_steps,
        "width": settings.local_image_width,
        "height": settings.local_image_height,
    }
    timeout = settings.local_image_timeout
    try:
        # A transient 500 or 503 while the diffusion server recovers is retried
        # by the shared transport with the same backoff as model calls.
        response = await transport.post_image(
            endpoint,
            json=request_payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"Image generator timed out after {timeout:g} seconds"
        ) from exc
    except httpx.RequestError as exc:
        reason = str(exc).replace("\r", " ").replace("\n", " ")[:160]
        raise RuntimeError(f"Could not connect to image generator: {reason}") from exc

    if response.status_code >= 400:
        # Do not log the response body: image services can echo the recipe
        # prompt, and prompts are intentionally excluded from logs.
        raise RuntimeError(f"Image generator returned HTTP {response.status_code}")

    try:
        payload = json.loads(response.content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RuntimeError("Image generator returned a non-UTF-8 response") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Image generator returned invalid JSON at character {exc.pos}"
        ) from exc
    try:
        encoded = payload["images"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Local image generator returned no image") from exc
    if not isinstance(encoded, str) or len(encoded) > 8_000_000:
        raise RuntimeError("Local image generator returned invalid image data")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("Local image generator returned invalid image data") from exc
