import os
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase


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

# Keep the pool small. This is a single-user app, and the Cloud SQL instance
# may be shared with other services that need their own connection headroom.
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


# create_all() creates missing tables but never alters existing ones, so
# columns added after a deploy have to be applied by hand. These are written
# to be safe to run on every startup.
_MIGRATIONS = (
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS ai_full_summary TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS ai_full_summary_at TIMESTAMPTZ",
)


async def run_migrations(conn):
    from sqlalchemy import text
    for statement in _MIGRATIONS:
        await conn.execute(text(statement))


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
