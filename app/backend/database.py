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

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
