import logging
import os
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


def _build_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Construct from parts (used in Cloud Run where DB_PASSWORD comes from Secret Manager)
    user = os.environ.get("DB_USER", "pulse_user")
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    db_name = os.environ.get("DB_NAME", "pulse")
    connection_name = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "")
    if connection_name:
        return f"postgresql+asyncpg://{user}:{password}@/{db_name}?host=/cloudsql/{connection_name}"
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"


DATABASE_URL = _build_database_url()

# Keep the pool small. The Cloud SQL instance is shared with other services
# that need their own connection headroom.
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "3"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "2"))


def create_engine_and_session():
    """Build a fresh engine and its session factory.

    Async connections are bound to the event loop that opened them. The
    scheduler thread starts a new loop per run via asyncio.run(), so it must
    not reuse the module-level engine — it calls this and disposes the result
    when the job finishes.
    """
    new_engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
    )
    factory = async_sessionmaker(
        new_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return new_engine, factory


engine, AsyncSessionLocal = create_engine_and_session()


class Base(DeclarativeBase):
    pass


# ─── migrations ──────────────────────────────────────────────────────────────
#
# create_all() creates missing tables but never alters existing ones. Each
# migration runs at most once, tracked in schema_migrations, so a step may
# safely contain one-shot data changes.

async def _m003_multi_user(conn):
    """Move a single-user install to per-user accounts, scores and state.

    Everything currently on the articles table belongs to the owner, so it is
    copied into article_states / article_scores under their new user id before
    the old columns are dropped.
    """
    owner_email = (os.environ.get("OWNER_EMAIL") or "").strip().lower()

    legacy = (await conn.execute(text(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='articles' AND column_name='ai_score'"
    ))).scalar_one()

    if not owner_email:
        if legacy:
            raise RuntimeError(
                "OWNER_EMAIL must be set before upgrading to multi-user: existing "
                "saves, ratings and scores need an account to belong to. Set it to "
                "the Google address that should own this instance and redeploy."
            )
        logger.warning("OWNER_EMAIL is not set — no owner account was created.")
        return

    await conn.execute(
        text(
            "INSERT INTO users (email, name, is_admin) VALUES (:e, :n, TRUE) "
            "ON CONFLICT (email) DO UPDATE SET is_admin = TRUE"
        ),
        {"e": owner_email, "n": owner_email.split("@")[0]},
    )
    await conn.execute(
        text("INSERT INTO allowed_emails (email, note) VALUES (:e, 'owner') "
             "ON CONFLICT (email) DO NOTHING"),
        {"e": owner_email},
    )
    owner_id = (await conn.execute(
        text("SELECT id FROM users WHERE email = :e"), {"e": owner_email}
    )).scalar_one()

    # Instance-wide refresh settings move off the per-user profile. Default
    # auto-refresh to OFF: scoring is per-person now, so an unattended daily
    # run costs more than it used to and should be opted into deliberately.
    has_profile_cols = (await conn.execute(text(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='user_profiles' AND column_name='refresh_interval_minutes'"
    ))).scalar_one()

    if has_profile_cols:
        await conn.execute(text(
            "INSERT INTO app_settings (id, auto_refresh_enabled, refresh_interval_minutes, "
            "                          last_auto_refresh_at) "
            "SELECT 1, FALSE, COALESCE(refresh_interval_minutes, 1440), last_auto_refresh_at "
            "FROM user_profiles WHERE id = 1 "
            "ON CONFLICT (id) DO NOTHING"
        ))
    await conn.execute(text(
        "INSERT INTO app_settings (id, auto_refresh_enabled, refresh_interval_minutes) "
        "VALUES (1, FALSE, 1440) ON CONFLICT (id) DO NOTHING"
    ))

    # user_profiles: attach to the owner, shed the instance-wide fields.
    await conn.execute(text(
        "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS user_id INTEGER "
        "REFERENCES users(id) ON DELETE CASCADE"
    ))
    await conn.execute(
        text("UPDATE user_profiles SET user_id = :u WHERE user_id IS NULL"),
        {"u": owner_id},
    )
    await conn.execute(text("DELETE FROM user_profiles WHERE user_id IS NULL"))
    await conn.execute(text("ALTER TABLE user_profiles ALTER COLUMN user_id SET NOT NULL"))
    await conn.execute(text(
        "DO $$ BEGIN "
        "  ALTER TABLE user_profiles ADD CONSTRAINT uq_user_profiles_user UNIQUE (user_id); "
        "EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL; END $$"
    ))
    for col in ("refresh_interval_minutes", "auto_refresh_enabled", "last_auto_refresh_at"):
        await conn.execute(text(f"ALTER TABLE user_profiles DROP COLUMN IF EXISTS {col}"))

    # feedback_blocks become per-person.
    await conn.execute(text(
        "ALTER TABLE feedback_blocks ADD COLUMN IF NOT EXISTS user_id INTEGER "
        "REFERENCES users(id) ON DELETE CASCADE"
    ))
    await conn.execute(
        text("UPDATE feedback_blocks SET user_id = :u WHERE user_id IS NULL"), {"u": owner_id}
    )
    await conn.execute(text("ALTER TABLE feedback_blocks ALTER COLUMN user_id SET NOT NULL"))

    if legacy:
        # Preserve reading history before the columns disappear.
        moved_state = (await conn.execute(
            text(
                "INSERT INTO article_states "
                "  (article_id, user_id, read_later, is_read, open_count, user_rating) "
                "SELECT id, :u, read_later, is_read, open_count, user_rating FROM articles "
                "WHERE read_later OR is_read OR open_count > 0 OR user_rating IS NOT NULL "
                "ON CONFLICT DO NOTHING RETURNING 1"
            ),
            {"u": owner_id},
        )).rowcount
        moved_scores = (await conn.execute(
            text(
                "INSERT INTO article_scores "
                "  (article_id, user_id, ai_score, ai_summary, ai_tags, ai_filtered, ai_filter_reason) "
                "SELECT id, :u, ai_score, ai_summary, ai_tags, ai_filtered, ai_filter_reason "
                "FROM articles WHERE ai_processed "
                "ON CONFLICT DO NOTHING RETURNING 1"
            ),
            {"u": owner_id},
        )).rowcount
        logger.info(
            "Migrated %s article states and %s scores to owner %s",
            moved_state, moved_scores, owner_email,
        )

        for col in (
            "ai_score", "ai_summary", "ai_tags", "ai_filtered", "ai_filter_reason",
            "ai_processed", "read_later", "is_read", "open_count", "user_rating",
        ):
            await conn.execute(text(f"ALTER TABLE articles DROP COLUMN IF EXISTS {col}"))


_MIGRATIONS = (
    (
        "001_article_full_summary",
        (
            "ALTER TABLE articles ADD COLUMN IF NOT EXISTS ai_full_summary TEXT",
            "ALTER TABLE articles ADD COLUMN IF NOT EXISTS ai_full_summary_at TIMESTAMPTZ",
        ),
    ),
    (
        "002_daily_auto_refresh",
        (
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS "
            "auto_refresh_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS "
            "last_auto_refresh_at TIMESTAMPTZ",
            "UPDATE user_profiles SET refresh_interval_minutes = 1440 "
            "WHERE refresh_interval_minutes < 1440",
        ),
    ),
    ("003_multi_user", _m003_multi_user),
)


async def run_migrations(conn):
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  name TEXT PRIMARY KEY,"
        "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    ))
    applied = set(
        (await conn.execute(text("SELECT name FROM schema_migrations"))).scalars().all()
    )

    for name, step in _MIGRATIONS:
        if name in applied:
            continue
        logger.info("Applying migration %s", name)
        if callable(step):
            await step(conn)
        else:
            for statement in step:
                await conn.execute(text(statement))
        await conn.execute(
            text("INSERT INTO schema_migrations (name) VALUES (:n)"), {"n": name}
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
