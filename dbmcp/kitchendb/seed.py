"""First-run seed data for a fresh KitchenHQ database.

seed_if_empty() only touches a table when it is completely empty, so it is safe to
call on every startup and it never fights the agent once real data exists.

The weekly menu, profile, and household members below mirror this household's actual
in-use data (Authentic South Indian, high-protein) rather than generic placeholders,
so a fresh install starts from a realistic, already-useful state.
"""

from __future__ import annotations

import json
import sqlite3

# (item_name, category, quantity, unit, minimum_threshold)
_SEED_INVENTORY = [
    ("Baby spinach", "Fresh", 2, "pcs", 1),
    ("Paneer", "Dairy", 450, "g", 250),
    ("Brown rice", "Pantry", 1.8, "kg", 1),
    ("Cherry tomatoes", "Fresh", 350, "g", 200),
    ("Eggs", "Proteins", 10, "pcs", 6),
    ("Greek yogurt", "Dairy", 700, "g", 300),
]

# day -> list of (meal_type, dish_name, is_kid_friendly, macros, ingredients, full_recipe)
_SEED_MENU: dict[str, list[tuple[str, str, bool, str, list[str], list[str]]]] = {
    "monday": [
        (
            "breakfast", "Moong Dal Chilla (Savory Lentil Pancakes)", True,
            "Kcal: 220, P: 14g, C: 30g, Fb: 8g, F: 6g",
            ["1 cup Yellow Moong Dal", "1 inch Ginger", "1 Green Chili", "Salt to taste"],
            [
                "Soak yellow moong dal for 4 hours.",
                "Blend dal with ginger, green chili, and water into a smooth batter.",
                "Add salt and a pinch of turmeric.",
                "Pour ladlefuls onto a non-stick pan and cook until golden brown on both sides.",
            ],
        ),
        (
            "lunch", "Paneer & Brown Rice Bowl", True,
            "Kcal: 420, P: 22g, C: 45g, Fb: 6g, F: 16g",
            ["100g Paneer", "1 cup Brown rice", "1 cup Baby spinach"],
            [
                "Cook brown rice.",
                "Sauté paneer cubes with turmeric and salt.",
                "Combine rice and paneer in a bowl with fresh spinach.",
            ],
        ),
        (
            "snack", "Roasted Makhana (Fox Nuts)", True,
            "Kcal: 150, P: 4g, C: 20g, Fb: 3g, F: 5g",
            ["2 cups Makhana", "1 tsp Ghee", "Salt and Turmeric"],
            [
                "Dry roast makhana in a pan until crunchy.",
                "Add a teaspoon of ghee and a pinch of salt and turmeric.",
                "Toss until evenly coated.",
            ],
        ),
        (
            "dinner", "Chicken Chettinad with Brown Rice", True,
            "Kcal: 520, P: 38g, C: 48g, Fb: 5g, F: 18g",
            ["150g Chicken breast", "1 cup Brown rice", "Coconut, Peppercorns, Cinnamon"],
            [
                "Sauté onions, ginger, and garlic.",
                "Add chicken and a blend of roasted coconut, peppercorns, and cinnamon.",
                "Simmer until chicken is tender.",
                "Serve with steamed brown rice.",
            ],
        ),
    ],
    "tuesday": [
        (
            "breakfast", "Ragi Porridge (Finger Millet)", True,
            "Kcal: 210, P: 6g, C: 35g, Fb: 7g, F: 5g",
            ["1/2 cup Ragi flour", "1 cup Coconut milk", "1 tbsp Jaggery"],
            [
                "Mix ragi flour with water to avoid lumps.",
                "Cook on medium heat until thickened.",
                "Add coconut milk (dairy-free) and a bit of jaggery for sweetness.",
            ],
        ),
        (
            "lunch", "Vegetable Kurma with Brown Rice", True,
            "Kcal: 380, P: 12g, C: 50g, Fb: 9g, F: 12g",
            ["1 cup Brown rice", "Mixed vegetables (Carrot, Peas, Potato)", "Coconut paste"],
            [
                "Sauté carrots, peas, and potatoes.",
                "Add a paste of coconut, poppy seeds, and cashew nuts.",
                "Simmer until vegetables are cooked.",
                "Serve with brown rice.",
            ],
        ),
        (
            "snack", "Spiced Buttermilk (Chaas)", True,
            "Kcal: 80, P: 4g, C: 8g, Fb: 0g, F: 3g",
            ["200ml Dairy-free yogurt/buttermilk", "1/2 tsp Cumin powder", "Salt"],
            [
                "Blend dairy-free yogurt/buttermilk with water.",
                "Add roasted cumin powder and a pinch of salt.",
                "Chill and serve.",
            ],
        ),
        (
            "dinner", "Chicken Pepper Fry with Brown Rice", True,
            "Kcal: 490, P: 36g, C: 48g, Fb: 4g, F: 14g",
            ["150g Chicken breast", "1 cup Brown rice", "Black pepper, Curry leaves"],
            [
                "Sauté onions and curry leaves.",
                "Add chicken and plenty of crushed black pepper.",
                "Cook until dry and well-browned.",
                "Serve with brown rice.",
            ],
        ),
    ],
    "wednesday": [
        (
            "breakfast", "Pesarattu (Green Gram Dosa)", True,
            "Kcal: 230, P: 15g, C: 32g, Fb: 9g, F: 6g",
            ["1 cup Green Moong Dal", "Ginger, Green Chili"],
            [
                "Soak whole green moong dal.",
                "Grind with ginger and green chili.",
                "Spread on a pan like a pancake and cook until crisp.",
            ],
        ),
        (
            "lunch", "Lemon Rice with Roasted Peanuts", True,
            "Kcal: 350, P: 11g, C: 45g, Fb: 5g, F: 12g",
            ["1 cup Brown rice", "2 tbsp Peanuts", "1 Lemon"],
            [
                "Sauté mustard seeds, curry leaves, and peanuts.",
                "Mix in cooked brown rice.",
                "Stir in lemon juice and turmeric.",
            ],
        ),
        (
            "snack", "Steamed Sprouts Salad", True,
            "Kcal: 160, P: 12g, C: 22g, Fb: 7g, F: 2g",
            ["1 cup Mixed sprouts", "Cucumber, Tomato, Lemon"],
            [
                "Steam mixed sprouts.",
                "Mix with diced cucumber, tomatoes, and lemon juice.",
                "Season with salt and a pinch of chaat masala.",
            ],
        ),
        (
            "dinner", "Chicken Stew with Brown Rice", True,
            "Kcal: 510, P: 37g, C: 48g, Fb: 4g, F: 18g",
            ["150g Chicken breast", "1 cup Brown rice", "Coconut milk, Carrots"],
            [
                "Sauté onions and carrots.",
                "Add chicken and coconut milk.",
                "Simmer until tender and creamy.",
                "Serve with brown rice.",
            ],
        ),
    ],
    "thursday": [
        (
            "breakfast", "Idli with Coconut Chutney", True,
            "Kcal: 250, P: 8g, C: 40g, Fb: 4g, F: 7g",
            ["2-3 Idlis (Rice/Urad dal)", "Fresh coconut, Ginger, Chili"],
            [
                "Steam fermented rice and urad dal batter.",
                "Blend fresh coconut, green chili, and ginger for chutney.",
                "Serve hot.",
            ],
        ),
        (
            "lunch", "Bisi Bele Bath (Lentil Rice)", True,
            "Kcal: 390, P: 18g, C: 55g, Fb: 10g, F: 8g",
            ["1/2 cup Brown rice", "1/2 cup Toor dal", "Mixed vegetables, Masala"],
            [
                "Cook brown rice and toor dal together.",
                "Add mixed vegetables and a special bisi bele bath masala.",
                "Simmer until mushy and flavorful.",
            ],
        ),
        (
            "snack", "Sundal (Seasoned Chickpeas)", True,
            "Kcal: 210, P: 11g, C: 28g, Fb: 9g, F: 6g",
            ["1 cup Chickpeas", "Grated coconut, Mustard seeds"],
            [
                "Boil chickpeas.",
                "Sauté mustard seeds and curry leaves.",
                "Toss chickpeas with grated coconut.",
            ],
        ),
        (
            "dinner", "Chicken Ghee Roast with Brown Rice", True,
            "Kcal: 540, P: 36g, C: 48g, Fb: 4g, F: 22g",
            ["150g Chicken breast", "1 cup Brown rice", "Ghee, Tamarind paste"],
            [
                "Sauté chicken in ghee with a spicy tamarind-based paste.",
                "Cook until the sauce thickens and coats the chicken.",
                "Serve with brown rice.",
            ],
        ),
    ],
    "friday": [
        (
            "breakfast", "Upma with Vegetables", True,
            "Kcal: 240, P: 7g, C: 42g, Fb: 5g, F: 6g",
            ["1/2 cup Semolina", "Mixed vegetables", "Mustard seeds, Curry leaves"],
            [
                "Roast semolina (rava).",
                "Sauté onions, carrots, and peas.",
                "Add water and simmer until the rava is cooked and fluffy.",
            ],
        ),
        (
            "lunch", "Curd Rice (Dairy-Free) with Pomegranate", True,
            "Kcal: 310, P: 9g, C: 52g, Fb: 6g, F: 7g",
            ["1 cup Brown rice", "1 cup Dairy-free yogurt", "Pomegranate seeds"],
            [
                "Mash cooked brown rice.",
                "Mix with dairy-free yogurt.",
                "Temper with mustard seeds and curry leaves.",
                "Top with pomegranate seeds.",
            ],
        ),
        (
            "snack", "Roasted Almonds & Walnuts", True,
            "Kcal: 220, P: 7g, C: 6g, Fb: 3g, F: 18g",
            ["30g Almonds", "30g Walnuts"],
            [
                "Lightly toast almonds and walnuts in a pan.",
                "Add a pinch of salt.",
            ],
        ),
        (
            "dinner", "Chicken Saag (Spinach Chicken) with Brown Rice", True,
            "Kcal: 480, P: 38g, C: 48g, Fb: 6g, F: 14g",
            ["150g Chicken breast", "1 cup Brown rice", "2 cups Baby spinach"],
            [
                "Puree baby spinach.",
                "Sauté chicken with ginger and garlic.",
                "Stir in spinach puree and simmer.",
                "Serve with brown rice.",
            ],
        ),
    ],
    "saturday": [
        (
            "breakfast", "Appam with Vegetable Stew", True,
            "Kcal: 320, P: 8g, C: 45g, Fb: 7g, F: 12g",
            ["Rice batter, Coconut milk", "Mixed vegetables"],
            [
                "Ferment rice and coconut milk batter.",
                "Cook in an appam pan to get a bowl shape.",
                "Simmer mixed vegetables in coconut milk.",
            ],
        ),
        (
            "lunch", "Masala Dosa with Sambar", True,
            "Kcal: 410, P: 14g, C: 60g, Fb: 11g, F: 12g",
            ["Dosa batter", "Potato, Onion", "Toor dal, Mixed vegetables"],
            [
                "Spread fermented rice/dal batter on a pan.",
                "Fill with a potato-onion masala.",
                "Serve with lentil-based vegetable sambar.",
            ],
        ),
        (
            "snack", "Fresh Coconut Water & Fruit", True,
            "Kcal: 120, P: 2g, C: 25g, Fb: 3g, F: 1g",
            ["1 Coconut water", "1 slice Papaya/Mango"],
            [
                "Serve fresh coconut water.",
                "Pair with a slice of papaya or mango.",
            ],
        ),
        (
            "dinner", "Chicken Biryani (Brown Rice)", True,
            "Kcal: 580, P: 42g, C: 55g, Fb: 6g, F: 20g",
            ["200g Chicken breast", "1 cup Brown rice", "Dairy-free yogurt, Spices"],
            [
                "Marinate chicken in yogurt (dairy-free), ginger, garlic, and spices.",
                "Layer with parboiled brown rice.",
                "Dum cook on low heat.",
            ],
        ),
    ],
    "sunday": [
        (
            "breakfast", "Uttapam with Tomato Chutney", True,
            "Kcal: 280, P: 9g, C: 45g, Fb: 6g, F: 8g",
            ["Dosa batter", "Onion, Tomato, Chili"],
            [
                "Pour thick dosa batter on a pan.",
                "Top with finely chopped onions, tomatoes, and chilies.",
                "Cook until golden.",
            ],
        ),
        (
            "lunch", "Avial (Mixed Vegetable Stew) with Brown Rice", True,
            "Kcal: 360, P: 11g, C: 48g, Fb: 9g, F: 14g",
            ["1 cup Brown rice", "Mixed vegetables (Carrot, Beans)", "Coconut, Coconut oil"],
            [
                "Steam carrots, beans, and drumsticks.",
                "Mix with a paste of coconut, green chili, and cumin.",
                "Add a drizzle of coconut oil.",
                "Serve with brown rice.",
            ],
        ),
        (
            "snack", "Roasted Peanuts & Seeds", True,
            "Kcal: 200, P: 10g, C: 8g, Fb: 4g, F: 15g",
            ["30g Peanuts", "20g Mixed seeds"],
            [
                "Roast peanuts, pumpkin seeds, and sunflower seeds.",
                "Season with salt and a hint of pepper.",
            ],
        ),
        (
            "dinner", "Chicken Korma (Dairy-Free) with Brown Rice", True,
            "Kcal: 530, P: 40g, C: 48g, Fb: 5g, F: 20g",
            ["200g Chicken breast", "1 cup Brown rice", "Cashew paste, Mild spices"],
            [
                "Sauté onions and cashew paste.",
                "Add chicken and a blend of mild spices.",
                "Simmer until tender.",
                "Serve with brown rice.",
            ],
        ),
    ],
}

# (trigger_day, trigger_time, task_type, detailed_instructions JSON, ingredients_used JSON)
_SEED_PREP = [
    (
        "monday", "07:30", "Morning prep",
        json.dumps(["Wash the spinach and pat it dry.", "Portion the Greek yogurt into the day's serving bowls."]),
        json.dumps([{"item_name": "Baby spinach", "quantity": 1, "unit": "pcs"}, {"item_name": "Greek yogurt", "quantity": 200, "unit": "g"}]),
    ),
    (
        "tuesday", "17:00", "Dinner prep",
        json.dumps(["Dice the cherry tomatoes.", "Press the paneer to remove excess water, then cube it."]),
        json.dumps([{"item_name": "Cherry tomatoes", "quantity": 150, "unit": "g"}, {"item_name": "Paneer", "quantity": 200, "unit": "g"}]),
    ),
    (
        "wednesday", "08:00", "Batch prep",
        json.dumps(["Rinse the brown rice.", "Cook until tender, then spread it in shallow containers to cool quickly."]),
        json.dumps([{"item_name": "Brown rice", "quantity": 0.5, "unit": "kg"}]),
    ),
]

# (name, dietary_preferences, health_conditions)
_SEED_HOUSEHOLD_MEMBERS = [
    ("Preksha", [], ["Lactose Intolerance"]),
    ("Devansh", ["Can't eat spicy food."], []),
]

_SEED_PROFILE = {
    "name": "Rakesh Kumar",
    "email": "haiimrakesh@gmail.com",
    "notes": "Make it mostly Authentic South Indian receipies with High Protein.",
}


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
                (day, meal_type, dish, is_kid_friendly, macros, json.dumps(ingredients), json.dumps(full_recipe))
                for day, meals in _SEED_MENU.items()
                for meal_type, dish, is_kid_friendly, macros, ingredients, full_recipe in meals
            ],
        )
    if _is_empty(connection, "detailed_prep_schedule"):
        connection.executemany(
            "INSERT INTO detailed_prep_schedule (trigger_day, trigger_time, task_type, detailed_instructions, ingredients_used) "
            "VALUES (?, ?, ?, ?, ?)",
            _SEED_PREP,
        )
    if _is_empty(connection, "household_members"):
        connection.executemany(
            "INSERT INTO household_members (name, dietary_preferences, health_conditions) VALUES (?, ?, ?)",
            [(name, json.dumps(preferences), json.dumps(conditions)) for name, preferences, conditions in _SEED_HOUSEHOLD_MEMBERS],
        )
    connection.execute(
        "INSERT OR IGNORE INTO user_profile (id, name, email, notes) VALUES (1, ?, ?, ?)",
        (_SEED_PROFILE["name"], _SEED_PROFILE["email"], _SEED_PROFILE["notes"]),
    )
