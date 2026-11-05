"""OpenAI-compatible chat transport and shared model-output validation."""

import json
import math
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from ..config import HOST, PORT, resolve_llm


class LLMRequestError(RuntimeError):
    """Safe client error plus provider diagnostics intended only for server logs."""

    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


def safe_error_excerpt(raw, secrets=()):
    """Return a bounded upstream error excerpt with request data removed."""
    excerpt = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    for secret in secrets:
        if secret:
            excerpt = excerpt.replace(secret, "<redacted>")
    excerpt = " ".join(excerpt.split())
    return excerpt[:1200]


def chat_completion(prompt, system_prompt, env, temperature, default_timeout,
                    invalid_json_message, meta=None):
    """Call the configured OpenAI-compatible chat endpoint and parse JSON.

    When ``meta`` is a dict, it is filled with provider, model, latency, and
    token counts so callers can surface call detail without logging payloads.
    """
    started = time.monotonic()
    config = resolve_llm(env, default_timeout)
    if config["provider"] == "openrouter" and not config["api_key"]:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if config["provider"] == "local":
        # Thinking models can spend thousands of tokens before emitting any
        # content; "none" keeps replies fast and non-empty.
        effort = env.get("LLM_REASONING_EFFORT", "none").strip()
        if effort:
            payload["reasoning_effort"] = effort
        json_mode = env.get("LLM_JSON_MODE", "true").strip().lower()
        if json_mode not in {"0", "false", "no", "off"}:
            payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": f"http://{HOST}:{PORT}/",
        "X-Title": "NutriParse",
    }
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"
    request = urllib.request.Request(
        f"{config['base_url']}/chat/completions", data=body, headers=headers, method="POST"
    )

    label = config["label"]
    try:
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Keep provider details out of the browser response, but retain enough
        # sanitized context in the server log to diagnose upstream failures.
        response_body = exc.read(4096)
        endpoint = urlsplit(config["base_url"])
        diagnostic = (
            f"provider={config['provider']} model={config['model']} "
            f"endpoint={endpoint.scheme}://{endpoint.netloc}{endpoint.path} "
            f"upstream_status={exc.code} response={safe_error_excerpt(response_body, (config['api_key'], prompt, system_prompt))}"
        )
        raise LLMRequestError(f"{label} returned HTTP {exc.code}", diagnostic) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = str(getattr(exc, "reason", exc)).replace("\r", " ").replace("\n", " ")[:240]
        endpoint = urlsplit(config["base_url"])
        diagnostic = (
            f"provider={config['provider']} model={config['model']} "
            f"endpoint={endpoint.scheme}://{endpoint.netloc}{endpoint.path} "
            f"transport_error={type(exc).__name__} reason={reason}"
        )
        raise LLMRequestError(f"Could not reach {label}", diagnostic) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} returned an invalid response") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"{label} returned an unexpected response shape") from exc
    if not isinstance(content, str):
        raise RuntimeError(f"{label} returned an unexpected response shape")
    content = content.strip()
    if content.startswith("```") and content.endswith("```"):
        content = content[3:-3].strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(invalid_json_message) from exc

    if meta is not None:
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        meta.update({
            "provider": config["provider"],
            "model": config["model"],
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        })
    return result


def number_field(result, key):
    """Read one non-negative finite number from a model result."""
    try:
        value = float(result[key])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError(f"AI response has an invalid '{key}' value") from exc
    if not math.isfinite(value) or value < 0:
        raise RuntimeError(f"AI response has an invalid '{key}' value")
    return value
