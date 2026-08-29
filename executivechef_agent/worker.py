"""Autonomous KitchenHQ agent worker."""

from __future__ import annotations

import asyncio
import logging

from agent import KitchenHQAgent, configure_scheduler

logger = logging.getLogger("kitchenhq-worker")


async def main() -> None:
    agents = {
        "executive_chef": KitchenHQAgent("executive_chef"),
        "sous_chef": KitchenHQAgent("sous_chef"),
        "pantry_manager": KitchenHQAgent("pantry_manager"),
    }
    await asyncio.gather(*(agent.start() for agent in agents.values()))
    scheduler = configure_scheduler(agents)
    scheduler.start()
    logger.info("Autonomous agent worker started with timezone %s", scheduler.timezone)
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
