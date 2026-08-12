import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()

# How often to wake and check whether a refresh is due. This is not the
# refresh cadence — that lives in the database so it can be changed from
# Settings without a redeploy. The tick only needs to be finer-grained than
# the shortest cadence offered in the UI (hourly).
TICK_MINUTES = int(os.environ.get("SCHEDULER_TICK_MINUTES", "15"))

DEFAULT_INTERVAL_MINUTES = 1440  # once a day


def _run_refresh_sync():
    try:
        asyncio.run(_tick())
    except Exception as e:
        logger.error("Scheduler tick failed: %s", e)


async def _tick():
    """Refresh only if auto-refresh is on and the cadence has elapsed."""
    from sqlalchemy import select

    from database import create_engine_and_session
    from models import UserProfile
    from routers.articles import _run_full_refresh

    scheduler_engine, session_factory = create_engine_and_session()
    try:
        async with session_factory() as db:
            result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
            profile = result.scalar_one_or_none()

            if profile and not profile.auto_refresh_enabled:
                logger.info("Auto-refresh is off — skipping tick")
                return

            interval = (
                profile.refresh_interval_minutes if profile else DEFAULT_INTERVAL_MINUTES
            )
            last = profile.last_auto_refresh_at if profile else None

            if last is not None:
                elapsed = datetime.now(timezone.utc) - last
                remaining = timedelta(minutes=interval) - elapsed
                if remaining > timedelta(0):
                    logger.info(
                        "Next auto-refresh in %d min (cadence %d min)",
                        int(remaining.total_seconds() // 60), interval,
                    )
                    return

        logger.info("Auto-refresh due (cadence %d min) — starting", interval)
        await _run_full_refresh(session_factory=session_factory)
    finally:
        await scheduler_engine.dispose()


def start_scheduler():
    _scheduler.add_job(
        _run_refresh_sync,
        "interval",
        minutes=TICK_MINUTES,
        id="feed_refresh",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — checking every %d min; cadence comes from the database",
        TICK_MINUTES,
    )


def shutdown_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
