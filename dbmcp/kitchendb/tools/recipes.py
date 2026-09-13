"""Recipe catalog data operations.

Recipes are rows in this same SQLite database (not a separate document store): one row
holds the full structured recipe as JSON, its embedding vector, and a household rating -
so the recipe and its search vector are always the same row and can never drift apart.
add_recipe/update_recipe always (re)compute the embedding synchronously; reindex_recipes
is a separate housekeeping sweep for bulk backfill or an embedding-model upgrade, not the
normal write path.
"""

from __future__ import annotations

import json
from typing import Any

from constants import MEAL_TYPE_SET

from .registry import tool
from ..db import connect, fetch_record
from ..embeddings import cosine_top_k, embed_text, embedding_text_for
from ..keyword_search import fts_fields_for, keyword_top_k
from ..validation import clean_line_list, normalize_ingredients_used

# A recipe qualifies for search_recipes' results if its keyword score OR its semantic
# score clears this bar; neither is required to be exact, but a recipe both signals
# consider a weak match is left out rather than padding top_k with noise.
_MATCH_THRESHOLD = 0.5


def _validate_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    name = str(recipe.get("name", "")).strip()
    if not name:
        raise ValueError("recipe.name must not be empty")
    ingredients = normalize_ingredients_used(recipe.get("ingredients"))
    if not ingredients:
        raise ValueError("recipe.ingredients must contain at least one item")
    instructions = clean_line_list(recipe.get("instructions", []), field="instructions", required=True)
    meal_types = []
    for meal_type in recipe.get("meal_types", []) or []:
        normalized = str(meal_type).strip().lower()
        if normalized not in MEAL_TYPE_SET:
            raise ValueError(f"meal_types must each be one of {sorted(MEAL_TYPE_SET)}")
        meal_types.append(normalized)
    dietary_flags = clean_line_list(recipe.get("dietary_flags", []), field="dietary_flags", required=False)
    tags = clean_line_list(recipe.get("tags", []), field="tags", required=False)
    serves = int(recipe.get("serves") or 1)
    if serves < 1:
        raise ValueError("recipe.serves must be at least 1")
    return {
        "name": name,
        "origin": str(recipe.get("origin", "")).strip(),
        "serves": serves,
        "prep_time_minutes": recipe.get("prep_time_minutes"),
        "cook_time_minutes": recipe.get("cook_time_minutes"),
        "ingredients": ingredients,
        "instructions": instructions,
        "macros_per_serving": recipe.get("macros_per_serving") or {},
        "dietary_flags": dietary_flags,
        "meal_types": meal_types,
        "tags": tags,
        "source": str(recipe.get("source", "household")).strip() or "household",
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "recipe": json.loads(row["recipe"]),
        "rating": row["rating"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@tool
def add_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Add a recipe to the household catalog.

    `recipe` is the full structured recipe: name, origin, serves, prep_time_minutes,
    cook_time_minutes, ingredients ([{item_name, quantity, unit}]), instructions
    (ordered plain-text steps), macros_per_serving, dietary_flags, meal_types (each one
    of "breakfast"/"lunch"/"snack"/"dinner"), tags, source. Its embedding is computed
    automatically from the whole recipe text, so it's searchable via search_recipes
    immediately.
    """
    validated = _validate_recipe(recipe)
    vector = embed_text(embedding_text_for(validated))
    name, ingredients_text, tags_text, instructions_text = fts_fields_for(validated)
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO recipes (name, recipe, embedding) VALUES (?, ?, ?)",
            (validated["name"], json.dumps(validated), json.dumps(vector)),
        )
        connection.execute(
            "INSERT INTO recipes_fts (rowid, name, ingredients, tags, instructions) VALUES (?, ?, ?, ?, ?)",
            (cursor.lastrowid, name, ingredients_text, tags_text, instructions_text),
        )
    return _row_to_dict(fetch_record("recipes", cursor.lastrowid))


@tool
def update_recipe(recipe_id: int, recipe: dict[str, Any]) -> dict[str, Any]:
    """Replace a recipe's content (same shape as add_recipe) and recompute its embedding."""
    validated = _validate_recipe(recipe)
    vector = embed_text(embedding_text_for(validated))
    name, ingredients_text, tags_text, instructions_text = fts_fields_for(validated)
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE recipes SET name = ?, recipe = ?, embedding = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (validated["name"], json.dumps(validated), json.dumps(vector), recipe_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No recipes record found for id {recipe_id}")
        connection.execute(
            "UPDATE recipes_fts SET name = ?, ingredients = ?, tags = ?, instructions = ? WHERE rowid = ?",
            (name, ingredients_text, tags_text, instructions_text, recipe_id),
        )
    return _row_to_dict(fetch_record("recipes", recipe_id))


@tool
def get_recipe(recipe_id: int) -> dict[str, Any]:
    """Read one recipe by id, full content included."""
    return _row_to_dict(fetch_record("recipes", recipe_id))


@tool
def list_recipes(limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
    """List recipes alphabetically by name. Pass limit=10 for the catalog's default view."""
    query = "SELECT * FROM recipes ORDER BY name COLLATE NOCASE"
    params: list[Any] = []
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in rows]


@tool
def delete_recipe(recipe_id: int) -> dict[str, Any]:
    """Remove a recipe from the catalog."""
    with connect() as connection:
        cursor = connection.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"No recipes record found for id {recipe_id}")
        connection.execute("DELETE FROM recipes_fts WHERE rowid = ?", (recipe_id,))
    return {"deleted": True, "id": recipe_id}


@tool
def rate_recipe(recipe_id: int, rating: int) -> dict[str, Any]:
    """Set a recipe's household rating (1-5). Never changes its embedding."""
    if rating not in (1, 2, 3, 4, 5):
        raise ValueError("rating must be an integer between 1 and 5")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE recipes SET rating = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (rating, recipe_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No recipes record found for id {recipe_id}")
    return _row_to_dict(fetch_record("recipes", recipe_id))


@tool
def search_recipes(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Hybrid keyword + semantic search of the recipe catalog for dishes matching `query`.

    Call this before writing new dish instructions (in chat, weekly-menu planning, or
    prep tasks) and adapt whatever comes back to the household's preferences, rather
    than inventing a dish unaided. A recipe is only returned if its keyword match score
    or its semantic match score clears _MATCH_THRESHOLD (currently 0.7) - the two are
    independent signals (typo/synonym-tolerant embedding similarity vs. exact-term BM25),
    and either one being confident is enough. Ranked recipes are ordered by the higher of
    the two scores, capped at top_k; a weak field (nothing clears the bar) returns fewer
    than top_k, or an empty list, rather than padding the results with irrelevant recipes
    - an empty list means nothing in the catalog is a real match and it's fine to plan
    from scratch.
    """
    with connect() as connection:
        rows = connection.execute("SELECT * FROM recipes").fetchall()
        if not rows:
            return []
        by_id = {row["id"]: row for row in rows}
        semantic_candidates = [(row["id"], json.loads(row["embedding"])) for row in rows]
        query_vector = embed_text(query)
        semantic_scores = dict(cosine_top_k(query_vector, semantic_candidates, len(semantic_candidates)))
        keyword_scores = dict(keyword_top_k(connection, query, len(rows)))

    qualifying = []
    for recipe_id in by_id:
        best_score = max(semantic_scores.get(recipe_id, 0.0), keyword_scores.get(recipe_id, 0.0))
        if best_score > _MATCH_THRESHOLD:
            qualifying.append((recipe_id, best_score))
    qualifying.sort(key=lambda pair: pair[1], reverse=True)

    results = []
    for recipe_id, score in qualifying[:top_k]:
        entry = _row_to_dict(by_id[recipe_id])
        entry["score"] = score
        results.append(entry)
    return results


@tool
def reindex_recipes() -> dict[str, Any]:
    """Recompute every recipe's embedding and keyword index from its stored content.

    Housekeeping only - add_recipe/update_recipe already embed and index on every write.
    Use this after a bulk import (rows inserted without going through add_recipe) or an
    embedding-model change.
    """
    with connect() as connection:
        rows = connection.execute("SELECT id, recipe FROM recipes").fetchall()
        for row in rows:
            recipe = json.loads(row["recipe"])
            vector = embed_text(embedding_text_for(recipe))
            name, ingredients_text, tags_text, instructions_text = fts_fields_for(recipe)
            connection.execute("UPDATE recipes SET embedding = ? WHERE id = ?", (json.dumps(vector), row["id"]))
            connection.execute(
                # INSERT OR REPLACE (not an ON CONFLICT upsert - FTS5 virtual tables
                # don't expose a declared unique index for the upsert planner to target,
                # but do honor plain rowid-conflict replacement) so this is safe whether
                # or not the row already has an FTS entry.
                "INSERT OR REPLACE INTO recipes_fts (rowid, name, ingredients, tags, instructions) "
                "VALUES (?, ?, ?, ?, ?)",
                (row["id"], name, ingredients_text, tags_text, instructions_text),
            )
    return {"reindexed": len(rows)}
