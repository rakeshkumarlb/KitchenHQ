# shared/

Cross-service constants for KitchenHQ. Currently just the day / meal-type vocabulary
and its ordering.

## Why it's copied, not imported

The three services (`dbmcp`, `agents`, `chatui`) each build from their own Docker
context and share no Python package or package manager — by design, so each stays
independently deployable. So `shared/constants.py` is the **canonical source**, and
`sync.py` vendors a byte-identical copy into each Python service that needs the values
in-process:

| Copy | Used for |
|---|---|
| `dbmcp/constants.py` | schema validation, the `ORDER BY … CASE` builders, the `constants` block in `GET /api/dashboard` |
| `agents/app/constants.py` | Pydantic validators + module-level slot sets in the email package and `kitchen_agent` |

The chatui React app can't import Python, so it reads the same values at runtime from
dbmcp's `GET /api/dashboard` response (`data.constants`).

## Workflow

1. Edit `shared/constants.py`.
2. Run `python shared/sync.py` to refresh the copies.
3. Commit all of them together.

`python shared/sync.py --check` exits non-zero if a copy has drifted — wire it into a
pre-commit hook or run it before releasing. `dbmcp`'s test suite also asserts its copy
matches `shared/constants.py`.
