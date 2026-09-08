"""First-run seed data for a fresh KitchenHQ database.

seed_if_empty() only touches a table when it is completely empty, so it is safe to
call on every startup and it never fights the agent once real data exists.
"""

from __future__ import annotations

import json
import sqlite3

# weekly_menu.full_recipe is a JSON string array of short plain-text lines. Every
# seeded dish uses this same generic method.
_SEED_RECIPE_STEPS = [
    "Wash and prepare every ingredient, then measure the spices and liquids into separate bowls.",
    "Heat a wide pan over medium heat and add the oil. Add the aromatics and cook for 2 minutes until fragrant.",
    "Add the main ingredients and cook for 5 minutes, stirring often so the edges colour evenly.",
    "Add the grains, sauce, or liquid, reduce the heat, cover, and cook for 10 minutes until tender.",
    "Remove the lid, taste, and adjust salt, acidity, and seasoning. Rest for 2 minutes.",
    "Plate while warm, finish with the fresh garnish, and serve immediately.",
]

# (item_name, category, quantity, unit, minimum_threshold)
_SEED_INVENTORY = [
    ("Baby spinach", "Fresh", 2, "bags", 1),
    ("Paneer", "Dairy", 450, "g", 250),
    ("Brown rice", "Pantry", 1.8, "kg", 1),
    ("Cherry tomatoes", "Fresh", 350, "g", 200),
    ("Eggs", "Proteins", 10, "pcs", 6),
    ("Greek yogurt", "Dairy", 700, "g", 300),
]

# day -> list of (meal_type, dish_name, macros, comma-separated ingredients)
_SEED_MENU: dict[str, list[tuple[str, str, str, str]]] = {
    "monday": [
        ("Breakfast", "Spinach masala eggs", "26g protein  /  18g carbs  /  20g fat", "Eggs, baby spinach, tomatoes"),
        ("Lunch", "Paneer tikka bowls", "32g protein  /  48g carbs  /  18g fat", "Paneer, brown rice, spinach, yogurt"),
        ("Snack", "Yogurt fruit crunch", "18g protein  /  26g carbs  /  8g fat", "Greek yogurt, banana, seeds"),
        ("Dinner", "Lemon herb rice skillet", "24g protein  /  52g carbs  /  14g fat", "Brown rice, spinach, yogurt"),
    ],
    "tuesday": [
        ("Breakfast", "Savory paneer toast", "29g protein  /  31g carbs  /  16g fat", "Paneer, wholegrain bread, tomatoes"),
        ("Lunch", "Paneer tomato rice bowl", "28g protein  /  46g carbs  /  16g fat", "Paneer, brown rice, cherry tomatoes, spinach"),
        ("Snack", "Spiced yogurt dip", "14g protein  /  12g carbs  /  7g fat", "Greek yogurt, cucumber, herbs"),
        ("Dinner", "Tikka rice lettuce cups", "30g protein  /  39g carbs  /  15g fat", "Paneer, brown rice, lettuce"),
    ],
    "wednesday": [
        ("Breakfast", "Green breakfast bowl", "22g protein  /  35g carbs  /  12g fat", "Eggs, spinach, brown rice"),
        ("Lunch", "Green goddess rice", "24g protein  /  54g carbs  /  14g fat", "Brown rice, spinach, yogurt"),
        ("Snack", "Tomato paneer skewers", "19g protein  /  14g carbs  /  9g fat", "Paneer, cherry tomatoes, herbs"),
        ("Dinner", "Creamy spinach eggs", "27g protein  /  20g carbs  /  19g fat", "Eggs, spinach, Greek yogurt"),
    ],
    "thursday": [
        ("Breakfast", "Yogurt oat parfait", "20g protein  /  42g carbs  /  10g fat", "Greek yogurt, oats, banana"),
        ("Lunch", "Roasted paneer salad", "35g protein  /  20g carbs  /  21g fat", "Paneer, cherry tomatoes, spinach"),
        ("Snack", "Cucumber raita cup", "12g protein  /  10g carbs  /  5g fat", "Greek yogurt, cucumber, herbs"),
        ("Dinner", "Golden egg rice", "25g protein  /  46g carbs  /  15g fat", "Eggs, brown rice, spinach"),
    ],
    "friday": [
        ("Breakfast", "Paneer breakfast hash", "31g protein  /  34g carbs  /  17g fat", "Paneer, brown rice, tomatoes"),
        ("Lunch", "Paneer spinach wraps", "30g protein  /  36g carbs  /  17g fat", "Paneer, spinach, yogurt, wholegrain wraps"),
        ("Snack", "Cinnamon yogurt bowl", "17g protein  /  24g carbs  /  6g fat", "Greek yogurt, banana, seeds"),
        ("Dinner", "Friday tomato rice", "23g protein  /  55g carbs  /  12g fat", "Brown rice, tomatoes, eggs"),
    ],
    "saturday": [
        ("Breakfast", "Herbed egg scramble", "25g protein  /  16g carbs  /  18g fat", "Eggs, spinach, herbs"),
        ("Lunch", "Paneer rainbow plate", "34g protein  /  32g carbs  /  19g fat", "Paneer, brown rice, tomatoes"),
        ("Snack", "Yogurt cucumber cups", "13g protein  /  11g carbs  /  5g fat", "Greek yogurt, cucumber"),
        ("Dinner", "One-pan spinach pilaf", "21g protein  /  51g carbs  /  13g fat", "Brown rice, spinach, yogurt"),
    ],
    "sunday": [
        ("Breakfast", "Weekend masala omelet", "27g protein  /  14g carbs  /  20g fat", "Eggs, tomatoes, spinach"),
        ("Lunch", "Sunday paneer bowls", "33g protein  /  49g carbs  /  18g fat", "Paneer, brown rice, yogurt"),
        ("Snack", "Fruit and yogurt lassi", "15g protein  /  30g carbs  /  5g fat", "Greek yogurt, banana, herbs"),
        ("Dinner", "Comfort tomato shakshuka", "28g protein  /  24g carbs  /  16g fat", "Eggs, tomatoes, spinach"),
    ],
}


def _ingredients_used(*wants: tuple[str, float, str]) -> str:
    return json.dumps([{"item_name": name, "quantity": quantity, "unit": unit} for name, quantity, unit in wants])


# (trigger_day, trigger_time, task_type, detailed_instructions JSON, ingredients_used JSON)
_SEED_PREP = [
    (
        "monday", "07:30", "Morning prep",
        json.dumps(["Wash the spinach and pat it dry.", "Portion the Greek yogurt into the day's serving bowls."]),
        _ingredients_used(("Baby spinach", 1, "bags"), ("Greek yogurt", 200, "g")),
    ),
    (
        "tuesday", "17:00", "Dinner prep",
        json.dumps(["Dice the cherry tomatoes.", "Press the paneer to remove excess water, then cube it."]),
        _ingredients_used(("Cherry tomatoes", 150, "g"), ("Paneer", 200, "g")),
    ),
    (
        "wednesday", "08:00", "Batch prep",
        json.dumps(["Rinse the brown rice.", "Cook until tender, then spread it in shallow containers to cool quickly."]),
        _ingredients_used(("Brown rice", 0.5, "kg")),
    ),
]


def _is_empty(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def seed_if_empty(connection: sqlite3.Connection) -> None:
    if _is_empty(connection, "inventory"):
        connection.executemany(
            "INSERT INTO inventory (item_name, category, quantity, unit, minimum_threshold) VALUES (?, ?, ?, ?, ?)",
            _SEED_INVENTORY,
        )
    if _is_empty(connection, "weekly_menu"):
        connection.executemany(
            "INSERT OR IGNORE INTO weekly_menu (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    day,
                    meal_type.lower(),
                    dish,
                    1,
                    macros,
                    json.dumps([part.strip() for part in ingredients.split(",") if part.strip()]),
                    json.dumps(_SEED_RECIPE_STEPS),
                )
                for day, meals in _SEED_MENU.items()
                for meal_type, dish, macros, ingredients in meals
            ],
        )
    if _is_empty(connection, "detailed_prep_schedule"):
        connection.executemany(
            "INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used) "
            "VALUES (?, ?, ?, ?, ?)",
            _SEED_PREP,
        )
    connection.execute("INSERT OR IGNORE INTO user_profile (id, name) VALUES (1, 'Alex Kim')")
