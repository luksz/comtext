"""FastAPI application entry point."""
import asyncio
import logging

import structlog
import uvicorn
from fastapi import FastAPI

from pce.api.routes import router
from pce.config import settings
from pce.db.models import Base
from pce.db.session import get_engine, get_session_factory

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level)
    ),
)

log = structlog.get_logger()

app = FastAPI(title="Personal Context Engine", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
async def startup():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("db_ready", path=str(settings.db_path))

    # Start file watcher if watch_dirs configured
    if settings.watch_dirs:
        from pce.connectors.files import start_watcher
        loop = asyncio.get_event_loop()
        start_watcher(loop)

    # Schedule background embedding job
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from pce.ingestion.embedder import embed_pending
    scheduler = AsyncIOScheduler()
    scheduler.add_job(embed_pending, "interval", minutes=1, id="embed_pending")
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("scheduler_started")


@app.on_event("shutdown")
async def shutdown():
    if settings.watch_dirs:
        from pce.connectors.files import stop_watcher
        stop_watcher()
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)


def serve():
    uvicorn.run("pce.main:app", host="127.0.0.1", port=settings.port, reload=False)
