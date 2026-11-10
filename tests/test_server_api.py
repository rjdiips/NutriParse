#!/usr/bin/env python3
"""Tests for the FastAPI surface.

The web app's contract is mostly status codes and one response shape, because
both front ends read `payload.error` and otherwise expect a whole journal
document. These tests pin that contract down: the route allowlist, the journal
round trip, the body rules, and the same-origin check on writes.

Run them with:  python -m unittest discover -s tests
"""

import base64
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PNG_BYTES = b"\x89PNG\r\n\x1a\ncached recipe image"
IMAGE_URL_REGEX = r"^/api/recipe-image/[0-9a-f]{64}\.png$"

try:
    import httpx
    from fastapi.testclient import TestClient

    from app.config import (
        DEFAULT_COOK_TIMEOUT,
        DEFAULT_LOCAL_TIMEOUT,
        DEFAULT_OPENROUTER_MODEL,
        DEFAULT_PARSE_TIMEOUT,
        IMAGE_TIMEOUT,
        MAX_MEAL_ITEMS,
        MAX_REQUEST_BYTES,
        RECIPE_COUNT,
        Settings,
        SettingsProvider,
    )
    from app.journal import store
    from app.main import create_app
    from app.services import nutrition, recipes
    from app.web.routers import ai, images
except Exception as error:  # pragma: no cover - only without the API dependencies
    TestClient = None
    SKIP_REASON = f"API dependencies are unavailable: {error}"


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class ApiTestCase(unittest.TestCase):
    # Subclasses may inject a stubbed provider transport and zero delays.
    http_transport = None
    retry_delays = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.root = Path(self._tmp.name)
        self.env_file = self.root / ".env"
        self.env_file.write_text("", encoding="utf-8")
        self.image_cache_dir = self.root / "image-cache"
        self.settings_provider = SettingsProvider(self.env_file)
        self.app = create_app(
            settings_provider=self.settings_provider,
            store_path=self.root / "data.json",
            image_cache_dir=self.image_cache_dir,
            http_transport=self.http_transport,
            retry_delays=self.retry_delays,
        )
        # Enter the context manager so the lifespan creates the shared client.
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.client = stack.enter_context(
            TestClient(self.app, base_url="http://localhost:8100")
        )

    def set_settings(self, **values):
        """Write a temporary .env and reload it, as an operator edit would."""
        lines = []
        for key, value in values.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            lines.append(f"{key.upper()}={value}")
        self.env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.settings_provider.reload()
        return self.settings_provider.current()

    def entry(self, **overrides):
        row = {
            "name": "Roti (whole wheat)",
            "calories": 110,
            "protein": 3,
            "carbs": 22,
            "fat": 0.5,
            "meal": "lunch",
            "date": "2026-10-21",
        }
        row.update(overrides)
        return row

    def assert_error(self, response, status, message):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json(), {"error": message})
        self.assertTrue(response.headers["content-type"].startswith("application/json"))


class TestStaticAllowlist(ApiTestCase):
    def test_health_reports_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_openapi_documents_every_json_body(self):
        schema = self.app.openapi()
        operations = (
            ("/api/parse", "post"),
            ("/api/leftover-alchemist", "post"),
            ("/api/recipe-image", "post"),
            ("/api/journal/entries", "post"),
            ("/api/journal/goal", "post"),
            ("/api/journal/entries/{entry_id}", "put"),
        )
        for path, method in operations:
            with self.subTest(path=path):
                request_body = schema["paths"][path][method]["requestBody"]
                self.assertIn("application/json", request_body["content"])

    def test_openapi_documents_response_models(self):
        schema = self.app.openapi()
        for path, method in (
            ("/api/parse", "post"),
            ("/api/leftover-alchemist", "post"),
            ("/api/config", "get"),
            ("/api/journal", "get"),
            ("/health", "get"),
        ):
            with self.subTest(path=path):
                content = schema["paths"][path][method]["responses"]["200"]["content"]
                self.assertIn("application/json", content)

    def test_public_files_are_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))

        script = self.client.get("/nutriparse.js")
        self.assertEqual(script.status_code, 200)
        self.assertTrue(script.headers["content-type"].startswith("text/javascript"))

        asset = self.client.get("/assets/js/nutriparse.js")
        self.assertEqual(asset.status_code, 200)
        self.assertTrue(asset.headers["content-type"].startswith("text/javascript"))

    def test_journal_surface_is_served(self):
        page = self.client.get("/food-journal.html")
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.headers["content-type"].startswith("text/html"))

        style = self.client.get("/food-journal.css")
        self.assertEqual(style.status_code, 200)
        self.assertTrue(style.headers["content-type"].startswith("text/css"))

        client = self.client.get("/journal-client.js")
        self.assertEqual(client.status_code, 200)
        self.assertTrue(client.headers["content-type"].startswith("text/javascript"))

        page_asset = self.client.get("/assets/js/food-journal.js")
        self.assertEqual(page_asset.status_code, 200)
        self.assertTrue(page_asset.headers["content-type"].startswith("text/javascript"))

    def test_private_files_are_not_reachable(self):
        for path in ("/requirements.txt", "/.env", "/store.py", "/data.json", "/app/main.py"):
            with self.subTest(path=path):
                self.assert_error(self.client.get(path), 404, "Not Found")


def milliseconds(seconds):
    return int(round(seconds * 1000))


class TestRuntimeConfig(ApiTestCase):
    def test_openrouter_defaults_are_reported_in_milliseconds(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "provider": "openrouter",
            "model": DEFAULT_OPENROUTER_MODEL,
            "parse_timeout_ms": milliseconds(DEFAULT_PARSE_TIMEOUT),
            "cook_timeout_ms": milliseconds(DEFAULT_COOK_TIMEOUT),
            "image_timeout_ms": milliseconds(IMAGE_TIMEOUT),
        })

    def test_the_response_is_not_cached(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_local_provider_reports_the_local_default(self):
        self.set_settings(llm_provider="local", llm_model="local-test")
        body = self.client.get("/api/config").json()
        self.assertEqual(body["provider"], "local")
        self.assertEqual(body["model"], "local-test")
        self.assertEqual(body["parse_timeout_ms"], milliseconds(DEFAULT_LOCAL_TIMEOUT))
        self.assertEqual(body["cook_timeout_ms"], milliseconds(DEFAULT_LOCAL_TIMEOUT))

    def test_llm_timeout_overrides_both_llm_timeouts(self):
        self.set_settings(llm_provider="openrouter", llm_timeout=12.5)
        body = self.client.get("/api/config").json()
        self.assertEqual(body["parse_timeout_ms"], 12500)
        self.assertEqual(body["cook_timeout_ms"], 12500)
        # An LLM override leaves the local image service alone.
        self.assertEqual(body["image_timeout_ms"], milliseconds(IMAGE_TIMEOUT))

    def test_image_timeout_comes_from_the_typed_settings(self):
        self.set_settings(local_image_timeout=90)
        body = self.client.get("/api/config").json()
        self.assertEqual(body["image_timeout_ms"], 90000)

    def test_editing_the_timeout_changes_the_next_response(self):
        self.set_settings(llm_provider="openrouter", llm_timeout=10)
        first = self.client.get("/api/config").json()
        self.set_settings(llm_provider="openrouter", llm_timeout=90)
        second = self.client.get("/api/config").json()
        self.assertEqual(first["parse_timeout_ms"], 10000)
        self.assertEqual(first["cook_timeout_ms"], 10000)
        self.assertEqual(second["parse_timeout_ms"], 90000)
        self.assertEqual(second["cook_timeout_ms"], 90000)

    def test_editing_the_provider_changes_the_next_response(self):
        self.set_settings(llm_provider="local", llm_model="first-model")
        first = self.client.get("/api/config").json()
        self.set_settings(llm_provider="openrouter", openrouter_model="second-model")
        second = self.client.get("/api/config").json()
        self.assertEqual((first["provider"], first["model"]), ("local", "first-model"))
        self.assertEqual((second["provider"], second["model"]), ("openrouter", "second-model"))


class TestJournal(ApiTestCase):
    def test_round_trip_returns_the_whole_document(self):
        created = self.client.post(
            "/api/journal/entries",
            json={"entries": [self.entry()]},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assertEqual(created.status_code, 200)
        document = created.json()
        self.assertEqual(document["calorie_goal"], 2000)
        self.assertEqual(len(document["entries"]), 1)
        entry_id = document["entries"][0]["id"]

        read = self.client.get("/api/journal")
        self.assertEqual(read.json()["entries"][0]["id"], entry_id)

        goal = self.client.post(
            "/api/journal/goal",
            json={"calorie_goal": 2200},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assertEqual(goal.status_code, 200)
        self.assertEqual(goal.json()["calorie_goal"], 2200)

        deleted = self.client.delete(f"/api/journal/entries/{entry_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["entries"], [])

    def test_portion_survives_the_round_trip(self):
        created = self.client.post(
            "/api/journal/entries",
            json={"entries": [self.entry(portion="2 rotis")]},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["entries"][0]["portion"], "2 rotis")

        read = self.client.get("/api/journal")
        self.assertEqual(read.json()["entries"][0]["portion"], "2 rotis")

    def test_update_replaces_an_entry(self):
        created = self.client.post(
            "/api/journal/entries",
            json={"entries": [self.entry()]},
            headers={"Origin": "http://localhost:8100"},
        )
        entry_id = created.json()["entries"][0]["id"]

        updated = self.client.put(
            f"/api/journal/entries/{entry_id}",
            json={"entries": [self.entry(name="Dal", calories=150, portion="1 bowl")]},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assertEqual(updated.status_code, 200)
        rows = updated.json()["entries"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], entry_id)
        self.assertEqual((rows[0]["name"], rows[0]["portion"]), ("Dal", "1 bowl"))

    def test_update_of_unknown_entry_is_404(self):
        response = self.client.put(
            "/api/journal/entries/not-there",
            json={"entries": [self.entry()]},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assert_error(response, 404, "That entry is no longer in the journal.")

    def test_update_needs_entries(self):
        created = self.client.post(
            "/api/journal/entries",
            json={"entries": [self.entry()]},
            headers={"Origin": "http://localhost:8100"},
        )
        entry_id = created.json()["entries"][0]["id"]
        response = self.client.put(
            f"/api/journal/entries/{entry_id}",
            json={"entries": []},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assert_error(response, 400, "Send at least one entry.")

    def test_cross_origin_updates_are_refused(self):
        created = self.client.post(
            "/api/journal/entries",
            json={"entries": [self.entry()]},
            headers={"Origin": "http://localhost:8100"},
        )
        entry_id = created.json()["entries"][0]["id"]
        response = self.client.put(
            f"/api/journal/entries/{entry_id}",
            json={"entries": [self.entry()]},
            headers={"Origin": "https://evil.example"},
        )
        self.assert_error(response, 403, "Journal writes must come from the NutriParse app")

    def test_cross_origin_writes_are_refused(self):
        response = self.client.post(
            "/api/journal/goal",
            json={"calorie_goal": 2200},
            headers={"Origin": "https://evil.example"},
        )
        self.assert_error(response, 403, "Journal writes must come from the NutriParse app")
        self.assertFalse(Path(self.app.state.store_path).exists())

    def test_invalid_entries_are_rejected_by_the_store(self):
        response = self.client.post(
            "/api/journal/entries",
            json={"entries": [self.entry(meal="brunch")]},
            headers={"Origin": "http://localhost:8100"},
        )
        self.assert_error(response, 400, "Meal must be one of: breakfast, lunch, dinner, snack.")

    def test_unknown_entry_is_404(self):
        response = self.client.delete("/api/journal/entries/not-there")
        self.assert_error(response, 404, "That entry is no longer in the journal.")

    def test_corrupt_store_is_500(self):
        Path(self.app.state.store_path).write_text("{ not json", encoding="utf-8")
        response = self.client.get("/api/journal")
        self.assertEqual(response.status_code, 500)
        self.assertIn("could not be read", response.json()["error"])


class TestRequestBodies(ApiTestCase):
    def test_content_type_must_be_json(self):
        response = self.client.post(
            "/api/parse", content=b"{}", headers={"Content-Type": "text/plain"}
        )
        self.assert_error(response, 415, "Content-Type must be application/json")

    def test_invalid_json_is_400(self):
        response = self.client.post(
            "/api/parse", content=b"{ nope", headers={"Content-Type": "application/json"}
        )
        self.assert_error(response, 400, "Invalid JSON body")

    def test_body_must_be_an_object(self):
        response = self.client.post(
            "/api/parse", content=b"[1, 2]", headers={"Content-Type": "application/json"}
        )
        self.assert_error(response, 400, "JSON body must be an object")

    def test_oversized_body_is_413(self):
        body = b'{"text":"' + b"a" * MAX_REQUEST_BYTES + b'"}'
        response = self.client.post(
            "/api/parse", content=body, headers={"Content-Type": "application/json"}
        )
        self.assert_error(response, 413, "Request body is too large")

    def test_blank_meal_is_400(self):
        response = self.client.post("/api/parse", json={"text": "   "})
        self.assert_error(response, 400, "Describe at least one food")

    def test_unknown_route_is_404(self):
        self.assert_error(self.client.get("/api/nope"), 404, "Not Found")


class TestResponseModels(ApiTestCase):
    """Typed responses must accept the real shapes the services produce."""

    def test_success_responses_keep_the_api_headers(self):
        response = self.client.get("/api/journal")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_legacy_numeric_ids_survive_the_response_model(self):
        Path(self.app.state.store_path).write_text(json.dumps({
            "calorie_goal": 1800,
            "entries": [{
                "id": 1750000000.5, "name": "Dal", "calories": 150,
                "meal": "lunch", "date": "2026-10-20",
                "protein": 9, "carbs": 20, "fat": 4,
            }],
        }), encoding="utf-8")
        response = self.client.get("/api/journal")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entries"][0]["id"], "1750000000.5")

    def test_parse_success_matches_the_response_model(self):
        original = ai.parse_meal
        self.addCleanup(setattr, ai, "parse_meal", original)

        async def parse_stub(text, env, transport):
            return {
                "items": [{
                    "name": "Dal", "portion": "1 bowl", "calories": 150,
                    "protein": 9, "carbs": 20, "fat": 4,
                }],
                "totals": {"calories": 150, "protein": 9, "carbs": 20, "fat": 4},
                "meta": {
                    "provider": "local", "model": "test", "elapsed_ms": 5,
                    "prompt_tokens": 10, "completion_tokens": 20,
                },
            }

        ai.parse_meal = parse_stub
        response = self.client.post("/api/parse", json={"text": "dal"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["name"], "Dal")
        self.assertEqual(response.json()["totals"]["calories"], 150)

    def test_recipe_success_matches_the_response_model(self):
        original = ai.suggest_recipes
        self.addCleanup(setattr, ai, "suggest_recipes", original)
        recipe = {
            "title": "Dal",
            "description": "A bowl",
            "ingredients_used": ["dal"],
            "pantry_extras": [],
            "steps": ["Boil", "Simmer", "Season", "Serve"],
            "servings": 2,
            "nutrition": {"calories": 300, "protein": 12, "carbs": 40, "fat": 8},
            "image": None,
            "image_pending": False,
            "image_unavailable": True,
        }
        async def recipes_stub(ingredients, use_soon, env, transport):
            return {
                "recipes": [recipe, recipe, recipe],
                "meta": {
                    "provider": "local", "model": "test", "elapsed_ms": 5,
                    "prompt_tokens": 10, "completion_tokens": 20,
                },
            }

        ai.suggest_recipes = recipes_stub
        response = self.client.post(
            "/api/leftover-alchemist", json={"ingredients": "dal", "use_soon": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["recipes"]), RECIPE_COUNT)

    def test_image_success_matches_the_response_model(self):
        original = images.generate_local_recipe_image
        self.addCleanup(setattr, images, "generate_local_recipe_image", original)

        async def image_stub(recipe, endpoint, settings, transport):
            return PNG_BYTES

        images.generate_local_recipe_image = image_stub
        self.set_settings(
            local_image_generation_enabled=True,
            local_image_api_url="http://127.0.0.1:7860/sdapi/v1/txt2img",
        )
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertRegex(body["image"], IMAGE_URL_REGEX)
        self.assertFalse(body["cached"])
        self.assertNotIn("base64", response.text)


class TestRecipeImageCache(ApiTestCase):
    """Generated images live once under a content hash and are served by URL."""

    def setUp(self):
        super().setUp()
        self.generated = 0
        original = images.generate_local_recipe_image
        self.addCleanup(setattr, images, "generate_local_recipe_image", original)

        async def image_stub(recipe, endpoint, settings, transport):
            self.generated += 1
            return PNG_BYTES

        images.generate_local_recipe_image = image_stub
        self.enable_images()

    def post_image(self, title="Dal", description="A bowl"):
        return self.client.post(
            "/api/recipe-image", json={"title": title, "description": description}
        )

    def enable_images(self, **overrides):
        self.set_settings(
            local_image_generation_enabled=True,
            local_image_api_url="http://127.0.0.1:7860/sdapi/v1/txt2img",
            **overrides,
        )

    def stored_path(self, url):
        return self.image_cache_dir / url.rsplit("/", 1)[-1]

    def test_first_request_stores_the_png_and_returns_a_url(self):
        response = self.post_image()
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(set(body), {"image", "cached"})
        self.assertFalse(body["cached"])
        self.assertRegex(body["image"], IMAGE_URL_REGEX)
        self.assertNotIn("base64", response.text)
        self.assertEqual(self.stored_path(body["image"]).read_bytes(), PNG_BYTES)

    def test_the_url_serves_the_png_with_an_immutable_cache_header(self):
        url = self.post_image().json()["image"]

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PNG_BYTES)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(
            response.headers["cache-control"],
            "public, max-age=31536000, immutable",
        )

    def test_a_repeat_request_reuses_the_stored_image(self):
        first = self.post_image().json()
        second = self.post_image().json()

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["image"], first["image"])
        self.assertEqual(self.generated, 1)

    def test_whitespace_around_the_recipe_does_not_change_the_hash(self):
        first = self.post_image(title="Dal", description="A bowl").json()
        second = self.post_image(title="  Dal  ", description=" A   bowl ").json()

        self.assertEqual(second["image"], first["image"])
        self.assertTrue(second["cached"])
        self.assertEqual(self.generated, 1)

    def test_dimensions_and_steps_are_part_of_the_hash(self):
        first = self.post_image().json()["image"]
        self.enable_images(local_image_width=320)
        second = self.post_image().json()
        self.enable_images(local_image_height=240)
        third = self.post_image().json()
        self.enable_images(local_image_steps=9)
        fourth = self.post_image().json()

        self.assertEqual(
            len({first, second["image"], third["image"], fourth["image"]}), 4
        )
        self.assertFalse(second["cached"])
        self.assertFalse(third["cached"])
        self.assertFalse(fourth["cached"])
        self.assertEqual(self.generated, 4)

    def test_an_unknown_hash_is_404(self):
        response = self.client.get(f"/api/recipe-image/{'0' * 64}.png")

        self.assert_error(response, 404, "Recipe image was not found")

    def test_disabled_generation_is_503_even_when_an_image_is_cached(self):
        self.post_image()
        self.set_settings(local_image_generation_enabled=False)

        response = self.post_image()

        self.assert_error(response, 503, "Local image generation is disabled")
        self.assertEqual(self.generated, 1)

    def test_storing_the_same_hash_again_keeps_the_first_bytes(self):
        images.store_recipe_image(self.image_cache_dir, "a" * 64, b"first image")
        images.store_recipe_image(self.image_cache_dir, "a" * 64, b"second image")

        stored = images.recipe_image_path(self.image_cache_dir, "a" * 64)
        self.assertEqual(stored.read_bytes(), b"first image")


class TestAiAndImages(ApiTestCase):
    def test_missing_provider_key_is_502(self):
        response = self.client.post("/api/parse", json={"text": "2 rotis and dal"})
        self.assert_error(response, 502, "OPENROUTER_API_KEY is not configured")

    def test_disabled_image_generation_is_503(self):
        self.set_settings(local_image_generation_enabled=False)
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl of dal"}
        )
        self.assert_error(response, 503, "Local image generation is disabled")

    def test_an_invalid_env_edit_is_a_clear_500(self):
        before = self.env_file.stat().st_mtime_ns
        self.env_file.write_text("LLM_PROVIDER=cloud\n", encoding="utf-8")
        newer = before + 1_000_000
        os.utime(self.env_file, ns=(newer, newer))

        response = self.client.post("/api/parse", json={"text": "dal"})
        self.assert_error(
            response, 500, "The .env file has invalid settings; check the server log"
        )

    def test_editing_the_env_file_applies_to_the_next_request(self):
        before = self.env_file.stat().st_mtime_ns
        self.env_file.write_text(
            "LOCAL_IMAGE_GENERATION_ENABLED=false\n", encoding="utf-8"
        )
        newer = before + 1_000_000
        os.utime(self.env_file, ns=(newer, newer))

        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl of dal"}
        )
        self.assert_error(response, 503, "Local image generation is disabled")


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class TestProviderTransport(ApiTestCase):
    """The routes use the shared async client with a stubbed provider."""

    def setUp(self):
        self.calls = 0
        self.statuses = []
        self.http_transport = httpx.MockTransport(self.handle)
        self.retry_delays = (0.0, 0.0)
        super().setUp()
        self.set_settings(
            llm_provider="local",
            llm_base_url="http://model.test/v1",
            llm_model="stub",
            local_image_generation_enabled=True,
            local_image_api_url="http://images.test/txt2img",
        )

    def handle(self, request):
        self.calls += 1
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return httpx.Response(status)
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps({"items": [{
                    "name": "Dal", "portion": "1 bowl", "calories": 150,
                    "protein": 9, "carbs": 20, "fat": 4,
                }]})}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            })
        encoded = base64.b64encode(b"fake png").decode()
        return httpx.Response(200, json={"images": [encoded]})

    def test_transient_provider_failure_is_retried(self):
        self.statuses = [500, 200]
        response = self.client.post("/api/parse", json={"text": "dal"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["name"], "Dal")
        self.assertEqual(self.calls, 2)

    def test_429_is_retried(self):
        self.statuses = [429, 200]
        response = self.client.post("/api/parse", json={"text": "dal"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, 2)

    def test_other_4xx_is_not_retried(self):
        self.statuses = [400]
        response = self.client.post("/api/parse", json={"text": "dal"})
        self.assert_error(response, 502, "Local model returned HTTP 400")
        self.assertEqual(self.calls, 1)

    def test_three_total_attempts_then_502(self):
        self.statuses = [500, 503, 500]
        response = self.client.post("/api/parse", json={"text": "dal"})
        self.assert_error(response, 502, "Local model returned HTTP 500")
        self.assertEqual(self.calls, 3)

    def test_image_retries_transient_failures(self):
        self.statuses = [503, 200]
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.json()["image"], IMAGE_URL_REGEX)
        self.assertEqual(self.calls, 2)

    def test_image_fails_after_three_attempts(self):
        self.statuses = [500, 500, 500]
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl"}
        )
        self.assert_error(response, 503, "Recipe image could not be generated")
        self.assertEqual(self.calls, 3)


def complete_recipe(steps=5, **overrides):
    """One sound recipe, as the model is asked to shape it."""
    recipe = {
        "title": "Dal",
        "description": "A bowl",
        "steps": [f"Step {i}" for i in range(steps)],
        "nutrition": {"calories": 300, "protein": 12, "carbs": 40, "fat": 8},
        "servings": 2,
        "ingredients_used": ["dal"],
        "pantry_extras": [],
    }
    recipe.update(overrides)
    return recipe


def complete_answer(recipe=None):
    recipe = complete_recipe() if recipe is None else recipe
    return {"recipes": [recipe for _ in range(RECIPE_COUNT)]}


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class TestRecipeRules(unittest.TestCase):
    """The shape check that decides whether a recipe answer is usable."""

    def recipe(self, steps=5, **overrides):
        return complete_recipe(steps, **overrides)

    def test_a_complete_answer_has_no_shortcomings(self):
        self.assertIsNone(recipes.recipe_shortcomings(complete_answer()))

    def test_the_wrong_number_of_recipes_is_a_shortcoming(self):
        for count in (0, 1, 2, 4):
            with self.subTest(count=count):
                problem = recipes.recipe_shortcomings(
                    {"recipes": [self.recipe() for _ in range(count)]}
                )
                self.assertIn(f"{count} recipes", problem)

    def test_collapsed_steps_are_a_shortcoming(self):
        rows = [self.recipe() for _ in range(2)] + [self.recipe(steps=2)]
        self.assertIn("usable steps", recipes.recipe_shortcomings({"recipes": rows}))

    def test_missing_pieces_are_shortcomings(self):
        self.assertIn("no recipe list", recipes.recipe_shortcomings({"recipes": "three"}))
        self.assertIn("no recipe list", recipes.recipe_shortcomings(None))
        self.assertIn("not an object", recipes.recipe_shortcomings({"recipes": ["Dal", "Rice", "Roti"]}))
        no_steps = {"title": "Dal", "description": "A bowl"}
        self.assertIn("no steps", recipes.recipe_shortcomings({"recipes": [no_steps, self.recipe(), self.recipe()]}))

    def test_missing_title_description_or_nutrition_is_a_shortcoming(self):
        for field, message in (("title", "no title"), ("description", "no description"),
                               ("nutrition", "no nutrition")):
            with self.subTest(field=field):
                broken = self.recipe(**{field: "" if field != "nutrition" else None})
                self.assertIn(message, recipes.recipe_shortcomings(
                    {"recipes": [broken, self.recipe(), self.recipe()]}
                ))

    def test_the_prompt_asks_for_three_sound_recipes(self):
        prompt = recipes.recipe_prompt(["dal", "rice"], "spinach")
        self.assertIn("exactly three", prompt)
        self.assertIn("number of servings", prompt)
        self.assertNotIn("instructions. servings", prompt)


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class TestRecipeRepair(unittest.IsolatedAsyncioTestCase):
    """A malformed answer earns one repair attempt, then the request fails."""

    def setUp(self):
        self._original = recipes.request_ai
        self.addCleanup(setattr, recipes, "request_ai", self._original)
        self.prompts = []

    def answers(self, *replies):
        async def request(prompt, env, system_prompt, transport, **kwargs):
            self.prompts.append(prompt)
            return replies[len(self.prompts) - 1]
        recipes.request_ai = request

    async def test_a_sound_first_answer_is_not_repaired(self):
        self.answers(complete_answer())
        result = await recipes.suggest_recipes(
            ["dal"], "", Settings(_env_file=None), transport=None
        )
        self.assertEqual(len(self.prompts), 1)
        self.assertEqual(len(result["recipes"]), RECIPE_COUNT)

    async def test_a_bad_first_answer_is_repaired_once(self):
        self.answers(complete_answer(complete_recipe(steps=2)), complete_answer())
        result = await recipes.suggest_recipes(
            ["dal"], "", Settings(_env_file=None), transport=None
        )
        self.assertEqual(len(self.prompts), 2)
        self.assertIn("rejected", self.prompts[1])
        self.assertEqual(len(result["recipes"]), RECIPE_COUNT)

    async def test_a_bad_second_answer_fails_closed(self):
        self.answers(complete_answer(complete_recipe(steps=2)),
                     complete_answer(complete_recipe(steps=2)))
        with self.assertRaisesRegex(RuntimeError, "complete recipes"):
            await recipes.suggest_recipes(
                ["dal"], "", Settings(_env_file=None), transport=None
            )
        self.assertEqual(len(self.prompts), 2)


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class TestMealItemRules(unittest.TestCase):
    """Model output is trimmed to what the store will accept."""

    def test_long_names_and_portions_are_cut_to_store_limits(self):
        items = nutrition.meal_items_from({"items": [{
            "name": "n" * 300,
            "portion": "p" * 300,
            "calories": 100, "protein": 1, "carbs": 2, "fat": 3,
        }]})
        self.assertEqual(len(items[0]["name"]), store.MAX_NAME_LENGTH)
        self.assertEqual(len(items[0]["portion"]), store.MAX_PORTION_LENGTH)
        # What the parser emits must pass the store's own validation.
        store.normalize_entry({**items[0], "meal": "lunch", "date": "2026-10-26"})

    def test_a_missing_portion_is_empty(self):
        items = nutrition.meal_items_from({"items": [{
            "name": "Dal", "calories": 150, "protein": 9, "carbs": 20, "fat": 4,
        }]})
        self.assertEqual(items[0]["portion"], "")

    def test_a_non_string_portion_is_ignored(self):
        items = nutrition.meal_items_from({"items": [{
            "name": "Dal", "portion": 2, "calories": 150, "protein": 9, "carbs": 20, "fat": 4,
        }]})
        self.assertEqual(items[0]["portion"], "")

    def test_empty_and_oversized_answers_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "did not find any food"):
            nutrition.meal_items_from({"items": []})
        with self.assertRaisesRegex(RuntimeError, "too many"):
            nutrition.meal_items_from({"items": [{"name": "Dal"}] * (MAX_MEAL_ITEMS + 1)})


if __name__ == "__main__":
    unittest.main()
