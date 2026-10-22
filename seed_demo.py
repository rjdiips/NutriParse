#!/usr/bin/env python3
"""Seed a demo journal for screenshots.

Writes `data.demo.json` — never `data.json` — with a week of plausible entries
anchored to today, so the Journal view has a full today card, history, and a
varied set of days (one over goal, one light) to photograph.

    python seed_demo.py
    python server.py --demo
    http://localhost:8100/?view=journal

Re-run the seed whenever the dates should move up to the current day.
"""

from datetime import date, timedelta
from pathlib import Path

import store

BASE_DIR = Path(__file__).resolve().parent
DEMO_PATH = BASE_DIR / "data.demo.json"
DEMO_GOAL = 2200

# offset from today, then (meal, name, kcal, protein g, carbs g, fat g).
# Totals are roughly consistent with the macros, and the days vary on purpose:
# today sits just under the goal, two days ago runs over it, three days ago is
# a light day. That gives the Journal view several states worth capturing.
WEEK = {
    0: [
        ("breakfast", "Greek yogurt with honey and walnuts", 280, 18, 28, 9),
        ("breakfast", "Flat white", 120, 6, 10, 6),
        ("lunch", "Chicken burrito bowl", 720, 45, 78, 22),
        ("snack", "Apple", 95, 0.5, 25, 0.3),
        ("snack", "Peanut butter, 2 tbsp", 190, 8, 7, 16),
        ("dinner", "Salmon with roasted vegetables", 520, 38, 24, 28),
    ],
    -1: [
        ("breakfast", "Overnight oats with blueberries", 360, 14, 58, 8),
        ("breakfast", "Boiled egg", 70, 6, 1, 5),
        ("lunch", "Turkey and avocado sandwich", 520, 32, 44, 24),
        ("lunch", "Lentil soup", 260, 16, 38, 4),
        ("dinner", "Roasted salmon with rice", 640, 42, 52, 26),
        ("snack", "Dark chocolate, 30 g", 170, 2, 16, 11),
    ],
    -2: [
        ("breakfast", "Masala dosa with sambar", 380, 9, 56, 12),
        ("breakfast", "Filter coffee", 90, 4, 10, 3),
        ("lunch", "Rajma chawal", 620, 22, 96, 14),
        ("lunch", "Cucumber salad", 60, 2, 8, 2),
        ("snack", "Paneer tikka", 430, 24, 12, 31),
        ("snack", "Masala chai", 105, 3, 12, 4),
        ("dinner", "Butter chicken", 380, 26, 12, 25),
        ("dinner", "Two rotis", 280, 8, 52, 6),
        ("snack", "Mango", 150, 1, 38, 0.5),
    ],
    -3: [
        ("breakfast", "Scrambled eggs on toast", 380, 22, 30, 18),
        ("breakfast", "Banana", 105, 1, 27, 0.3),
        ("lunch", "Chicken Caesar salad", 470, 38, 14, 30),
        ("snack", "Greek yogurt", 180, 17, 8, 8),
        ("snack", "Blueberries", 85, 1, 21, 0.5),
        ("snack", "Almonds, 25 g", 165, 6, 6, 14),
    ],
    -4: [
        ("breakfast", "Oatmeal with banana and peanut butter", 480, 16, 62, 18),
        ("breakfast", "Coffee with milk", 45, 2, 4, 2),
        ("lunch", "Tofu vegetable stir-fry", 540, 28, 42, 26),
        ("lunch", "Brown rice", 210, 5, 44, 2),
        ("snack", "Hummus with carrot sticks", 180, 6, 18, 10),
        ("snack", "Whole wheat pita", 165, 6, 33, 2),
        ("dinner", "Grilled chicken breast", 290, 54, 0, 7),
    ],
    -5: [
        ("breakfast", "Berry protein smoothie", 320, 24, 38, 7),
        ("breakfast", "Egg muffin", 240, 14, 18, 12),
        ("lunch", "Salmon sushi, 8 pieces", 480, 24, 68, 10),
        ("lunch", "Miso soup", 60, 4, 6, 2),
        ("snack", "Edamame", 190, 17, 15, 8),
        ("dinner", "Teriyaki chicken", 420, 34, 30, 18),
        ("dinner", "Steamed rice", 210, 5, 44, 2),
    ],
    -6: [
        ("breakfast", "Pancakes with maple syrup", 520, 10, 86, 14),
        ("breakfast", "Bacon, 3 rashers", 180, 12, 1, 14),
        ("lunch", "Cheeseburger", 780, 38, 54, 44),
        ("lunch", "French fries", 360, 4, 48, 16),
        ("snack", "Green salad with vinaigrette", 120, 2, 8, 9),
        ("snack", "Vanilla ice cream", 280, 5, 34, 14),
    ],
}


def build_entries(today=None):
    """Return unvalidated rows dated relative to `today` (local date)."""
    today = today or date.today()
    rows = []
    for offset, items in WEEK.items():
        day = (today + timedelta(days=offset)).isoformat()
        for meal, name, calories, protein, carbs, fat in items:
            rows.append({
                "name": name,
                "calories": calories,
                "protein": protein,
                "carbs": carbs,
                "fat": fat,
                "meal": meal,
                "date": day,
            })
    return rows


def seed(path=DEMO_PATH, today=None):
    """Replace the demo file with a fresh week and return the document."""
    path = Path(path)
    if path.exists():
        path.unlink()

    rows = build_entries(today)
    document = None
    for start in range(0, len(rows), store.MAX_ENTRIES_PER_WRITE):
        document = store.add_entries(path, rows[start:start + store.MAX_ENTRIES_PER_WRITE])
    document = store.set_goal(path, DEMO_GOAL)
    return document


def main():
    document = seed()
    days = len({entry["date"] for entry in document["entries"]})
    print(f"Wrote {len(document['entries'])} entries across {days} days to {DEMO_PATH.name}.")
    print(f"Daily goal: {document['calorie_goal']} kcal")
    print("Next: python server.py --demo, then http://localhost:8100/?view=journal")


if __name__ == "__main__":
    main()
