"""Client for the optional local A1111-compatible image generator."""

import base64
import json
import time
import urllib.error
import urllib.request

from ..config import IMAGE_TIMEOUT, Settings


def generate_local_recipe_image(recipe, endpoint, settings: Settings):
    """Ask the local A1111-compatible API to render a recipe image."""
    prompt = (
        "Photorealistic editorial food photograph of a finished dish: "
        f"{recipe['title']}. {recipe['description']} Plated naturally, warm soft daylight, "
        "three-quarter close view, simple uncluttered kitchen background, no text."
    )
    body = json.dumps({
        "prompt": prompt,
        "steps": settings.local_image_steps,
        "width": settings.local_image_width,
        "height": settings.local_image_height,
    }).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        # The local diffusion server can return a transient 500 while it is
        # recovering from an inference error. Retry once, serially, before
        # telling the UI that the image is unavailable.
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=IMAGE_TIMEOUT) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 500 and attempt == 0:
                    time.sleep(1)
                    continue
                # Do not log the response body: image services can echo the
                # recipe prompt, and prompts are intentionally excluded from logs.
                raise RuntimeError(f"Image generator returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason).replace("\r", " ").replace("\n", " ")[:160]
        raise RuntimeError(f"Could not connect to image generator: {reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"Image generator timed out after {IMAGE_TIMEOUT:g} seconds"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Image generator I/O error: {type(exc).__name__}") from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError("Image generator returned a non-UTF-8 response") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Image generator returned invalid JSON at character {exc.pos}") from exc
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
