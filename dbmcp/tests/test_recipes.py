from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_API_KEY = "test-key"

_SAMPLE_RECIPE = {
    "name": "Paneer Butter Masala",
    "origin": "North Indian",
    "serves": 4,
    "prep_time_minutes": 15,
    "cook_time_minutes": 30,
    "ingredients": [{"item_name": "paneer", "quantity": 250, "unit": "g"}],
    "instructions": ["Cube the paneer.", "Heat oil and simmer the gravy."],
    "macros_per_serving": {"calories": 320, "protein_g": 14},
    "dietary_flags": ["vegetarian"],
    "meal_types": ["lunch", "dinner"],
    "tags": ["curry"],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KITCHEN_DB_PATH", str(tmp_path / "kitchen.db"))
    monkeypatch.setenv("KITCHENHQ_API_KEY", TEST_API_KEY)

    # Ranking-logic tests should not depend on downloading the real embedding model -
    # stub it with a deterministic bag-of-words feature-hash vector (shared words land
    # in the same dimension), so cosine similarity meaningfully reflects text overlap
    # without any network access or real ML model. Patched on kitchendb.tools.recipes
    # (not kitchendb.embeddings) because that module did `from ..embeddings import
    # embed_text`, binding its own name to the original function - patching the
    # embeddings module's attribute would not affect that already-bound reference.
    import zlib

    import kitchendb.tools.recipes as recipes_module

    def fake_embed_text(text: str) -> list[float]:
        vector = [0.0] * 64
        for word in text.lower().split():
            vector[zlib.crc32(word.encode()) % len(vector)] += 1.0
        return vector

    monkeypatch.setattr(recipes_module, "embed_text", fake_embed_text)

    from fastapi.testclient import TestClient
    from kitchendb import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-API-Key": TEST_API_KEY})
        yield test_client


def test_recipe_crud_round_trip(client):
    added = client.post("/api/recipes", json={"recipe": _SAMPLE_RECIPE}).json()
    assert added["name"] == "Paneer Butter Masala"
    assert added["recipe"]["ingredients"] == [{"item_name": "paneer", "quantity": 250.0, "unit": "g"}]
    assert added["rating"] is None

    fetched = client.get(f"/api/recipes/{added['id']}").json()
    assert fetched["recipe"]["instructions"] == _SAMPLE_RECIPE["instructions"]

    listed = client.get("/api/recipes?limit=10").json()
    assert any(row["id"] == added["id"] for row in listed)

    updated_payload = {**_SAMPLE_RECIPE, "name": "Paneer Butter Masala (Updated)"}
    updated = client.put(f"/api/recipes/{added['id']}", json={"recipe": updated_payload}).json()
    assert updated["name"] == "Paneer Butter Masala (Updated)"

    deleted = client.delete(f"/api/recipes/{added['id']}").json()
    assert deleted == {"deleted": True, "id": added["id"]}
    assert client.get(f"/api/recipes/{added['id']}").status_code == 400


def test_search_recipes_ranks_relevant_first(client):
    veg = client.post("/api/recipes", json={"recipe": _SAMPLE_RECIPE}).json()
    client.post("/api/recipes", json={"recipe": {
        **_SAMPLE_RECIPE,
        "name": "Grilled Salmon",
        "ingredients": [{"item_name": "salmon", "quantity": 200, "unit": "g"}],
        "instructions": ["Season the salmon.", "Grill until flaky."],
        "tags": ["seafood"],
    }}).json()

    # An exact-name query is a strong match (both keyword and semantic) for the paneer
    # recipe and shares no terms/topic with the salmon one - the unrelated recipe must be
    # filtered out, not just ranked second, since neither of its signals clears 70%.
    results = client.get("/api/recipes/search", params={"q": "Paneer Butter Masala", "top_k": 5}).json()
    assert [row["id"] for row in results] == [veg["id"]]
    assert results[0]["score"] > 0.7


def test_search_recipes_excludes_weak_matches_entirely(client):
    client.post("/api/recipes", json={"recipe": {
        **_SAMPLE_RECIPE,
        "name": "Grilled Salmon",
        "ingredients": [{"item_name": "salmon", "quantity": 200, "unit": "g"}],
        "instructions": ["Season the salmon.", "Grill until flaky."],
        "tags": ["seafood"],
    }}).json()

    # Nothing in the catalog is about tacos - a query with no keyword or semantic overlap
    # must come back empty rather than padding top_k with the nearest-available recipe.
    results = client.get("/api/recipes/search", params={"q": "beef tacos", "top_k": 5}).json()
    assert results == []


def test_add_recipe_validation_failures(client):
    bad_ingredients = client.post("/api/recipes", json={"recipe": {**_SAMPLE_RECIPE, "ingredients": []}})
    assert bad_ingredients.status_code == 400

    bad_meal_type = client.post("/api/recipes", json={"recipe": {**_SAMPLE_RECIPE, "meal_types": ["brunch"]}})
    assert bad_meal_type.status_code == 400

    bad_instructions = client.post("/api/recipes", json={"recipe": {**_SAMPLE_RECIPE, "instructions": []}})
    assert bad_instructions.status_code == 400


def test_rate_recipe(client):
    added = client.post("/api/recipes", json={"recipe": _SAMPLE_RECIPE}).json()
    before_embedding = client.get(f"/api/recipes/{added['id']}").json()

    rated = client.patch(f"/api/recipes/{added['id']}/rating", json={"rating": 5}).json()
    assert rated["rating"] == 5

    after_embedding = client.get(f"/api/recipes/{added['id']}").json()
    assert after_embedding["recipe"] == before_embedding["recipe"]

    assert client.patch(f"/api/recipes/{added['id']}/rating", json={"rating": 0}).status_code == 422
    assert client.patch("/api/recipes/999999/rating", json={"rating": 3}).status_code == 400
