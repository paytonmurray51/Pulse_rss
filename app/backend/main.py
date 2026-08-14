import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from database import engine, Base, run_migrations
from scheduler import start_scheduler, shutdown_scheduler
from routers import articles, auth, blocks, feeds, interests, members, suggestions

# Without this, refresh-pipeline logger.info() calls never reach Cloud Run.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_migrations(conn)
    start_scheduler()
    yield
    shutdown_scheduler()
    await engine.dispose()


app = FastAPI(title="Pulse RSS", lifespan=lifespan)

# Session cookies mean requests carry credentials, so a wildcard origin is no
# longer acceptable. Same-origin needs no entry; extra dev origins can be
# added through CORS_ORIGINS.
_origins = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(feeds.router, prefix="/api/feeds", tags=["feeds"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(interests.router, prefix="/api/interests", tags=["interests"])
app.include_router(blocks.router, prefix="/api/blocks", tags=["blocks"])
app.include_router(members.router, prefix="/api/members", tags=["members"])
app.include_router(suggestions.router, prefix="/api/suggestions", tags=["suggestions"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return FileResponse(str(STATIC_DIR / "index.html"))
