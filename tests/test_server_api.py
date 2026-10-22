#!/usr/bin/env python3
"""Tests for the FastAPI surface.

The web app's contract is mostly status codes and one response shape, because
both front ends read `payload.error` and otherwise expect a whole journal
document. These tests pin that contract down: the route allowlist, the journal
round trip, the body rules, and the same-origin check on writes.

Run them with:  python -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from fastapi.testclient import TestClient

    import server
except Exception as error:  # pragma: no cover - only without the API dependencies
    TestClient = None
    SKIP_REASON = f"API dependencies are unavailable: {error}"


@unittest.skipUnless(TestClient is not None, globals().get("SKIP_REASON", ""))
class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self._previous = (
            server.app.state.store_path,
            server.app.state.env,
            server.app.state.env_mtime,
        )
        self.addCleanup(self._restore_state)

        server.app.state.store_path = Path(self._tmp.name) / "data.json"
        server.app.state.env = {}
        # Pin the mtime so a request does not treat the real .env as a change.
        server.app.state.env_mtime = server.env_file_mtime()
        self.client = TestClient(server.app, base_url="http://localhost:8100")

    def _restore_state(self):
        (server.app.state.store_path,
         server.app.state.env,
         server.app.state.env_mtime) = self._previous

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
    def test_public_files_are_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))

        script = self.client.get("/compose.js")
        self.assertEqual(script.status_code, 200)
        self.assertTrue(script.headers["content-type"].startswith("text/javascript"))

    def test_private_files_are_not_reachable(self):
        for path in ("/server.py", "/.env", "/store.py", "/data.json"):
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

    def test_cross_origin_writes_are_refused(self):
        response = self.client.post(
            "/api/journal/goal",
            json={"calorie_goal": 2200},
            headers={"Origin": "https://evil.example"},
        )
        self.assert_error(response, 403, "Journal writes must come from the NutriParse app")
        self.assertFalse(Path(server.app.state.store_path).exists())

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
        Path(server.app.state.store_path).write_text("{ not json", encoding="utf-8")
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
        body = b'{"text":"' + b"a" * server.MAX_REQUEST_BYTES + b'"}'
        response = self.client.post(
            "/api/parse", content=body, headers={"Content-Type": "application/json"}
        )
        self.assert_error(response, 413, "Request body is too large")

    def test_blank_meal_is_400(self):
        response = self.client.post("/api/parse", json={"text": "   "})
        self.assert_error(response, 400, "Describe at least one food")

    def test_blank_food_name_is_400(self):
        response = self.client.post("/api/suggest", json={"name": " ", "portion": ""})
        self.assert_error(response, 400, "A food name is required")

    def test_unknown_route_is_404(self):
        self.assert_error(self.client.get("/api/nope"), 404, "Not Found")


class TestAiAndImages(ApiTestCase):
    def test_missing_provider_key_is_502(self):
        response = self.client.post("/api/parse", json={"text": "2 rotis and dal"})
        self.assert_error(response, 502, "OPENROUTER_API_KEY is not configured")

    def test_disabled_image_generation_is_503(self):
        server.app.state.env = {"LOCAL_IMAGE_GENERATION_ENABLED": "false"}
        server.app.state.env_mtime = server.env_file_mtime()
        response = self.client.post(
            "/api/recipe-image", json={"title": "Dal", "description": "A bowl of dal"}
        )
        self.assert_error(response, 503, "Local image generation is disabled")


if __name__ == "__main__":
    unittest.main()
