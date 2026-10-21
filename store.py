#!/usr/bin/env python3
"""The journal store: one JSON document, one set of rules, two front ends.

The CLI (`nutriparse.py`) and the web app's HTTP API (`server.py`) both read and
write `data.json` through this module, so the two surfaces share one store
instead of keeping separate ones. The server owns the file; the CLI talks to it
directly because it runs on the same machine as the file.

Every write validates the incoming entries, re-reads the document, applies the
change, and swaps the new file in atomically through os.replace. That means a
crash mid-write cannot leave a half-written journal behind.
"""

import json
import math
import os
import tempfile
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "data.json"
DEFAULT_GOAL = 2000
MAX_GOAL = 20000
MAX_ENTRIES_PER_WRITE = 50
MAX_NAME_LENGTH = 120
MEALS = ("breakfast", "lunch", "dinner", "snack")

# One process can serve several requests at once, so read-modify-write cycles
# are serialised here. A second process on the same file is still possible (the
# CLI beside an open browser tab); see the README for what that costs.
_LOCK = threading.Lock()


class StoreError(Exception):
    """The store is unreadable, or a write to it would be invalid."""


class EntryNotFound(StoreError):
    """The entry a caller asked to delete is not in the store."""


def number(value, default=0.0):
    """Best-effort numeric read of a value that came from a file we did not write."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    return value if math.isfinite(value) else default


def _clean_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StoreError(f"{field} must be a number.")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise StoreError(f"{field} must be a number of 0 or more.")
    return round(value, 1)


def _clean_goal(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StoreError("The calorie goal must be a number.")
    value = float(value)
    if not math.isfinite(value) or not 1 <= value <= MAX_GOAL:
        raise StoreError(f"The calorie goal must be between 1 and {MAX_GOAL}.")
    return int(round(value))


def normalize_entry(raw):
    """Validate one entry from a client and give it an id owned by the store."""
    if not isinstance(raw, dict):
        raise StoreError("Each entry must be an object.")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise StoreError("Each entry needs a food name.")
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise StoreError(f"Food names must be {MAX_NAME_LENGTH} characters or fewer.")

    meal = raw.get("meal", "snack")
    if meal not in MEALS:
        raise StoreError(f"Meal must be one of: {', '.join(MEALS)}.")

    day = raw.get("date") or date.today().isoformat()
    if not isinstance(day, str):
        raise StoreError("Date must be text in YYYY-MM-DD form.")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise StoreError("Date must be in YYYY-MM-DD form.") from None

    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "calories": _clean_number(raw.get("calories"), "Calories"),
        "protein": _clean_number(raw.get("protein", 0), "Protein"),
        "carbs": _clean_number(raw.get("carbs", 0), "Carbs"),
        "fat": _clean_number(raw.get("fat", 0), "Fat"),
        "meal": meal,
        "date": day,
    }


def load(path=DEFAULT_PATH):
    """Return the whole journal document with defaults filled in.

    A missing file is an empty journal. A file that exists but cannot be parsed
    raises instead of quietly starting over, so a corrupt store never gets
    overwritten by the next write.
    """
    path = Path(path)
    if not path.exists():
        return {"calorie_goal": DEFAULT_GOAL, "entries": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StoreError(f"{path.name} could not be read: {error}") from error
    if not isinstance(raw, dict):
        raise StoreError(f"{path.name} is not a journal document.")

    entries = raw.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise StoreError(f"{path.name} does not contain a list of entries.")

    document = {"calorie_goal": DEFAULT_GOAL, "entries": entries}
    goal = raw.get("calorie_goal")
    if not isinstance(goal, bool) and isinstance(goal, (int, float)) and math.isfinite(float(goal)):
        document["calorie_goal"] = _clean_goal(goal)
    if isinstance(raw.get("updated_at"), str):
        document["updated_at"] = raw["updated_at"]
    return document


def _write(path, document):
    """Swap a complete document into place, atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(document)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".data-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return payload


def add_entries(path, entries):
    """Append validated entries and return the whole updated document."""
    if not isinstance(entries, list) or not entries:
        raise StoreError("Send at least one entry.")
    if len(entries) > MAX_ENTRIES_PER_WRITE:
        raise StoreError(f"At most {MAX_ENTRIES_PER_WRITE} entries can be added at once.")
    validated = [normalize_entry(entry) for entry in entries]
    with _LOCK:
        document = load(path)
        document["entries"] = document["entries"] + validated
        return _write(path, document)


def delete_entry(path, entry_id):
    """Remove one entry by id and return the whole updated document."""
    wanted = str(entry_id)
    with _LOCK:
        document = load(path)
        remaining = [entry for entry in document["entries"] if str(entry.get("id")) != wanted]
        if len(remaining) == len(document["entries"]):
            raise EntryNotFound("That entry is no longer in the journal.")
        document["entries"] = remaining
        return _write(path, document)


def set_goal(path, goal):
    """Set the daily calorie goal and return the whole updated document."""
    value = _clean_goal(goal)
    with _LOCK:
        document = load(path)
        document["calorie_goal"] = value
        return _write(path, document)


def totals_for_date(entries, target_date):
    """Sum calories and macros for one YYYY-MM-DD day."""
    day = [entry for entry in entries if entry.get("date") == target_date]
    return {
        "calories": sum(number(entry.get("calories")) for entry in day),
        "protein": sum(number(entry.get("protein")) for entry in day),
        "carbs": sum(number(entry.get("carbs")) for entry in day),
        "fat": sum(number(entry.get("fat")) for entry in day),
        "count": len(day),
    }


def day_list(entries):
    """Newest-first list of YYYY-MM-DD days that have entries."""
    return sorted({entry.get("date") for entry in entries if entry.get("date")}, reverse=True)
