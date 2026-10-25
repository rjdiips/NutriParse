#!/usr/bin/env python3
"""Tests for the shared journal store.

The store is the one place where the CLI and the web API meet, so its rules are
worth pinning down: what counts as a valid entry, what happens to a file that
cannot be parsed, and whether two callers writing at once can lose a row.

Run them with:  python -m unittest discover -s tests
"""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import store  # noqa: E402 - the repo root has to be importable first


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data.json"
        self.addCleanup(self._tmp.cleanup)

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


class TestLoad(StoreTestCase):
    def test_missing_file_is_an_empty_journal(self):
        document = store.load(self.path)
        self.assertEqual(document["calorie_goal"], store.DEFAULT_GOAL)
        self.assertEqual(document["entries"], [])

    def test_sparse_document_gets_defaults(self):
        self.path.write_text(json.dumps({"entries": []}), encoding="utf-8")
        self.assertEqual(store.load(self.path)["calorie_goal"], store.DEFAULT_GOAL)

    def test_legacy_entries_are_kept_verbatim(self):
        legacy = {"id": 1750000000.5, "name": "Dal", "calories": 150, "meal": "lunch",
                  "date": "2026-10-20", "protein": 9, "carbs": 20, "fat": 4}
        self.path.write_text(json.dumps({"calorie_goal": 1800, "entries": [legacy]}),
                             encoding="utf-8")
        document = store.load(self.path)
        self.assertEqual(document["calorie_goal"], 1800)
        self.assertEqual(document["entries"], [legacy])

    def test_corrupt_file_raises_instead_of_resetting(self):
        self.path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(store.StoreError):
            store.load(self.path)
        # The unreadable file is left alone so nothing is lost silently.
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{ not json")

    def test_non_document_json_raises(self):
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(store.StoreError):
            store.load(self.path)

    def test_entries_of_the_wrong_type_raises(self):
        self.path.write_text(json.dumps({"entries": "nope"}), encoding="utf-8")
        with self.assertRaises(store.StoreError):
            store.load(self.path)

    def test_nonsense_goal_falls_back_to_the_default(self):
        self.path.write_text(json.dumps({"calorie_goal": "lots", "entries": []}),
                             encoding="utf-8")
        self.assertEqual(store.load(self.path)["calorie_goal"], store.DEFAULT_GOAL)


class TestAddEntries(StoreTestCase):
    def test_add_returns_the_whole_document(self):
        document = store.add_entries(self.path, [self.entry()])
        self.assertEqual(len(document["entries"]), 1)
        self.assertEqual(document["entries"][0]["name"], "Roti (whole wheat)")
        self.assertEqual(document["calorie_goal"], store.DEFAULT_GOAL)

    def test_the_store_owns_the_id(self):
        document = store.add_entries(self.path, [self.entry(id="client-supplied")])
        self.assertNotEqual(document["entries"][0]["id"], "client-supplied")
        self.assertEqual(len(document["entries"][0]["id"]), 12)

    def test_ids_are_unique(self):
        document = store.add_entries(self.path, [self.entry() for _ in range(20)])
        ids = {row["id"] for row in document["entries"]}
        self.assertEqual(len(ids), 20)

    def test_entries_persist_across_calls(self):
        store.add_entries(self.path, [self.entry()])
        store.add_entries(self.path, [self.entry(name="Dal")])
        document = store.load(self.path)
        self.assertEqual([row["name"] for row in document["entries"]],
                         ["Roti (whole wheat)", "Dal"])

    def test_names_are_trimmed(self):
        document = store.add_entries(self.path, [self.entry(name="  Paneer  ")])
        self.assertEqual(document["entries"][0]["name"], "Paneer")

    def test_macros_are_optional(self):
        document = store.add_entries(self.path, [{
            "name": "Black coffee", "calories": 5, "meal": "snack", "date": "2026-10-21",
        }])
        row = document["entries"][0]
        self.assertEqual((row["protein"], row["carbs"], row["fat"]), (0.0, 0.0, 0.0))

    def test_portion_is_stored(self):
        document = store.add_entries(self.path, [self.entry(portion="2 rotis")])
        self.assertEqual(document["entries"][0]["portion"], "2 rotis")

    def test_portion_is_optional(self):
        document = store.add_entries(self.path, [self.entry()])
        self.assertEqual(document["entries"][0]["portion"], "")

    def test_portion_is_trimmed(self):
        document = store.add_entries(self.path, [self.entry(portion="  1 cup  ")])
        self.assertEqual(document["entries"][0]["portion"], "1 cup")

    def test_macros_are_rounded(self):
        document = store.add_entries(self.path, [self.entry(protein=3.14159)])
        self.assertEqual(document["entries"][0]["protein"], 3.1)

    def test_a_write_stamps_the_document(self):
        document = store.add_entries(self.path, [self.entry()])
        self.assertIn("updated_at", document)
        self.assertIn("updated_at", json.loads(self.path.read_text(encoding="utf-8")))

    def test_no_temp_files_are_left_behind(self):
        store.add_entries(self.path, [self.entry()])
        leftovers = [item.name for item in self.path.parent.iterdir() if item.name != self.path.name]
        self.assertEqual(leftovers, [])


class TestValidation(StoreTestCase):
    def assert_rejected(self, entry, message_fragment):
        with self.assertRaises(store.StoreError) as caught:
            store.add_entries(self.path, [entry])
        self.assertIn(message_fragment, str(caught.exception))
        self.assertFalse(self.path.exists(), "a rejected write must not touch the file")

    def test_empty_write_is_rejected(self):
        with self.assertRaises(store.StoreError):
            store.add_entries(self.path, [])

    def test_named_errors(self):
        self.assert_rejected(self.entry(name="   "), "food name")
        self.assert_rejected(self.entry(name="x" * 200), "120 characters")
        self.assert_rejected(self.entry(meal="brunch"), "Meal must be one of")
        self.assert_rejected(self.entry(date="21-10-2026"), "YYYY-MM-DD")
        self.assert_rejected(self.entry(date=20261021), "text in YYYY-MM-DD")
        self.assert_rejected(self.entry(calories=-5), "0 or more")
        self.assert_rejected(self.entry(calories=None), "must be a number")
        self.assert_rejected(self.entry(calories="lots"), "must be a number")
        self.assert_rejected(self.entry(calories=True), "must be a number")
        self.assert_rejected("Roti", "must be an object")

    def test_portion_rules(self):
        self.assert_rejected(self.entry(portion="x" * 121), "120 characters")
        self.assert_rejected(self.entry(portion=2), "Portion must be text")

    def test_nan_is_rejected(self):
        with self.assertRaises(store.StoreError):
            store.add_entries(self.path, [self.entry(calories=float("nan"))])

    def test_a_batch_can_be_capped(self):
        rows = [self.entry() for _ in range(store.MAX_ENTRIES_PER_WRITE + 1)]
        with self.assertRaises(store.StoreError):
            store.add_entries(self.path, rows)

    def test_a_batch_validates_before_writing(self):
        with self.assertRaises(store.StoreError):
            store.add_entries(self.path, [self.entry(), self.entry(meal="brunch")])
        self.assertFalse(self.path.exists())


class TestGoal(StoreTestCase):
    def test_goal_rounds_to_a_whole_number(self):
        document = store.set_goal(self.path, 2150.6)
        self.assertEqual(document["calorie_goal"], 2151)

    def test_goal_bounds(self):
        for value in (0, -10, store.MAX_GOAL + 1, "2000", None):
            with self.assertRaises(store.StoreError):
                store.set_goal(self.path, value)

    def test_setting_a_goal_keeps_entries(self):
        store.add_entries(self.path, [self.entry()])
        document = store.set_goal(self.path, 1800)
        self.assertEqual(document["calorie_goal"], 1800)
        self.assertEqual(len(document["entries"]), 1)


class TestDelete(StoreTestCase):
    def test_delete_removes_only_the_named_entry(self):
        document = store.add_entries(self.path, [self.entry(name="Roti"), self.entry(name="Dal")])
        target = document["entries"][0]["id"]
        document = store.delete_entry(self.path, target)
        self.assertEqual([row["name"] for row in document["entries"]], ["Dal"])
        self.assertEqual(store.load(self.path)["entries"], document["entries"])

    def test_delete_accepts_a_legacy_numeric_id(self):
        self.path.write_text(json.dumps({
            "calorie_goal": 2000,
            "entries": [{"id": 1750000000.5, "name": "Dal", "calories": 150, "protein": 9,
                         "carbs": 20, "fat": 4, "meal": "lunch", "date": "2026-10-20"}],
        }), encoding="utf-8")
        document = store.delete_entry(self.path, 1750000000.5)
        self.assertEqual(document["entries"], [])

    def test_deleting_a_missing_entry_is_an_error(self):
        store.add_entries(self.path, [self.entry()])
        with self.assertRaises(store.EntryNotFound):
            store.delete_entry(self.path, "not-a-real-id")


class TestUpdate(StoreTestCase):
    def test_update_changes_fields_and_keeps_the_id(self):
        document = store.add_entries(self.path, [self.entry()])
        target = document["entries"][0]["id"]
        updated = store.update_entry(self.path, target, [
            self.entry(name="Dal", calories=150, portion="1 bowl"),
        ])
        self.assertEqual(len(updated["entries"]), 1)
        row = updated["entries"][0]
        self.assertEqual(row["id"], target)
        self.assertEqual((row["name"], row["calories"], row["portion"]),
                         ("Dal", 150.0, "1 bowl"))

    def test_update_can_turn_one_row_into_several(self):
        document = store.add_entries(self.path, [
            self.entry(name="Roti"), self.entry(name="Dal"),
        ])
        target = document["entries"][0]["id"]
        updated = store.update_entry(self.path, target, [
            self.entry(name="Roti"), self.entry(name="Ghee"),
        ])
        self.assertEqual([row["name"] for row in updated["entries"]],
                         ["Roti", "Ghee", "Dal"])
        self.assertEqual(updated["entries"][0]["id"], target)
        self.assertEqual(len({row["id"] for row in updated["entries"]}), 3)

    def test_update_of_a_missing_entry_is_an_error(self):
        store.add_entries(self.path, [self.entry()])
        with self.assertRaises(store.EntryNotFound):
            store.update_entry(self.path, "not-a-real-id", [self.entry()])

    def test_update_rejects_an_empty_list(self):
        document = store.add_entries(self.path, [self.entry()])
        target = document["entries"][0]["id"]
        with self.assertRaises(store.StoreError):
            store.update_entry(self.path, target, [])

    def test_update_validates_before_writing(self):
        document = store.add_entries(self.path, [self.entry()])
        target = document["entries"][0]["id"]
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(store.StoreError):
            store.update_entry(self.path, target, [self.entry(meal="brunch")])
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_update_does_not_duplicate_the_row(self):
        document = store.add_entries(self.path, [self.entry()])
        target = document["entries"][0]["id"]
        store.update_entry(self.path, target, [self.entry(name="Dal")])
        self.assertEqual(len(store.load(self.path)["entries"]), 1)


class TestConcurrentWrites(StoreTestCase):
    def test_parallel_adds_keep_every_entry(self):
        errors = []

        def writer(index):
            try:
                store.add_entries(self.path, [self.entry(name=f"Row {index}")])
            except Exception as error:  # noqa: BLE001 - reported through the assertion below
                errors.append(error)

        threads = [threading.Thread(target=writer, args=(index,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        document = store.load(self.path)
        self.assertEqual(len(document["entries"]), 12)
        self.assertEqual(len({row["id"] for row in document["entries"]}), 12)


class TestTotals(StoreTestCase):
    def test_totals_cover_one_day(self):
        rows = [
            self.entry(date="2026-10-21", calories=110, protein=3, carbs=22, fat=0.5),
            self.entry(date="2026-10-21", calories=150, protein=9, carbs=20, fat=4),
            self.entry(date="2026-10-20", calories=999),
        ]
        totals = store.totals_for_date(rows, "2026-10-21")
        self.assertEqual(totals["calories"], 260)
        self.assertEqual(totals["protein"], 12)
        self.assertEqual(totals["count"], 2)

    def test_totals_ignore_junk_values(self):
        totals = store.totals_for_date([{"date": "2026-10-21", "calories": "many"}], "2026-10-21")
        self.assertEqual(totals["calories"], 0)
        self.assertEqual(totals["count"], 1)

    def test_days_are_listed_newest_first(self):
        rows = [self.entry(date=day) for day in ("2026-10-18", "2026-10-21", "2026-10-18")]
        self.assertEqual(store.day_list(rows), ["2026-10-21", "2026-10-18"])


if __name__ == "__main__":
    unittest.main()
