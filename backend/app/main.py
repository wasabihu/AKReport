"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, import_, reports, settings as settings_api, tasks
from app.api.exception_handlers import http_exception_handler, validation_exception_handler
from app.config import Settings
from app.dependencies import (
    get_cninfo_client,
    get_downloader,
    get_rate_limiter,
    get_repo,
    get_settings,
    init_dependencies,
)
from app.services.task_queue import TaskQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    settings = Settings()
    init_dependencies(settings)
    logger.info("Initialized dependencies")

    # Start task queue
    from app.dependencies import _rate_limiter, _cninfo_client, _downloader, _repo

    task_queue = TaskQueue(
        settings=settings,
        rate_limiter=_rate_limiter,
        cninfo_client=_cninfo_client,
        downloader=_downloader,
        repo=_repo,
    )
    await task_queue.start()
    tasks.set_task_queue(task_queue)
    logger.info("Task queue started")

    yield

    # Shutdown
    await task_queue.stop()
    await _cninfo_client.close()
    await _downloader.close()
    from app.dependencies import _database
    if _database:
        _database.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="AKShare Wasa",
    version="0.1.0",
    lifespan=lifespan,
)

# Custom exception handlers for unified { error: { code, message } } format
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(reports.router)
app.include_router(tasks.router)
app.include_router(settings_api.router)
app.include_router(import_.router)
