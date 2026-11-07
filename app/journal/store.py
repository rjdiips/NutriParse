#!/usr/bin/env python3
"""The journal store: one JSON document and one set of rules.

The web app's HTTP API (``app.web``) reads and writes ``data.json`` through this
module, so the Compose view and the Food Journal share one store instead of
keeping separate ones.

Every write validates the incoming entries, re-reads the document, applies the
change, and swaps the new file in atomically through os.replace. That means a
crash mid-write cannot leave a half-written journal behind.

Writers are serialised twice: a thread lock covers requests inside one server
process, and a sidecar lock file (``data.json.lock``) covers separate processes
such as two Uvicorn workers. Readers stay lock-free because ``os.replace`` only
ever exposes a complete document.
"""

import json
import math
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PATH = BASE_DIR / "data.json"
DEFAULT_GOAL = 2000
MAX_GOAL = 20000
MAX_ENTRIES_PER_WRITE = 50
MAX_NAME_LENGTH = 120
MAX_PORTION_LENGTH = 120
MEALS = ("breakfast", "lunch", "dinner", "snack")

# One process can serve several requests at once, so read-modify-write cycles
# are serialised here. The sidecar file lock below covers a second process.
_LOCK = threading.Lock()
LOCK_TIMEOUT = 10.0


class StoreError(Exception):
    """The store is unreadable, or a write to it would be invalid."""


class EntryNotFound(StoreError):
    """The entry a caller asked to delete is not in the store."""


class StoreBusy(StoreError):
    """Another process held the write lock longer than LOCK_TIMEOUT."""


def number(value, default=0.0):
    """Best-effort numeric read of a value that came from a file we did not write.

    Shared with ``evals/run_parse_eval.py``, which grades whatever a model
    returned before any of it reaches the store.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    return value if math.isfinite(value) else default


def _lock_windows(handle, timeout):
    import msvcrt

    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise StoreBusy("The journal is busy; try again.") from None
            time.sleep(0.05)


def _lock_posix(handle, timeout):
    import fcntl

    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise StoreBusy("The journal is busy; try again.") from None
            time.sleep(0.05)


def _unlock(handle):
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def _file_lock(path, timeout=LOCK_TIMEOUT):
    """Serialise writers across processes with a sidecar lock file."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            _lock_windows(handle, timeout)
        else:
            _lock_posix(handle, timeout)
        yield
    finally:
        _unlock(handle)
        handle.close()


def _read_text(path, attempts=8, delay=0.05):
    """Read the journal, retrying the brief window when Windows holds the file."""
    for attempt in range(attempts):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _replace(source, destination, attempts=8, delay=0.05):
    """Swap the file in, retrying the brief window when Windows holds it open."""
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


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

    portion = raw.get("portion", "")
    if not isinstance(portion, str):
        raise StoreError("Portion must be text.")
    portion = portion.strip()
    if len(portion) > MAX_PORTION_LENGTH:
        raise StoreError(f"Portions must be {MAX_PORTION_LENGTH} characters or fewer.")

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
        "portion": portion,
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
        raw = json.loads(_read_text(path))
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
        _replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return payload


def _validated_batch(entries):
    """Validate a caller's rows before anything touches the file."""
    if not isinstance(entries, list) or not entries:
        raise StoreError("Send at least one entry.")
    if len(entries) > MAX_ENTRIES_PER_WRITE:
        raise StoreError(f"At most {MAX_ENTRIES_PER_WRITE} entries can be written at once.")
    return [normalize_entry(entry) for entry in entries]


def add_entries(path, entries):
    """Append validated entries and return the whole updated document."""
    validated = _validated_batch(entries)
    with _LOCK, _file_lock(path):
        document = load(path)
        document["entries"] = document["entries"] + validated
        return _write(path, document)


def update_entry(path, entry_id, entries):
    """Replace one entry with the given rows and return the whole document.

    The first new row keeps the original id, so a caller can treat this as an
    edit even when the user added or merged rows while editing.
    """
    validated = _validated_batch(entries)
    wanted = str(entry_id)
    with _LOCK, _file_lock(path):
        document = load(path)
        index = next(
            (i for i, entry in enumerate(document["entries"]) if str(entry.get("id")) == wanted),
            None,
        )
        if index is None:
            raise EntryNotFound("That entry is no longer in the journal.")
        existing_id = document["entries"][index].get("id")
        if existing_id is not None:
            validated[0]["id"] = existing_id
        document["entries"][index:index + 1] = validated
        return _write(path, document)


def delete_entry(path, entry_id):
    """Remove one entry by id and return the whole updated document."""
    wanted = str(entry_id)
    with _LOCK, _file_lock(path):
        document = load(path)
        remaining = [entry for entry in document["entries"] if str(entry.get("id")) != wanted]
        if len(remaining) == len(document["entries"]):
            raise EntryNotFound("That entry is no longer in the journal.")
        document["entries"] = remaining
        return _write(path, document)


def set_goal(path, goal):
    """Set the daily calorie goal and return the whole updated document."""
    value = _clean_goal(goal)
    with _LOCK, _file_lock(path):
        document = load(path)
        document["calorie_goal"] = value
        return _write(path, document)
