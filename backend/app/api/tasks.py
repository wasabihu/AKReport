"""Task management endpoints: CRUD, SSE events, control actions."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_rate_limiter, get_repo, get_settings
from app.models import (
    CreateTaskRequest,
    ErrorResponse,
    ItemStatus,
    Market,
    ReportType,
    SuccessResponse,
    Task,
    TaskDetailResponse,
    TaskItem,
    TaskStatus,
)
from app.services.report_matcher import infer_market_from_code
from app.services.task_queue import TaskQueue

router = APIRouter(tags=["tasks"])

# Set by main.py during lifespan
_task_queue: TaskQueue | None = None


def set_task_queue(tq: TaskQueue) -> None:
    global _task_queue
    _task_queue = tq


def _get_task_queue() -> TaskQueue:
    assert _task_queue is not None, "Task queue not initialized"
    return _task_queue


@router.post(
    "/api/tasks",
    response_model=SuccessResponse,
    responses={400: {"model": ErrorResponse}},
)
async def create_task(req: CreateTaskRequest):
    """Create a new download task."""
    rate_limiter = get_rate_limiter()
    settings = get_settings()
    repo = get_repo()

    # Validate interval
    if not rate_limiter.validate_interval(req.request_interval_seconds):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INTERVAL", "message": f"请求间隔不能低于{settings.min_request_interval_seconds}秒"},
        )

    # Validate concurrency
    if not rate_limiter.validate_concurrency(req.concurrency, settings.max_concurrency):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CONCURRENCY", "message": f"并发数必须在1-{settings.max_concurrency}之间"},
        )

    # Create task
    task = Task(
        market_mode=req.market_mode,
        save_dir=req.save_dir,
        request_interval_seconds=req.request_interval_seconds,
        concurrency=req.concurrency,
        auto_slowdown=req.auto_slowdown,
        overwrite_existing=req.overwrite_existing,
    )

    # Create items: one per (code, year, report_type) combination
    items: list[TaskItem] = []
    for code in req.codes:
        for year in req.years:
            for rt in req.report_types:
                market = req.market_mode
                if market == Market.auto:
                    market = infer_market_from_code(code)
                items.append(
                    TaskItem(
                        task_id=task.id,
                        code=code,
                        market=market,
                        year=year,
                        report_type=rt,
                    )
                )

    task.items = items

    # Persist
    repo.create_task(task)
    repo.create_items(items)

    # Enqueue
    tq = _get_task_queue()
    await tq.enqueue(task.id)

    return SuccessResponse(
        data={"task_id": task.id, "status": task.status.value, "item_count": len(items)},
        message="任务已创建",
    )


@router.get(
    "/api/tasks/{task_id}",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_task_detail(task_id: str):
    """Get task detail including items and stats."""
    repo = get_repo()
    detail = repo.get_task_detail(task_id)
    if not detail:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})
    return SuccessResponse(data=detail.model_dump(), message="ok")


@router.get("/api/tasks", response_model=SuccessResponse)
async def list_tasks(limit: int = 50, offset: int = 0):
    """List all tasks."""
    repo = get_repo()
    tasks = repo.list_tasks(limit, offset)
    return SuccessResponse(data=tasks, message="ok")


@router.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str, request: Request):
    """SSE endpoint for real-time task updates."""

    async def event_generator() -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def on_event(event: dict) -> None:
            if event.get("task_id") == task_id:
                await queue.put(event)

        tq = _get_task_queue()
        tq.on_event(on_event)

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"event": event.get("type", "update"), "data": json.dumps(event, ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"type": "ping"})}
        finally:
            if on_event in tq._event_callbacks:
                tq._event_callbacks.remove(on_event)

    return EventSourceResponse(event_generator())


@router.post(
    "/api/tasks/{task_id}/cancel",
    response_model=SuccessResponse,
)
async def cancel_task(task_id: str):
    """Cancel a running task."""
    repo = get_repo()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})

    tq = _get_task_queue()
    await tq.cancel_task(task_id)
    return SuccessResponse(message="任务已取消")


@router.post(
    "/api/tasks/{task_id}/retry-failed",
    response_model=SuccessResponse,
)
async def retry_failed(task_id: str):
    """Retry failed items in a task."""
    repo = get_repo()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})

    tq = _get_task_queue()
    await tq.retry_failed_items(task_id)
    return SuccessResponse(message="失败项已重新入队")


@router.post(
    "/api/tasks/{task_id}/resume",
    response_model=SuccessResponse,
)
async def resume_task(task_id: str):
    """Resume a paused task."""
    repo = get_repo()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})

    repo.update_task_status(task_id, TaskStatus.pending.value)
    tq = _get_task_queue()
    await tq.enqueue(task_id)
    return SuccessResponse(message="任务已恢复")
