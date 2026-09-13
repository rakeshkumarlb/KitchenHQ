"""SQLite FTS5 keyword search over the recipes catalog - the other half of
search_recipes' hybrid ranking (see kitchendb/tools/recipes.py and kitchendb/embeddings.py
for the semantic half).

recipes_fts (schema.sql) is a standalone FTS5 table, not a content=-linked one - its rowid
is always kept equal to the matching recipes.id by explicit INSERT/UPDATE/DELETE calls
from the recipes tools, the same way embedding is kept in sync there. This module only
builds the FTS MATCH query and turns FTS5's bm25() output into a bounded [0, 1] score.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def fts_fields_for(recipe: dict[str, Any]) -> tuple[str, str, str, str]:
    """Build the (name, ingredients, tags, instructions) text for a recipe_fts row.

    The fts5 table has a fixed 4-column shape, so category-style fields that aren't
    "tags" in the schema (meal_types, origin, source) are folded into the tags column
    text - they're still categorical/descriptive labels, just stored under a different
    recipe field name, and this is what makes them MATCH-able at all. Diet/allergen/
    nutrition labels live directly in tags itself (see the recipe catalog standards).
    """
    ingredient_names = ", ".join(str(item.get("item_name", "")) for item in recipe.get("ingredients", []))
    tags_text = ", ".join([
        *recipe.get("tags", []),
        *recipe.get("meal_types", []),
        str(recipe.get("origin", "")),
        str(recipe.get("source", "")),
    ])
    return (
        str(recipe.get("name", "")),
        ingredient_names,
        tags_text,
        " ".join(recipe.get("instructions", [])),
    )


def _match_query_for(text: str) -> str | None:
    """Turn free-text (a dish name, a whole sentence) into a safe FTS5 MATCH query.

    Quoting each token and OR-ing them means punctuation/operators in the raw query
    (colons, hyphens, quotes - anything a chat message might contain) can never be
    parsed as FTS5 query syntax, and any one matching term is enough to surface a
    candidate for BM25 to rank - keyword recall is intentionally loose here since the
    70% threshold in search_recipes is what keeps weak matches out, not this query.
    """
    tokens = [token for token in text.split() if token]
    if not tokens:
        return None
    escaped = [token.replace('"', '""') for token in tokens]
    return " OR ".join(f'"{token}"' for token in escaped)


def keyword_top_k(connection: sqlite3.Connection, query: str, k: int) -> list[tuple[int, float]]:
    """Rank recipes_fts rows matching `query` by BM25, best first, normalized to [0, 1].

    FTS5's bm25() is unbounded and lower-is-better, with no natural 0-1 scale, so it's
    min-max normalized across just the rows that matched this query (best match -> 1.0,
    worst matching row -> 0.0; a single match has nothing to compare against and is
    scored 1.0). Rows with no term overlap at all never appear in the FTS match set, so
    they get no keyword score rather than a misleadingly low nonzero one.
    """
    match_query = _match_query_for(query)
    if match_query is None:
        return []
    rows = connection.execute(
        "SELECT rowid, bm25(recipes_fts) AS rank FROM recipes_fts WHERE recipes_fts MATCH ? ORDER BY rank",
        (match_query,),
    ).fetchall()
    if not rows:
        return []
    scores = [row["rank"] for row in rows]
    best, worst = scores[0], scores[-1]
    spread = worst - best
    ranked = []
    for row in rows:
        normalized = 1.0 if spread == 0 else (worst - row["rank"]) / spread
        ranked.append((row["rowid"], normalized))
    return ranked[: max(k, 0)]
