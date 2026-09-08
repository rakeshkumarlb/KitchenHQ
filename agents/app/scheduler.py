from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Settings
from .jobs import run_job


def configure_scheduler(settings: Settings) -> AsyncIOScheduler:
    # APScheduler's default misfire_grace_time is 1s: if the shared event loop is busy
    # (an in-flight run_agent builds an LLM client + loads MCP tools synchronously) when
    # a cron trigger fires on its round minute, the run is declared "missed" and dropped
    # ("Run time of job ... was missed by 0:00:12"). These jobs are not second-critical,
    # so allow them to start up to an hour late; coalesce collapses a backlog of missed
    # fires (e.g. after the process was down) into a single run.
    scheduler = AsyncIOScheduler(
        timezone=settings.tz,
        job_defaults={"misfire_grace_time": 3600, "coalesce": True, "max_instances": 1},
    )
    scheduler.add_job(run_job, "cron", day_of_week="sat", hour=10, minute=0, args=["weekly_menu", settings], id="weekly-menu", replace_existing=True)
    scheduler.add_job(run_job, "cron", day_of_week="sun", hour=14, minute=0, args=["sunday_prep", settings], id="sunday-prep", replace_existing=True)
    scheduler.add_job(run_job, "cron", day_of_week="sun,mon,tue,wed,thu,fri,sat", hour=20, minute=0, args=["nightly_prep", settings], id="nightly-prep", replace_existing=True)
    scheduler.add_job(run_job, "cron", day_of_week="mon-fri", hour=6, minute=30, args=["morning_cooking", settings], id="morning-cooking", replace_existing=True)
    scheduler.add_job(run_job, "cron", day_of_week="mon-fri", hour=18, minute=0, args=["dinner_cooking", settings], id="dinner-cooking", replace_existing=True)
    scheduler.add_job(run_job, "cron", hour=18, minute=0, args=["pantry_manager", settings], id="pantry-manager-daily", replace_existing=True)
    return scheduler
