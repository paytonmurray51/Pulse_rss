import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()

# How often to wake and check whether a sync is due. Not the sync cadence —
# that lives in app_settings so an admin can change it without a redeploy.
TICK_MINUTES = int(os.environ.get("SCHEDULER_TICK_MINUTES", "15"))

DEFAULT_INTERVAL_MINUTES = 1440  # once a day

# Scoring is per-person now, so an unattended sync costs one pass per active
# reader. Accounts idle longer than this are skipped until they sign in again.
ACTIVE_WITHIN_DAYS = int(os.environ.get("SYNC_ACTIVE_WITHIN_DAYS", "14"))


def _run_refresh_sync():
    try:
        asyncio.run(_tick())
    except Exception as e:
        logger.error("Scheduler tick failed: %s", e)


async def _tick():
    """Sync only if an admin enabled it and the cadence has elapsed."""
    from sqlalchemy import select

    from database import create_engine_and_session
    from models import AppSettings, User
    from routers.articles import ingest_feeds, score_for_user

    scheduler_engine, session_factory = create_engine_and_session()
    try:
        async with session_factory() as db:
            settings = (await db.execute(
                select(AppSettings).where(AppSettings.id == 1)
            )).scalar_one_or_none()

            if settings is None or not settings.auto_refresh_enabled:
                logger.info("Scheduled sync is off — skipping tick")
                return

            interval = settings.refresh_interval_minutes or DEFAULT_INTERVAL_MINUTES
            last = settings.last_auto_refresh_at
            if last is not None:
                remaining = timedelta(minutes=interval) - (datetime.now(timezone.utc) - last)
                if remaining > timedelta(0):
                    logger.info(
                        "Next scheduled sync in %d min (cadence %d min)",
                        int(remaining.total_seconds() // 60), interval,
                    )
                    return

            logger.info("Scheduled sync due (cadence %d min) — starting", interval)
            new_articles = await ingest_feeds(db)

            cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WITHIN_DAYS)
            active = (await db.execute(
                select(User).where(User.last_seen_at >= cutoff)
            )).scalars().all()

            total_scored = 0
            for user in active:
                try:
                    scored, _ = await score_for_user(db, user)
                    total_scored += scored
                except Exception as e:
                    logger.error("Scheduled scoring failed for %s: %s", user.email, e)

            settings.last_auto_refresh_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(
                "Scheduled sync done: %d new articles, %d scores across %d active readers",
                new_articles, total_scored, len(active),
            )
    finally:
        await scheduler_engine.dispose()


def start_scheduler():
    _scheduler.add_job(
        _run_refresh_sync, "interval", minutes=TICK_MINUTES,
        id="feed_refresh", replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — checking every %d min; cadence comes from app_settings",
        TICK_MINUTES,
    )


def shutdown_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
