import json
import os
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

MEALS = ["breakfast", "lunch", "dinner", "snack"]
MACROS = ["protein", "carbs", "fat"]

SUGGEST_URL = "http://localhost:8000/api/suggest"

CALORIE_GOAL_KEY = "calorie_goal"
ENTRIES_KEY = "entries"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {CALORIE_GOAL_KEY: 2000, ENTRIES_KEY: []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if CALORIE_GOAL_KEY not in data:
            data[CALORIE_GOAL_KEY] = 2000
        if ENTRIES_KEY not in data:
            data[ENTRIES_KEY] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {CALORIE_GOAL_KEY: 2000, ENTRIES_KEY: []}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def prompt_float(prompt_text, allow_empty=False, min_value=0):
    while True:
        raw = input(prompt_text).strip()
        if allow_empty and raw == "":
            return None
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if value < min_value:
            print(f"Value must be at least {min_value}.")
            continue
        return value


def prompt_int(prompt_text, min_value=1):
    while True:
        raw = input(prompt_text).strip()
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if value < min_value:
            print(f"Value must be at least {min_value}.")
            continue
        return value


def prompt_choice(prompt_text, choices):
    choices_lower = [c.lower() for c in choices]
    while True:
        raw = input(f"{prompt_text} ({'/'.join(choices)}): ").strip().lower()
        if raw in choices_lower:
            return choices[choices_lower.index(raw)]
        print(f"Choose one of: {', '.join(choices)}")


def add_entry(data):
    print("\n--- Add Food Entry ---")
    name = input("Food name: ").strip()
    if not name:
        print("Name is required.")
        return
    calories = prompt_float("Calories: ")
    protein = prompt_float("Protein (g): ")
    carbs = prompt_float("Carbs (g): ")
    fat = prompt_float("Fat (g): ")
    meal = prompt_choice("Meal", MEALS)
    date_str = input(f"Date [YYYY-MM-DD, default {date.today().isoformat()}]: ").strip()
    if not date_str:
        date_str = date.today().isoformat()
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("Invalid date format. Using today.")
            date_str = date.today().isoformat()

    entry = {
        "id": datetime.now().timestamp(),
        "name": name,
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "meal": meal,
        "date": date_str,
    }
    data[ENTRIES_KEY].append(entry)
    save_data(data)
    print(f"Added '{name}' ({calories} cal) to {meal} on {date_str}.")


def list_entries(data):
    print("\n--- Recent Entries ---")
    entries = sorted(data[ENTRIES_KEY], key=lambda e: e["date"], reverse=True)
    if not entries:
        print("No entries found.")
        return
    for entry in entries[:20]:
        print(
            f"{entry['date']} | {entry['meal']:9s} | {entry['name']:20s} | "
            f"{entry['calories']:5.0f} cal | P{entry['protein']:.0f}g "
            f"C{entry['carbs']:.0f}g F{entry['fat']:.0f}g"
        )


def delete_entry(data):
    print("\n--- Delete Entry ---")
    entries = sorted(data[ENTRIES_KEY], key=lambda e: e["date"], reverse=True)
    if not entries:
        print("No entries to delete.")
        return
    for i, entry in enumerate(entries, 1):
        print(
            f"{i}. {entry['date']} | {entry['meal']:9s} | {entry['name']:20s} | "
            f"{entry['calories']:5.0f} cal"
        )
    choice = prompt_int("Entry number to delete: ", min_value=1)
    if choice < 1 or choice > len(entries):
        print("Invalid selection.")
        return
    removed = entries.pop(choice - 1)
    data[ENTRIES_KEY] = [e for e in data[ENTRIES_KEY] if e["id"] != removed["id"]]
    save_data(data)
    print(f"Deleted '{removed['name']}'.")


def totals_for_date(entries, target_date):
    day_entries = [e for e in entries if e["date"] == target_date]
    return {
        "calories": sum(e["calories"] for e in day_entries),
        "protein": sum(e["protein"] for e in day_entries),
        "carbs": sum(e["carbs"] for e in day_entries),
        "fat": sum(e["fat"] for e in day_entries),
        "count": len(day_entries),
    }


def summary(data):
    print("\n--- Daily Summary ---")
    goal = data[CALORIE_GOAL_KEY]
    today_obj = date.today()
    today = today_obj.isoformat()
    days = [(today_obj - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    print(f"{'Date':<12} {'Calories':>9} {'Goal':>6} {'P':>5} {'C':>5} {'F':>5}")
    for d in days:
        t = totals_for_date(data[ENTRIES_KEY], d)
        mark = " *today" if d == today else ""
        print(
            f"{d}{mark:<7} {t['calories']:>9.0f} {goal:>6.0f} "
            f"{t['protein']:>5.0f} {t['carbs']:>5.0f} {t['fat']:>5.0f}"
        )
    today_totals = totals_for_date(data[ENTRIES_KEY], today)
    remaining = goal - today_totals["calories"]
    print(f"\nToday: {today_totals['calories']:.0f} / {goal:.0f} calories "
          f"({remaining:.0f} remaining)")


def set_goal(data):
    print(f"\nCurrent daily calorie goal: {data[CALORIE_GOAL_KEY]:.0f}")
    goal = prompt_float("New daily calorie goal: ", min_value=1)
    data[CALORIE_GOAL_KEY] = goal
    save_data(data)
    print(f"Daily calorie goal set to {goal:.0f}.")


def suggest_nutrition(name, portion=""):
    body = json.dumps({"name": name, "portion": portion}).encode("utf-8")
    req = urllib.request.Request(
        SUGGEST_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Server returned {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not connect to {SUGGEST_URL}. Is server.py running?"
        ) from e


def ai_suggest(data):
    print("\n--- AI Nutrition Suggest ---")
    name = input("Food name: ").strip()
    if not name:
        print("Name is required.")
        return
    portion = input("Portion (e.g. 1 slice, 100g, 250ml, 1 cup) [optional]: ").strip()
    print("Querying AI...")
    try:
        result = suggest_nutrition(name, portion)
    except RuntimeError as e:
        print(f"Suggestion failed: {e}")
        return
    print(f"\nSuggested for '{result.get('name', name)}':")
    print(f"  Calories: {float(result.get('calories', 0)):.0f}")
    print(f"  Protein:  {float(result.get('protein', 0)):.0f}g")
    print(f"  Carbs:    {float(result.get('carbs', 0)):.0f}g")
    print(f"  Fat:      {float(result.get('fat', 0)):.0f}g")
    use = input("Use these values to add an entry? (y/N): ").strip().lower()
    if use == "y":
        entry = {
            "id": datetime.now().timestamp(),
            "name": result.get("name", name),
            "calories": float(result.get("calories", 0)),
            "protein": float(result.get("protein", 0)),
            "carbs": float(result.get("carbs", 0)),
            "fat": float(result.get("fat", 0)),
            "meal": prompt_choice("Meal", MEALS),
            "date": date.today().isoformat(),
        }
        data[ENTRIES_KEY].append(entry)
        save_data(data)
        print(f"Added '{entry['name']}' ({entry['calories']:.0f} cal).")


def print_menu():
    print("\n=== Calorie Tracker ===")
    print("2. View recent entries")
    print("3. View daily summary")
    print("4. Set daily calorie goal")
    print("5. Delete an entry")
    print("6. Suggest nutrition with AI")
    print("7. Exit")


def main():
    data = load_data()
    while True:
        print_menu()
        choice = input("Choose an option: ").strip()
        if choice == "1":
            add_entry(data)
        elif choice == "2":
            list_entries(data)
        elif choice == "3":
            summary(data)
        elif choice == "4":
            set_goal(data)
        elif choice == "5":
            delete_entry(data)
        elif choice == "6":
            ai_suggest(data)
        elif choice == "7":
            print("Goodbye!")
            break
        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
