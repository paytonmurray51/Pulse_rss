import asyncio
import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()


def _run_refresh_sync():
    try:
        asyncio.run(_async_refresh())
    except Exception as e:
        logger.error(f"Scheduler refresh error: {e}")


async def _async_refresh():
    from routers.articles import _run_full_refresh
    await _run_full_refresh()


def start_scheduler():
    interval = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "30"))
    _scheduler.add_job(
        _run_refresh_sync,
        "interval",
        minutes=interval,
        id="feed_refresh",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started with interval {interval} minutes")


def shutdown_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
