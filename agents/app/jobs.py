from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from .config import Settings
from .kitchen_agent import run_agent
from .models import ExecutiveChefResult, FoodInspectorResult, PantryManagerResult, SousChefResult
from .telemetry import record_agent_run

logger = logging.getLogger("kitchenhq-agent")

# Each scheduled prompt is self-contained: one PURPOSE line, then the exact ordered
# steps for THIS run. Role prompts (prompts/*.md) hold only standing behaviour -
# anything job-specific (which day, which meals, the time cap, which email) lives here.

_PREP_STEPS = """\
2. job.target_menu_days from get_job_context holds the exact weekday(s) for {day_phrase}. Load the weekly_menu rows for {meal_scope} on those weekday(s) - the table is keyed by weekday name, not date.
3. Call get_household_preferences and get_inventory. Match each ingredient the task will actually use to its exact item_name spelling in inventory, and let any household member's dietary preferences or health conditions shape the instructions (e.g. keep an allergen out, note a substitution).
4. Save with add_detailed_prep_schedule ({time_cap}): detailed_instructions is your ordered list of instruction-step strings (one step per list entry, no numbering); ingredients_used is [{{item_name, quantity, unit}}] for every ingredient matched in step 3, using the item_name exactly as it appears in inventory - this is what lets inventory deduct automatically once a human checks the task complete, so do not omit an ingredient that has a matching inventory row. Give each unit as g/kg, ml/l or pcs matching that item's inventory dimension (tsp/tbsp/cup are accepted and auto-approximated to g/ml); the quantity is converted into the row's own unit on deduction, so match the dimension, not the exact unit. This save is the required outcome - you are not finished until it succeeds.
5. Call send_prep_task_email: prep_date is the date in job.target_menu_days, meals is [{{dish, meal_type, servings}}] for each dish (servings = household size, from get_household_preferences' household_members), steps is your instructions, ingredients is what will be used.
6. Reply with a two-sentence summary naming the dishes and the saved prep_schedule id(s)."""

SCHEDULED_REQUESTS = {
    "weekly_menu": """\
PURPOSE: replace the saved weekly menu with a fresh, complete plan for the coming Monday-to-Sunday week - 28 slots: all seven days (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday AND Sunday) x breakfast, lunch, snack, dinner.
1. Call get_job_context.
2. Call get_household_preferences. The chef note and favourite dishes are OPTIONAL - if empty, ignore them and continue; do not stop.
3. Call get_inventory, then get_weekly_menu to see what is currently saved.
4. Decide a dish for every one of the 28 slots, including Saturday and Sunday - plan the weekend fresh, do not leave the currently-saved weekend dishes in place. Rules: follow every dietary and macro rule; lunches must be vegetarian with NO egg, meat or fish and there must be at least 5 DISTINCT lunch dishes across the week; chicken only at dinner.
5. Save each slot with its own add_weekly_menu_item call (day_of_week, meal_type, dish_name, is_kid_friendly, macros, ingredients as a list of ingredient strings, full_recipe as a list of method-step strings). Overwriting an existing slot is expected. Saving all 28 DISTINCT day/meal slots is the required outcome - you are not finished until every one of the seven days has all four meals saved.
6. Call validate_weekly_menu_policy with no arguments to check the saved week. If it returns violations, fix those slots with more add_weekly_menu_item calls and validate again, until it returns valid.
7. Call send_weekly_plan_email: week_start and week_end are the first and last dates in job.target_menu_days; considerations is your reasoning (favourites used, how the rules were met, inventory gaps); shopping_needs is the ingredients likely to be bought. Do NOT pass days - the tool reads the saved menu itself.
8. Reply in plain text with a two-sentence summary of the week and whether the email sent.""",
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
2. Call get_household_preferences so you judge against the same chef note, favourites, and household members' preferences/conditions the Executive Chef had.
3. Call get_unaudited_weekly_menu_items. If it returns nothing, there is nothing to audit this run - say so and stop.
4. For every row returned, judge it against the dietary/macro rules (lunches vegetarian with no egg/meat/fish, chicken dinner-only, etc.) and the household context from step 2, then call record_weekly_menu_audit(weekly_menu_id, score, audit_feedback) for that row - score 0-100, audit_feedback naming what it got right and, if imperfect, exactly what it falls short on. Do this for every row from step 3; do not stop partway.
5. Reply with a short summary of how many rows you scored and any repeat issue worth flagging.""",
    "task_audit": """\
PURPOSE: judge every detailed_prep_schedule row not yet scored against the same rules and preferences the Sous Chef used.
1. Call get_job_context.
2. Call get_household_preferences so you judge against the same household context the Sous Chef had.
3. Call get_unaudited_prep_tasks. If it returns nothing, there is nothing to audit this run - say so and stop.
4. For every row returned (including cancelled ones - you are judging the decision, not whether it was performed), judge the instructions and ingredients_used against the dietary rules and household context from step 2, then call record_prep_task_audit(prep_schedule_id, score, audit_feedback) for that row - score 0-100, audit_feedback naming what it got right and, if imperfect, exactly what it falls short on. Do this for every row from step 3; do not stop partway.
5. Reply with a short summary of how many rows you scored and any repeat issue worth flagging.""",
    "expire_prep_tasks": """\
PURPOSE: housekeeping sweep - expire any prep task a human never acknowledged or cancelled within its 2-hour action window, so stale tasks stop cluttering the task list.
1. Call get_job_context.
2. Call expire_stale_prep_tasks (no arguments) - it finds every detailed_prep_schedule row still 'assigned' with created_at more than 2 hours ago and marks each one 'expired'. It never touches inventory.
3. Reply with a one-sentence summary of how many tasks (if any) were expired, using the tool's returned expired_ids.""",
}

JOB_ROLES = {
    "weekly_menu": "executive_chef",
    "sunday_prep": "sous_chef",
    "nightly_prep": "sous_chef",
    "morning_cooking": "sous_chef",
    "dinner_cooking": "sous_chef",
    "pantry_manager": "pantry_manager",
    "menu_audit": "food_inspector",
    "task_audit": "food_inspector",
    "expire_prep_tasks": "sous_chef",
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
    "task_audit": FoodInspectorResult,
    "expire_prep_tasks": SousChefResult,
}

# The DB write(s) each job exists to make. If the model stops short, run_agent sends
# corrective nudges (see _MAX_FOLLOWUPS) and finally raises rather than recording an
# empty "completed" run. REQUIRED_TOOLS = must be called at least once (an entry may be
# a tuple of alternative tool names, satisfied by calling any one of them); REQUIRED_TOOL_COUNTS
# = must be called at least N times (a full week is 28 add_weekly_menu_item slots). The
# email tools are deliberately not required - a missed email must never fail the job.
JOB_REQUIRED_TOOLS = {
    "weekly_menu": ["validate_weekly_menu_policy"],
    "sunday_prep": ["add_detailed_prep_schedule"],
    "nightly_prep": ["add_detailed_prep_schedule"],
    "morning_cooking": ["add_detailed_prep_schedule"],
    "dinner_cooking": ["add_detailed_prep_schedule"],
    "pantry_manager": ["add_shopping_items"],
    # Only the "did you even check" step is enforced - how many rows get audited varies
    # run to run (some nights there's nothing new to score), so record_*_audit isn't a
    # hard requirement the way add_weekly_menu_item's 28 slots are.
    "menu_audit": ["get_unaudited_weekly_menu_items"],
    "task_audit": ["get_unaudited_prep_tasks"],
    "expire_prep_tasks": ["expire_stale_prep_tasks"],
}

JOB_REQUIRED_TOOL_COUNTS = {
    "weekly_menu": {"add_weekly_menu_item": 28},
}


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
    logger.info("Running job: %s (role=%s)", job_name, role)
    try:
        result = await run_agent(
            role, request, settings,
            remember=False, trace=False, job_name=job_name,
            require_tools=JOB_REQUIRED_TOOLS.get(job_name),
            require_tool_counts=JOB_REQUIRED_TOOL_COUNTS.get(job_name),
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
        await record_agent_run(role, job_name, "completed", settings, result=result)
        return result
    except Exception as error:
        logger.exception("Job %s failed", job_name)
        await record_agent_run(role, job_name, "failed", settings, error=str(error))
        raise
