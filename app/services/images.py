"""Client for the optional local A1111-compatible image generator."""

import base64
import json

import httpx

from ..config import Settings
from .transport import ProviderTransport


async def generate_local_recipe_image(recipe, endpoint, settings: Settings,
                                      transport: ProviderTransport):
    """Ask the local A1111-compatible API to render a recipe image."""
    prompt = (
        "Photorealistic editorial food photograph of a finished dish: "
        f"{recipe['title']}. {recipe['description']} Plated naturally, warm soft daylight, "
        "three-quarter close view, simple uncluttered kitchen background, no text."
    )
    request_payload = {
        "prompt": prompt,
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
        base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("Local image generator returned invalid image data") from exc
    return f"data:image/png;base64,{encoded}"
