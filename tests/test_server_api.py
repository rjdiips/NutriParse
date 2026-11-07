#!/usr/bin/env python3
"""Tests for the FastAPI surface.

The web app's contract is mostly status codes and one response shape, because
both front ends read `payload.error` and otherwise expect a whole journal
document. These tests pin that contract down: the route allowlist, the journal
round trip, the body rules, and the same-origin check on writes.

Run them with:  python -m unittest discover -s tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from fastapi.testclient import TestClient

    from app.config import MAX_MEAL_ITEMS, MAX_REQUEST_BYTES, RECIPE_COUNT, env_file_mtime
    from app.journal import store
    from app.main import app
    from app.services import nutrition, recipes
    from app.web.routers import ai, images
except Exception as error:  # pragma: no cover - only without the API dependencies
    TestClient = None
    SKIP_REASON = f"API dependencies are unavailable: {error}"


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self._previous = (
            app.state.store_path,
            app.state.env,
            app.state.env_mtime,
        )
        self.addCleanup(self._restore_state)

        app.state.store_path = Path(self._tmp.name) / "data.json"
        app.state.env = {}
        # Pin the mtime so a request does not treat the real .env as a change.
        app.state.env_mtime = env_file_mtime()
        self.client = TestClient(app, base_url="http://localhost:8100")

    def _restore_state(self):
        (app.state.store_path,
         app.state.env,
         app.state.env_mtime) = self._previous

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
        schema = app.openapi()
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
        schema = app.openapi()
        for path, method in (
            ("/api/parse", "post"),
            ("/api/leftover-alchemist", "post"),
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
        self.assertFalse(Path(app.state.store_path).exists())

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
        Path(app.state.store_path).write_text("{ not json", encoding="utf-8")
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
        Path(app.state.store_path).write_text(json.dumps({
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
        ai.parse_meal = lambda text, env: {
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
        ai.suggest_recipes = lambda ingredients, use_soon, env: {
            "recipes": [recipe, recipe, recipe],
            "meta": {
                "provider": "local", "model": "test", "elapsed_ms": 5,
                "prompt_tokens": 10, "completion_tokens": 20,
            },
        }
        response = self.client.post(
            "/api/leftover-alchemist", json={"ingredients": "dal", "use_soon": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["recipes"]), RECIPE_COUNT)

    def test_image_success_matches_the_response_model(self):
        original = images.generate_local_recipe_image
        self.addCleanup(setattr, images, "generate_local_recipe_image", original)
        images.generate_local_recipe_image = (
            lambda recipe, endpoint, env: "data:image/png;base64,AAAA"
        )
        app.state.env = {
            "LOCAL_IMAGE_GENERATION_ENABLED": "true",
            "LOCAL_IMAGE_API_URL": "http://127.0.0.1:7860/sdapi/v1/txt2img",
        }
        app.state.env_mtime = env_file_mtime()
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["image"], "data:image/png;base64,AAAA")


class TestAiAndImages(ApiTestCase):
    def test_missing_provider_key_is_502(self):
        response = self.client.post("/api/parse", json={"text": "2 rotis and dal"})
        self.assert_error(response, 502, "OPENROUTER_API_KEY is not configured")

    def test_disabled_image_generation_is_503(self):
        app.state.env = {"LOCAL_IMAGE_GENERATION_ENABLED": "false"}
        app.state.env_mtime = env_file_mtime()
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl of dal"}
        )
        self.assert_error(response, 503, "Local image generation is disabled")


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
class TestRecipeRepair(unittest.TestCase):
    """A malformed answer earns one repair attempt, then the request fails."""

    def setUp(self):
        self._original = recipes.request_ai
        self.addCleanup(setattr, recipes, "request_ai", self._original)
        self.prompts = []

    def answers(self, *replies):
        def request(prompt, env, system_prompt, **kwargs):
            self.prompts.append(prompt)
            return replies[len(self.prompts) - 1]
        recipes.request_ai = request

    def test_a_sound_first_answer_is_not_repaired(self):
        self.answers(complete_answer())
        result = recipes.suggest_recipes(["dal"], "", {})
        self.assertEqual(len(self.prompts), 1)
        self.assertEqual(len(result["recipes"]), RECIPE_COUNT)

    def test_a_bad_first_answer_is_repaired_once(self):
        self.answers(complete_answer(complete_recipe(steps=2)), complete_answer())
        result = recipes.suggest_recipes(["dal"], "", {})
        self.assertEqual(len(self.prompts), 2)
        self.assertIn("rejected", self.prompts[1])
        self.assertEqual(len(result["recipes"]), RECIPE_COUNT)

    def test_a_bad_second_answer_fails_closed(self):
        self.answers(complete_answer(complete_recipe(steps=2)),
                     complete_answer(complete_recipe(steps=2)))
        with self.assertRaisesRegex(RuntimeError, "complete recipes"):
            recipes.suggest_recipes(["dal"], "", {})
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
