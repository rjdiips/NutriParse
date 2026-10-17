#!/usr/bin/env python3
"""Local OpenVINO Stable Diffusion image API for Leftover Alchemist."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import threading

from PIL import Image
import openvino as ov
import openvino_genai as ov_genai


BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.environ.get(
    "LOCAL_IMAGE_MODEL_DIR", BASE_DIR / "models" / "stable-diffusion-v1-5-int8-ov"
))
HOST = "127.0.0.1"
PORT = 7860
MAX_REQUEST_BYTES = 16 * 1024
GENERATION_LOCK = threading.Lock()


def load_pipeline():
    if not MODEL_DIR.is_dir():
        raise RuntimeError(f"Model folder not found: {MODEL_DIR}")
    devices = ov.Core().available_devices
    device = "GPU" if "GPU" in devices else "CPU"
    print(f"Loading local image model on {device}. First run may take a few minutes.", flush=True)
    return ov_genai.Text2ImagePipeline(str(MODEL_DIR), device)


class Handler(BaseHTTPRequestHandler):
    pipeline = None

    def do_POST(self):
        if self.path != "/sdapi/v1/txt2img":
            self._send_json(404, {"error": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if size < 0 or size > MAX_REQUEST_BYTES:
            self._send_json(413, {"error": "Invalid request size"})
            return
        try:
            request = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Invalid JSON"})
            return
        prompt = request.get("prompt") if isinstance(request, dict) else None
        if not isinstance(prompt, str) or not prompt.strip():
            self._send_json(400, {"error": "A prompt is required"})
            return

        try:
            with GENERATION_LOCK:
                result = self.pipeline.generate(
                    prompt.strip()[:2000], width=512, height=512,
                    num_inference_steps=20, num_images_per_prompt=1,
                )
            image = Image.fromarray(result.data[0])
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        except Exception:
            self._send_json(503, {"error": "Local image generation failed"})
            return
        self._send_json(200, {"images": [encoded]})

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Prompts and recipe data stay out of the console log.
        print(f"local_image_api {args[1] if len(args) > 1 else ''}", flush=True)


def main():
    Handler.pipeline = load_pipeline()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Local image generator listening at http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
