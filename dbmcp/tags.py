"""Shared recipe/preference tag taxonomy for KitchenHQ.

CANONICAL SOURCE: ``shared/tags.py``. Vendored verbatim into ``dbmcp/tags.py`` and
``agents/app/tags.py`` by ``shared/sync.py`` (same mechanism as ``shared/constants.py``
- edit this file, then run ``python shared/sync.py``; ``--check`` fails on drift).

This is a *suggested* vocabulary, not an enforced enum: ``recipes.tags`` and the
household's ``preferred_tags``/``excluded_tags`` (``user_profile``) stay freeform JSON
string arrays with no DB-level constraint against these lists. The goal is one shared set
of category labels the Profile page's tag picker and (per the recipe catalog standards in
``agents/prompts/system.md``) recipe tagging both draw from, so the same dish/preference
is described the same way in both places - not a closed set a caller can't add to.

Non-Python clients (the chatui React app) get these at runtime via the ``tags`` key in
``GET /api/dashboard``'s ``constants`` block, the same delivery mechanism used for
``DAYS``/``MEAL_TYPES``.
"""

from __future__ import annotations

CUISINE_TAGS: tuple[str, ...] = (
    "Chinese",
    "Indian",
    "Mexican",
    "Italian",
    "Thai",
    "Japanese",
    "Mediterranean",
    "American",
    "Indo-Chinese",
    "Indo-Italian",
    "Tex-Mex",
)

DIETARY_TAGS: tuple[str, ...] = (
    "Vegan",
    "Vegetarian",
    "Non-Vegetarian",
    "Eggetarian",
    "Pescatarian",
)

ALLERGEN_MEDICAL_TAGS: tuple[str, ...] = (
    "Gluten-Free",
    "Dairy-Free",
    "Nut-Free",
    "Soy-Free",
    "Keto",
    "Paleo",
)

RELIGIOUS_TAGS: tuple[str, ...] = (
    "Halal",
    "Jain",
    "Hindu",
    "Kosher",
)

METHOD_EQUIPMENT_TAGS: tuple[str, ...] = (
    "Air Fryer",
    "Instant Pot",
    "Oven-Baked",
    "Slow Cooker",
    "Stovetop",
    "Microwave",
)

METHOD_PREP_STYLE_TAGS: tuple[str, ...] = (
    "One-Pot/One-Pan",
    "No-Cook",
    "Stir-Fried",
    "Deep-Fried",
    "Steamed",
)

METHOD_SPEED_TAGS: tuple[str, ...] = (
    "Under 15 Minutes",
    "30-Minute Meals",
    "Meal Prep Friendly",
    "5-Ingredients or Less",
)

# Ordered for display - a category label paired with its tuple of tags, in the order the
# Profile page's tag picker and any future recipe-tagging UI should render them.
TAG_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cuisine", CUISINE_TAGS),
    ("Dietary", DIETARY_TAGS),
    ("Allergen & Medical", ALLERGEN_MEDICAL_TAGS),
    ("Religious", RELIGIOUS_TAGS),
    ("Method: Equipment", METHOD_EQUIPMENT_TAGS),
    ("Method: Preparation Style", METHOD_PREP_STYLE_TAGS),
    ("Method: Convenience & Speed", METHOD_SPEED_TAGS),
)

ALL_TAGS: frozenset[str] = frozenset(tag for _, tags in TAG_CATEGORIES for tag in tags)
