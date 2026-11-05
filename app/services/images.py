"""Client for the optional local A1111-compatible image generator."""

import base64
import json
import time
import urllib.error
import urllib.request


def image_int(env, key, default, low, high):
    """Read a bounded integer setting from the environment."""
    try:
        value = int(env.get(key, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def generate_local_recipe_image(recipe, endpoint, env):
    """Ask the local A1111-compatible API to render a recipe image."""
    prompt = (
        "Photorealistic editorial food photograph of a finished dish: "
        f"{recipe['title']}. {recipe['description']} Plated naturally, warm soft daylight, "
        "three-quarter close view, simple uncluttered kitchen background, no text."
    )
    body = json.dumps({
        "prompt": prompt,
        "steps": image_int(env, "LOCAL_IMAGE_STEPS", 20, 1, 100),
        "width": image_int(env, "LOCAL_IMAGE_WIDTH", 512, 64, 2048),
        "height": image_int(env, "LOCAL_IMAGE_HEIGHT", 512, 64, 2048),
    }).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        # The local diffusion server can return a transient 500 while it is
        # recovering from an inference error. Retry once, serially, before
        # telling the UI that the image is unavailable.
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
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
        raise RuntimeError("Image generator timed out after 240 seconds") from exc
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
