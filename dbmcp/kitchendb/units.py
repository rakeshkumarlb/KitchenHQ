"""Unit-of-measure normalization and conversion for inventory math.

KitchenHQ tracks stock in exactly three dimensions, each with one base unit:

    mass   -> gram        (canonical stored forms: "g", "kg")
    volume -> millilitre  (canonical stored forms: "ml", "l")
    count  -> piece       (canonical stored form:  "pcs")

Every inventory deduction (prep acknowledgement) and intake (shopping purchase
acknowledgement) converts the incoming quantity into the *stored* unit of the
matched inventory row before touching the balance - so a task that consumes
"500 g" of a row stored in "kg" deducts 0.5, not 500.

Recipe / prep instructions routinely name culinary units (tbsp, tsp, cup, ...).
Rather than carry a density per ingredient, those are approximated to a base
magnitude in gram-or-millilitre and given a "flexible" dimension that resolves
to whichever dimension the target inventory row uses (i.e. density ~ water).

`convert()` never guesses across dimensions: a "2 bags" against a row stored in
"kg", or an unrecognized unit token, comes back with ok=False and the caller
skips that line rather than applying a wrong number.
"""

from __future__ import annotations

MASS = "mass"
VOLUME = "volume"
COUNT = "count"
FLEXIBLE = "flexible"  # a culinary unit: adopts the target row's dimension

_ROUND = 4

# The five units an inventory row may be stored in.
CANONICAL_UNITS = ("g", "kg", "ml", "l", "pcs")

# unit token (lowercased, trimmed, de-pluralized as a fallback) -> (base_magnitude, dimension)
# base magnitude is grams (mass), millilitres (volume) or pieces (count).
_UNIT_TABLE: dict[str, tuple[float, str]] = {
    # --- mass -----------------------------------------------------------------
    "g": (1.0, MASS), "gram": (1.0, MASS), "grams": (1.0, MASS),
    "gm": (1.0, MASS), "gms": (1.0, MASS),
    "kg": (1000.0, MASS), "kgs": (1000.0, MASS),
    "kilo": (1000.0, MASS), "kilos": (1000.0, MASS),
    "kilogram": (1000.0, MASS), "kilograms": (1000.0, MASS),
    "mg": (0.001, MASS),
    "oz": (28.3495, MASS), "ounce": (28.3495, MASS), "ounces": (28.3495, MASS),
    "lb": (453.592, MASS), "lbs": (453.592, MASS),
    "pound": (453.592, MASS), "pounds": (453.592, MASS),
    # --- volume -------------------------------------------------------------
    "ml": (1.0, VOLUME), "cc": (1.0, VOLUME),
    "milliliter": (1.0, VOLUME), "milliliters": (1.0, VOLUME),
    "millilitre": (1.0, VOLUME), "millilitres": (1.0, VOLUME),
    "l": (1000.0, VOLUME),
    "liter": (1000.0, VOLUME), "liters": (1000.0, VOLUME),
    "litre": (1000.0, VOLUME), "litres": (1000.0, VOLUME),
    "fl oz": (29.5735, VOLUME), "floz": (29.5735, VOLUME),
    "fluid ounce": (29.5735, VOLUME), "fluid ounces": (29.5735, VOLUME),
    "pint": (473.176, VOLUME), "pints": (473.176, VOLUME),
    "quart": (946.353, VOLUME), "quarts": (946.353, VOLUME),
    "gallon": (3785.41, VOLUME), "gallons": (3785.41, VOLUME),
    # --- count ------------------------------------------------------------
    "pcs": (1.0, COUNT), "pc": (1.0, COUNT),
    "piece": (1.0, COUNT), "pieces": (1.0, COUNT),
    "ea": (1.0, COUNT), "each": (1.0, COUNT), "count": (1.0, COUNT),
    "no": (1.0, COUNT), "nos": (1.0, COUNT),
    "unit": (1.0, COUNT), "units": (1.0, COUNT),
    "dozen": (12.0, COUNT), "dozens": (12.0, COUNT),
    # Pack nouns: recognized as a count for legacy data so a deduction still
    # lands, but deliberately NOT canonical stored units (see _CANONICAL_FORM) -
    # add_inventory steers new rows to "pcs" instead.
    "bag": (1.0, COUNT), "bags": (1.0, COUNT),
    "bunch": (1.0, COUNT), "bunches": (1.0, COUNT),
    "pack": (1.0, COUNT), "packs": (1.0, COUNT),
    "packet": (1.0, COUNT), "packets": (1.0, COUNT),
    "box": (1.0, COUNT), "boxes": (1.0, COUNT),
    "can": (1.0, COUNT), "cans": (1.0, COUNT),
    "bottle": (1.0, COUNT), "bottles": (1.0, COUNT),
    "jar": (1.0, COUNT), "jars": (1.0, COUNT),
    # --- culinary approximations (density ~ water) -----------------------
    "tsp": (5.0, FLEXIBLE), "teaspoon": (5.0, FLEXIBLE), "teaspoons": (5.0, FLEXIBLE),
    "tbsp": (15.0, FLEXIBLE), "tbs": (15.0, FLEXIBLE),
    "tablespoon": (15.0, FLEXIBLE), "tablespoons": (15.0, FLEXIBLE),
    "cup": (240.0, FLEXIBLE), "cups": (240.0, FLEXIBLE),
    "pinch": (0.4, FLEXIBLE), "pinches": (0.4, FLEXIBLE),
    "dash": (0.6, FLEXIBLE), "dashes": (0.6, FLEXIBLE),
    "handful": (30.0, FLEXIBLE), "handfuls": (30.0, FLEXIBLE),
}

# Alias -> canonical stored form, for the mass/volume/count units that map
# cleanly onto one of CANONICAL_UNITS. Culinary/flexible units and pack nouns
# are intentionally absent: they are valid *inputs* to a conversion, never a
# valid unit for an inventory row to be stored in.
_CANONICAL_FORM: dict[str, str] = {
    "g": "g", "gram": "g", "grams": "g", "gm": "g", "gms": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "cc": "ml",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "pcs": "pcs", "pc": "pcs", "piece": "pcs", "pieces": "pcs",
    "ea": "pcs", "each": "pcs", "count": "pcs",
    "no": "pcs", "nos": "pcs", "unit": "pcs", "units": "pcs",
}


def _clean(raw: str | None) -> str:
    """Lowercase, trim, drop a trailing '.', collapse internal whitespace."""
    return " ".join(str(raw if raw is not None else "").strip().lower().rstrip(".").split())


def normalize_unit(raw: str | None) -> tuple[float, str] | None:
    """Map a free-text unit onto ``(base_magnitude, dimension)``; ``None`` if unknown."""
    token = _clean(raw)
    if not token:
        return None
    if token in _UNIT_TABLE:
        return _UNIT_TABLE[token]
    if token.endswith("s") and token[:-1] in _UNIT_TABLE:  # tolerate an un-enumerated plural
        return _UNIT_TABLE[token[:-1]]
    return None


def canonicalize_inventory_unit(raw: str | None) -> str | None:
    """Canonical stored form ('g'/'kg'/'ml'/'l'/'pcs') for a recognized
    mass/volume/count unit, else ``None``.

    Returns ``None`` for culinary units (tbsp, cup, ...) and pack nouns (bag,
    can, ...): those are never a valid unit for an inventory row.
    """
    token = _clean(raw)
    if token in _CANONICAL_FORM:
        return _CANONICAL_FORM[token]
    if token.endswith("s") and token[:-1] in _CANONICAL_FORM:
        return _CANONICAL_FORM[token[:-1]]
    return None


def _fmt(value: float) -> str:
    return f"{value:g}"


def convert(quantity: float, from_unit: str | None, to_unit: str | None) -> tuple[float, str, bool]:
    """Convert ``quantity`` from ``from_unit`` into ``to_unit`` (an inventory row's stored unit).

    Returns ``(value, note, ok)``:

    * ``ok=True, note=""``  - straight passthrough (no source unit, or it already
      matches the row's unit); ``value`` is ``quantity`` unchanged.
    * ``ok=True, note="converted 500 g -> 0.5 kg"``  - a real conversion.
    * ``ok=False``  - the units are different dimensions, or one of them is
      unrecognized. ``value`` is the untouched input and the caller MUST skip the
      line rather than apply a wrong number; ``note`` explains why.
    """
    from_clean = _clean(from_unit)
    to_clean = _clean(to_unit)

    if not from_clean or from_clean == to_clean:
        return quantity, "", True

    from_spec = normalize_unit(from_clean)
    if from_spec is None:
        return quantity, f"unrecognized unit '{from_unit}' - cannot convert to '{to_unit}'", False
    to_spec = normalize_unit(to_clean)
    if to_spec is None or to_spec[1] == FLEXIBLE:
        # An inventory row is only ever stored in a concrete mass/volume/count
        # unit; a culinary unit (or an unknown token) as the target is something
        # we refuse to reason about rather than guess.
        return quantity, f"inventory unit '{to_unit}' is non-standard - cannot convert '{from_unit}' into it", False

    from_mag, from_dim = from_spec
    to_mag, to_dim = to_spec
    if from_dim == FLEXIBLE:  # a culinary unit adopts the target row's dimension
        from_dim = to_dim

    if from_dim != to_dim:
        return quantity, f"cannot convert {from_dim} ('{from_unit}') into {to_dim} ('{to_unit}')", False

    converted = round(quantity * from_mag / to_mag, _ROUND)
    return converted, f"converted {_fmt(quantity)} {from_clean} -> {_fmt(converted)} {to_clean}", True
