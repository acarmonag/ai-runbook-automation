"""
ARQ worker entrypoint.

Start with: python -m worker.main
Or via Docker: the agent-worker service runs this directly.
"""

import logging
import os

from arq import cron
from arq.connections import RedisSettings

from worker.jobs import process_alert

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


async def startup(ctx: dict) -> None:  # type: ignore[type-arg]
    """Called once when the worker process starts."""
    import redis.asyncio as aioredis
    from db.database import create_tables

    logger.info("Worker starting up — creating DB tables if needed")
    await create_tables()

    # Store a Redis client in ctx for pub/sub publishing
    ctx["redis"] = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Worker ready")


async def shutdown(ctx: dict) -> None:  # type: ignore[type-arg]
    await ctx["redis"].aclose()
    logger.info("Worker shut down")


class WorkerSettings:
    functions = [process_alert]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = int(os.environ.get("NUM_WORKERS", "4"))
    job_timeout = 600  # 10 min max per incident
    keep_result = 3600  # keep job results for 1 hour
    retry_jobs = True
    max_tries = 3


if __name__ == "__main__":
    import asyncio
    from arq import run_worker

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_worker(WorkerSettings)
