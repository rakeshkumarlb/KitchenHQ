from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kitchendb.units import canonicalize_inventory_unit, convert, normalize_unit


@pytest.mark.parametrize(
    "quantity, from_unit, to_unit, expected",
    [
        (500, "g", "kg", 0.5),        # the reported bug: grams into a kg row
        (2, "kg", "g", 2000),
        (1.5, "l", "ml", 1500),
        (250, "ml", "l", 0.25),
        (1, "tbsp", "g", 15),         # culinary unit approximated, mass target
        (2, "tbsp", "ml", 30),        # same unit approximated, volume target
        (1, "cup", "ml", 240),
        (1, "dozen", "pcs", 12),
    ],
)
def test_convert_same_dimension(quantity, from_unit, to_unit, expected):
    value, note, ok = convert(quantity, from_unit, to_unit)
    assert ok is True
    assert value == expected
    assert "->" in note


def test_convert_passthrough_when_unit_missing_or_matches():
    assert convert(300, "", "g") == (300, "", True)
    assert convert(300, None, "kg") == (300, "", True)
    assert convert(2, "kg", "kg") == (2, "", True)


def test_convert_rejects_dimension_mismatch():
    value, note, ok = convert(2, "bags", "kg")
    assert ok is False
    assert value == 2               # input handed back untouched
    assert "count" in note and "mass" in note


def test_convert_rejects_unknown_source_unit():
    value, note, ok = convert(1, "sprig", "g")
    assert ok is False
    assert value == 1
    assert "unrecognized" in note


def test_convert_flags_non_standard_inventory_unit():
    value, note, ok = convert(1, "g", "handful")
    assert ok is False
    assert "non-standard" in note


def test_normalize_unit_aliases_and_plurals():
    assert normalize_unit("Kilograms") == (1000.0, "mass")
    assert normalize_unit("LITRE") == (1000.0, "volume")
    assert normalize_unit("pieces") == (1.0, "count")
    assert normalize_unit("tablespoon")[1] == "flexible"
    assert normalize_unit("nonsense") is None


def test_canonicalize_inventory_unit():
    assert canonicalize_inventory_unit("grams") == "g"
    assert canonicalize_inventory_unit(" KG ") == "kg"
    assert canonicalize_inventory_unit("litres") == "l"
    assert canonicalize_inventory_unit("piece") == "pcs"
    # culinary units and pack nouns are never valid stored units
    assert canonicalize_inventory_unit("tbsp") is None
    assert canonicalize_inventory_unit("bag") is None
    assert canonicalize_inventory_unit("bottle") is None
