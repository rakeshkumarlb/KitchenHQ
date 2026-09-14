from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from .config import Settings
from .job_context import build_job_context
from .kitchen_agent import ALL_MENU_SLOTS, run_agent
from .models import ExecutiveChefResult, FoodInspectorResult, PantryManagerResult, SousChefResult
from .telemetry import record_agent_run
from .weekly_plan import record_skipped_menu_slots, record_weekly_plan

logger = logging.getLogger("kitchenhq-agent")

# Each scheduled prompt is self-contained: one PURPOSE line, then the exact ordered
# steps for THIS run. Role prompts (prompts/*.md) hold only standing behaviour -
# anything job-specific (which day, which meals, the time cap, which email) lives here.

_PREP_STEPS = """\
2. job.target_menu_days from get_job_context holds the exact weekday(s) for {day_phrase}. Load the weekly_menu rows for {meal_scope} on those weekday(s) - the table is keyed by weekday name, not date.
3. Call get_household_preferences and get_inventory. Call search_recipes for each dish being prepped and adapt a relevant match rather than inventing the method unaided (proceed normally if nothing relevant comes back). Match each ingredient the task will actually use to its exact item_name spelling in inventory, and let any household member's dietary preferences or health conditions shape the instructions (e.g. keep an allergen out, note a substitution).
4. Save with add_detailed_prep_schedule ({time_cap}): detailed_instructions is your ordered list of instruction-step strings (one step per list entry, no numbering); ingredients_used is [{{item_name, quantity, unit}}] for every ingredient matched in step 3, using the item_name exactly as it appears in inventory - this is what lets inventory deduct automatically once a human checks the task complete, so do not omit an ingredient that has a matching inventory row. Give each unit as g/kg, ml/l or pcs matching that item's inventory dimension (tsp/tbsp/cup are accepted and auto-approximated to g/ml); the quantity is converted into the row's own unit on deduction, so match the dimension, not the exact unit. This save is the required outcome - you are not finished until it succeeds.
5. Call send_prep_task_email: prep_date is the date in job.target_menu_days, meals is [{{dish, meal_type, servings}}] for each dish (servings = household size, from get_household_preferences' household_members), steps is your instructions, ingredients is what will be used.
6. Reply with a two-sentence summary naming the dishes and the saved prep_schedule id(s)."""

SCHEDULED_REQUESTS = {
    "weekly_menu": """\
PURPOSE: replace the saved weekly menu with a fresh, complete plan for the coming Monday-to-Sunday week - {slot_count} required slots: all seven days (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday AND Sunday) x breakfast, lunch, snack, dinner{skip_note}.
1. Call get_job_context.
2. Call get_household_preferences. Its `restrictions` list is the authoritative rule set - there is no separate deterministic check, so honor every entry with `enabled: true` up front rather than discovering a conflict later. Its `skip_meals` lists any day/meal slots the household wants left unplanned this week - do NOT call add_weekly_menu_item for those. The chef note and favourite dishes are OPTIONAL - if empty, ignore them and continue; do not stop.
3. Call get_inventory, then get_weekly_menu to see what is currently saved.
4. For each required slot (every slot except the ones skip_meals lists), call search_recipes for a candidate dish before deciding on it; adapt a relevant match to the household's preferences and inventory rather than inventing unaided, and plan from scratch only when nothing relevant comes back. Note the matched recipe's id for step 5 whenever you adapt one. Decide a dish for every required slot, including Saturday and Sunday - plan the weekend fresh, do not leave the currently-saved weekend dishes in place. Follow every dietary and macro rule and every enabled restriction from step 2; chicken only at dinner.
5. Save each required slot with its own add_weekly_menu_item call (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients as a list of ingredient strings, description as a short one-to-two sentence summary of the dish, full_recipe as a list of method-step strings, and source_recipe_id set to step 4's matched recipe id when the dish was adapted from one, left unset when invented from scratch). Overwriting an existing slot is expected. Saving all {slot_count} DISTINCT required day/meal slots is the required outcome - you are not finished until every one of them has been saved.
6. Call send_weekly_plan_email: week_start and week_end are the first and last dates in job.target_menu_days; considerations is your reasoning (favourites used, how the rules were met, inventory gaps); shopping_needs is the ingredients likely to be bought. Do NOT pass days - the tool reads the saved menu itself.
7. Reply in plain text with a two-sentence summary of the week and whether the email sent.""",
    "sunday_prep": "PURPOSE: one batch-prep session that makes the coming week's cooking faster.\n1. Call get_job_context.\n"
    + _PREP_STEPS.format(meal_scope="the meals", day_phrase="the coming week", time_cap="cap 60 minutes"),
    "nightly_prep": "PURPOSE: a small prep task tonight so tomorrow morning's cooking is quick.\n1. Call get_job_context.\n"
    + _PREP_STEPS.format(meal_scope="breakfast and lunch", day_phrase="tomorrow", time_cap="cap 10 minutes"),
    "morning_cooking": "PURPOSE: a parallel cooking plan for the breakfast and lunch being made this morning.\n1. Call get_job_context.\n"
    + _PREP_STEPS.format(meal_scope="breakfast and lunch", day_phrase="today", time_cap="cap 40 minutes"),
    "dinner_cooking": "PURPOSE: a parallel cooking plan for tonight's snack and dinner.\n1. Call get_job_context.\n"
    + _PREP_STEPS.format(meal_scope="snack and dinner", day_phrase="today", time_cap="cap 40 minutes"),
    "pantry_manager": """\
PURPOSE: propose a shopping list for whatever is running low or needed for the coming week.
1. Call get_job_context.
2. Call get_inventory and get_shopping_items so you can see what's already pending.
3. Load the weekly_menu rows for the weekdays in job.target_menu_days and work out what they will consume.
4. Work out what is genuinely needed (below minimum_threshold or short for the week) and call add_shopping_items with it - it merges into whatever is already pending, so just call it with whatever is newly needed; there's no need to check for or avoid duplicates yourself. This save is the required outcome.
5. Call send_shopping_list_email: items is the exact list you passed to add_shopping_items in step 4, each as {item_name, proposed_quantity, unit, reason} with a short reason; reasoning is the overall rationale. The tool does not read the list itself.
6. Reply with a two-sentence summary of what was added.""",
    "menu_audit": """\
PURPOSE: judge every weekly_menu row not yet scored against the same rules and preferences the Executive Chef used.
1. Call get_job_context.
2. Call get_household_preferences so you judge against the same chef note, favourites, restrictions, and household members' preferences/conditions the Executive Chef had.
3. Call get_unaudited_weekly_menu_items. If it returns nothing, there is nothing to audit this run - say so and stop.
4. For every row returned, judge it against the dietary/macro rules, every `per_meal`-scope entry in step 2's `restrictions` with `enabled: true` (a `week`-scope entry like lunch variety is judged separately, across the whole saved week, by the weekly_plan_audit job - not here), chicken dinner-only, and the household context from step 2 - including whether the ingredient quantities look scaled for the household (household_members count) and whether the dish/instructions were actually adapted to a member's preference or health condition, not just nutritionally fine in general - then call record_weekly_menu_audit(weekly_menu_id, score, audit_feedback) for that row - score 0-100, audit_feedback naming what it got right and, if imperfect, exactly what it falls short on. Do this for every row from step 3; do not stop partway.
5. Reply with a short summary of how many rows you scored and any repeat issue worth flagging.""",
    "weekly_plan_audit": """\
PURPOSE: judge every weekly_plans row not yet scored for completeness and rule-compliance against the exact context that week was planned under - the whole-week properties that can't be judged from any single weekly_menu row alone.
1. Call get_job_context.
2. Call get_unaudited_weekly_plans. If it returns nothing, there is nothing to audit this run - say so and stop. Do NOT call get_household_preferences for this job - each row's own skip_meals_snapshot/chef_note_snapshot/restrictions_snapshot IS the authoritative context for that week (what the Executive Chef actually saw), not whatever the household has changed to since.
3. For every row returned, call get_weekly_menu to see that week's full saved menu, then judge three things: (a) completeness - every (day, meal_type) slot NOT listed in that row's skip_meals_snapshot must have a saved dish for that week; a missing required slot is a hard fault; (b) every `week`-scope entry in that row's restrictions_snapshot (e.g. lunch_variety - count the actual distinct weekday lunch dishes and compare against its `value`) - ignore `per_meal`-scope entries here, those were already judged per row by menu_audit against live rules; (c) when chef_note_snapshot is non-empty, whether the week's dishes plausibly reflect it.
4. Call record_weekly_plan_audit(weekly_plan_id, score, audit_feedback) for that row - score 0-100, audit_feedback naming what the week's plan got right and, if imperfect, exactly what it falls short on (a missing slot, an unmet restriction, or an ignored chef note). Do this for every row from step 2; do not stop partway.
5. Reply with a short summary of how many weeks you scored and any repeat issue worth flagging.""",
    "task_audit": """\
PURPOSE: judge every detailed_prep_schedule row not yet scored against the same rules and preferences the Sous Chef used.
1. Call get_job_context.
2. Call get_household_preferences so you judge against the same household context the Sous Chef had.
3. Call get_unaudited_prep_tasks. If it returns nothing, there is nothing to audit this run - say so and stop.
4. For every row returned (including cancelled ones - you are judging the decision, not whether it was performed), judge the instructions and ingredients_used against the dietary rules and household context from step 2 - including whether ingredients_used quantities look scaled for the household and whether the instructions genuinely reflect a member's preference or health condition - then call record_prep_task_audit(prep_schedule_id, score, audit_feedback) for that row - score 0-100, audit_feedback naming what it got right and, if imperfect, exactly what it falls short on. Do this for every row from step 3; do not stop partway.
5. Reply with a short summary of how many rows you scored and any repeat issue worth flagging.""",
    "expire_prep_tasks": """\
PURPOSE: housekeeping sweep - expire any prep task a human never acknowledged or cancelled within its 2-hour action window, so stale tasks stop cluttering the task list.
1. Call get_job_context.
2. Call expire_stale_prep_tasks (no arguments) - it finds every detailed_prep_schedule row still 'assigned' with created_at more than 2 hours ago and marks each one 'expired'. It never touches inventory.
3. Reply with a one-sentence summary of how many tasks (if any) were expired, using the tool's returned expired_ids.""",
    "recipe_audit": """\
PURPOSE: judge every recipe catalog row not yet scored against the recipe catalog standards, independent of any household's preferences.
1. Call get_job_context.
2. Call get_unaudited_recipes. If it returns nothing, there is nothing to audit this run - say so and stop. Do NOT call get_household_preferences for this job - a catalog recipe is a general-purpose reference, not a plan for a specific household, so it is judged only against the recipe catalog standards below.
3. For every row returned, judge its tags and instructions against the recipe catalog standards: diet category must carry exactly one explicit tag from the mutually exclusive pair "Vegetarian"/"Non-Vegetarian" (never both on the same recipe, never neither), allergen/nutrition labels the ingredients/macros actually support, and clear, ordered, complete instructions. Then call record_recipe_audit(recipe_id, score, audit_feedback) for that row - score 0-100, audit_feedback naming what it got right and, if imperfect, exactly what tag or instruction issue it falls short on. Do this for every row from step 2; do not stop partway.
4. Reply with a short summary of how many rows you scored and any repeat issue worth flagging.""",
}

JOB_ROLES = {
    "weekly_menu": "executive_chef",
    "sunday_prep": "sous_chef",
    "nightly_prep": "sous_chef",
    "morning_cooking": "sous_chef",
    "dinner_cooking": "sous_chef",
    "pantry_manager": "pantry_manager",
    "menu_audit": "food_inspector",
    "weekly_plan_audit": "food_inspector",
    "task_audit": "food_inspector",
    "expire_prep_tasks": "sous_chef",
    "recipe_audit": "food_inspector",
}

# Structured result each job returns. Passed explicitly to run_agent so the weekly_menu
# job gets structured JSON even though executive_chef's chat replies stay free text.
JOB_RESULT_MODELS = {
    "weekly_menu": ExecutiveChefResult,
    "sunday_prep": SousChefResult,
    "nightly_prep": SousChefResult,
    "morning_cooking": SousChefResult,
    "dinner_cooking": SousChefResult,
    "pantry_manager": PantryManagerResult,
    "menu_audit": FoodInspectorResult,
    "weekly_plan_audit": FoodInspectorResult,
    "task_audit": FoodInspectorResult,
    "expire_prep_tasks": SousChefResult,
    "recipe_audit": FoodInspectorResult,
}

# The DB write(s) each job exists to make. If the model stops short, run_agent sends
# corrective nudges (see _MAX_FOLLOWUPS) and finally raises rather than recording an
# empty "completed" run. REQUIRED_TOOLS = must be called at least once (an entry may be
# a tuple of alternative tool names, satisfied by calling any one of them); REQUIRED_TOOL_COUNTS
# = must be called at least N times (weekly_menu needs one add_weekly_menu_item call per
# required slot - up to 28, fewer if skip_meals excludes some - computed per-run in
# run_job, not fixed here). The email tools are deliberately not required - a missed
# email must never fail the job.
JOB_REQUIRED_TOOLS = {
    # No deterministic policy gate - get_household_preferences' `restrictions` is now the
    # only rule source, so it's required directly rather than a validator tool call.
    "weekly_menu": ["get_household_preferences"],
    "sunday_prep": ["add_detailed_prep_schedule"],
    "nightly_prep": ["add_detailed_prep_schedule"],
    "morning_cooking": ["add_detailed_prep_schedule"],
    "dinner_cooking": ["add_detailed_prep_schedule"],
    "pantry_manager": ["add_shopping_items"],
    # Only the "did you even check" step is enforced - how many rows get audited varies
    # run to run (some nights there's nothing new to score), so record_*_audit isn't a
    # hard requirement the way add_weekly_menu_item's 28 slots are.
    "menu_audit": ["get_unaudited_weekly_menu_items"],
    "weekly_plan_audit": ["get_unaudited_weekly_plans"],
    "task_audit": ["get_unaudited_prep_tasks"],
    "expire_prep_tasks": ["expire_stale_prep_tasks"],
    "recipe_audit": ["get_unaudited_recipes"],
}

# weekly_menu's count is computed per-run in run_job (28 minus whatever skip_meals
# lists), not fixed here - see _fetch_skip_meals/_required_menu_slots below.
JOB_REQUIRED_TOOL_COUNTS: dict[str, dict[str, int]] = {}


async def _fetch_planning_snapshot(settings: Settings) -> dict[str, Any]:
    """The household's configured skip_meals/chef note/enabled restrictions right now.

    Fetched once before the weekly_menu job runs and threaded through to
    record_weekly_plan afterward, so weekly_plans' snapshot reflects the exact context
    the Executive Chef planned this week under - not whatever the household edits later.
    Best-effort, same pattern as telemetry.py's record_agent_run - a fetch failure just
    means nothing is treated as skipped/noted/restricted (the full 28-slot week is still
    required), never a reason to fail the job outright.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.db_api_url}/api/dashboard",
                headers={"X-API-Key": settings.kitchenhq_api_key},
            )
            response.raise_for_status()
        profile = response.json().get("profile") or {}
        skip_meals = profile.get("skip_meals")
        restrictions = profile.get("restrictions")
        return {
            "skip_meals": skip_meals if isinstance(skip_meals, dict) else {},
            "chef_note": str(profile.get("notes") or ""),
            "restrictions": [
                entry for entry in (restrictions if isinstance(restrictions, list) else [])
                if isinstance(entry, dict) and entry.get("enabled")
            ],
        }
    except Exception:
        logger.warning("Could not fetch planning context for weekly_menu job; planning the full week", exc_info=True)
        return {"skip_meals": {}, "chef_note": "", "restrictions": []}


def _required_menu_slots(skip_meals: dict[str, list[str]]) -> set[tuple[str, str]]:
    skipped = {
        (str(day).strip().lower(), str(meal).strip().lower())
        for day, meals in (skip_meals or {}).items()
        for meal in meals or []
    }
    return set(ALL_MENU_SLOTS) - skipped


async def run_job(job_name: str, settings: Settings) -> str:
    """Run one canned scheduled prompt and record telemetry either way.

    Used both by the cron scheduler and by the on-demand `/invoke/{job_name}` route,
    so a manual "run now" from chatui produces identical telemetry to an autonomous run.
    """
    if job_name not in SCHEDULED_REQUESTS:
        raise ValueError(f"Unknown job: {job_name}")
    role = JOB_ROLES[job_name]
    request = SCHEDULED_REQUESTS[job_name]
    result_model = JOB_RESULT_MODELS.get(job_name)
    require_tool_counts = JOB_REQUIRED_TOOL_COUNTS.get(job_name)
    required_menu_slots = None
    if job_name == "weekly_menu":
        planning_snapshot = await _fetch_planning_snapshot(settings)
        required_menu_slots = _required_menu_slots(planning_snapshot["skip_meals"])
        skipped_count = len(ALL_MENU_SLOTS) - len(required_menu_slots)
        skip_note = f", except {skipped_count} slot(s) the household has marked skipped this week" if skipped_count else ""
        request = request.format(slot_count=len(required_menu_slots), skip_note=skip_note)
        require_tool_counts = {"add_weekly_menu_item": len(required_menu_slots)}
        # Written before the agent runs (not after) so a stale dish from an earlier week
        # is already replaced by the time the agent's own send_weekly_plan_email call
        # (mid-run) reads the saved menu back - independent of whether this run's
        # planning ultimately succeeds, since skip_meals is the household's own config.
        await record_skipped_menu_slots(settings, sorted(ALL_MENU_SLOTS - required_menu_slots))
    logger.info("Running job: %s (role=%s)", job_name, role)
    try:
        result = await run_agent(
            role, request, settings,
            remember=False, trace=False, job_name=job_name,
            require_tools=JOB_REQUIRED_TOOLS.get(job_name),
            require_tool_counts=require_tool_counts,
            required_menu_slots=required_menu_slots,
            response_format=result_model,
        )
        if result_model is not None:
            # Best-effort sanity check on the model's structured summary, not a check
            # that the job did its job - the DB writes already happened via tool calls
            # (and require_tools enforced them) regardless of whether the model also
            # produced parseable structured output. Ollama in particular doesn't
            # reliably populate structured_response, so a miss here must not flip a real
            # success into a reported failure.
            try:
                result_model.model_validate(json.loads(result))
            except (json.JSONDecodeError, ValidationError) as validation_error:
                logger.warning(
                    "Job %s completed but its summary wasn't valid structured output (%s); "
                    "treating the job as completed since its database writes already happened.",
                    job_name, validation_error,
                )
        logger.info("Job %s completed", job_name)
        if job_name == "weekly_menu":
            # Deterministic, not an LLM tool call - target_menu_days is already resolved
            # by get_job_context's own logic, no re-derivation or agent involvement.
            target_days = build_job_context(settings, "weekly_menu")["job"]["target_menu_days"]
            await record_weekly_plan(
                settings, target_days[0]["date"], target_days[-1]["date"],
                planning_snapshot["skip_meals"], planning_snapshot["chef_note"], planning_snapshot["restrictions"],
            )
        await record_agent_run(role, job_name, "completed", settings, result=result)
        return result
    except Exception as error:
        logger.exception("Job %s failed", job_name)
        await record_agent_run(role, job_name, "failed", settings, error=str(error))
        raise
