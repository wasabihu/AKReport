"""Async task queue with worker pool and rate limiter integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

from app.config import Settings
from app.models import (
    DownloadResult,
    ItemStatus,
    Market,
    ReportType,
    Task,
    TaskItem,
    TaskStatus,
)
from app.services.cninfo_client import CNInfoClient
from app.services.downloader import Downloader
from app.services.rate_limiter import RateLimiter
from app.storage.repositories import TaskRepository

logger = logging.getLogger(__name__)


class TaskQueue:
    """Manage download tasks with async workers and rate limiting."""

    def __init__(
        self,
        settings: Settings,
        rate_limiter: RateLimiter,
        cninfo_client: CNInfoClient,
        downloader: Downloader,
        repo: TaskRepository,
    ) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._cninfo = cninfo_client
        self._downloader = downloader
        self._repo = repo
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._event_callbacks: list[Callable[[dict], Awaitable[None]]] = []

    def on_event(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        """Register a callback for task events (item updates, task completion)."""
        self._event_callbacks.append(callback)

    async def _emit(self, event: dict) -> None:
        for cb in self._event_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.warning("Event callback error: %s", e)

    async def start(self) -> None:
        """Start the worker pool."""
        if self._running:
            return
        self._running = True
        max_workers = self._settings.max_concurrency
        for i in range(max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        logger.info("Started %d task queue workers", max_workers)

    async def stop(self) -> None:
        """Stop all workers gracefully."""
        self._running = False
        for w in self._workers:
            w.cancel()
        self._workers.clear()
        logger.info("Task queue stopped")

    async def enqueue(self, task_id: str) -> None:
        """Add a task to the queue for processing."""
        await self._queue.put(task_id)
        logger.info("Enqueued task %s", task_id)

    async def _worker(self, worker_id: int) -> None:
        """Worker loop: pick tasks from queue and process items."""
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._process_task(task_id)
            except Exception as e:
                logger.error("Worker %d error processing task %s: %s", worker_id, task_id, e)
                self._repo.update_task_status(task_id, TaskStatus.failed.value)
                await self._emit_log(task_id, "error", None, f"Task failed: {e}")

    async def _process_task(self, task_id: str) -> None:
        """Process all items in a task."""
        task_data = self._repo.get_task(task_id)
        if not task_data:
            return

        # Check if task was cancelled or paused
        if task_data["status"] in (TaskStatus.cancelled.value, TaskStatus.paused.value):
            return

        self._repo.update_task_status(
            task_id, TaskStatus.running.value,
            started_at=datetime.now().isoformat() if not task_data.get("started_at") else None,
        )
        await self._emit_log(task_id, "info", None, "Task started")
        await self._emit({"type": "task_started", "task_id": task_id})

        items = self._repo.get_items(task_id)
        save_dir = Path(task_data["save_dir"])
        overwrite = bool(task_data.get("overwrite_existing", 0))

        for item_row in items:
            # Re-check task status (may have been paused/cancelled)
            current_task = self._repo.get_task(task_id)
            if current_task["status"] in (TaskStatus.cancelled.value, TaskStatus.paused.value):
                break

            item_id = item_row["id"]
            code = item_row["code"]
            market = Market(item_row["market"])
            year = item_row["year"]
            report_type = ReportType(item_row["report_type"])

            try:
                # Step 1: Search for best report
                self._repo.update_item(item_id, ItemStatus.searching.value, "正在检索公告...")
                await self._emit({
                    "type": "item_updated",
                    "task_id": task_id,
                    "item_id": item_id,
                    "code": code,
                    "year": year,
                    "report_type": report_type.value,
                    "status": ItemStatus.searching.value,
                })

                best = await self._cninfo.find_best_report(code, market, year, report_type)

                if not best:
                    self._repo.update_item(
                        item_id, ItemStatus.failed.value,
                        f"未找到符合条件的{year}年{report_type.value}",
                    )
                    await self._emit_log(task_id, "warn", code, f"未找到匹配报告")
                    await self._emit({
                        "type": "item_updated",
                        "task_id": task_id,
                        "item_id": item_id,
                        "code": code,
                        "year": year,
                        "report_type": report_type.value,
                        "status": ItemStatus.failed.value,
                        "message": "未找到匹配报告",
                    })
                    continue

                pdf_url = best.get("pdf_url", "")
                ann_title = best.get("announcement_title", "")
                ann_date = best.get("announcement_date", "")
                sec_name = best.get("sec_name") or item_row.get("name")

                self._repo.update_item(
                    item_id, ItemStatus.downloading.value, "正在下载...",
                    announcement_title=ann_title,
                    pdf_url=pdf_url,
                    name=sec_name,
                )
                await self._emit({
                    "type": "item_updated",
                    "task_id": task_id,
                    "item_id": item_id,
                    "code": code,
                    "year": year,
                    "report_type": report_type.value,
                    "status": ItemStatus.downloading.value,
                })

                # Step 2: Download
                result = await self._downloader.download_report(
                    task_id=task_id,
                    code=code,
                    name=sec_name,
                    market=market,
                    year=year,
                    report_type=report_type,
                    pdf_url=pdf_url,
                    announcement_date=ann_date,
                    save_dir=save_dir,
                    overwrite=overwrite,
                )

                self._repo.update_item(
                    item_id, result.status.value, result.message,
                    file_path=str(result.file_path) if result.file_path else None,
                    name=sec_name,
                )
                await self._emit_log(
                    task_id,
                    "info" if result.status == ItemStatus.success else "warn",
                    code,
                    result.message,
                )
                await self._emit({
                    "type": "item_updated",
                    "task_id": task_id,
                    "item_id": item_id,
                    "code": code,
                    "year": year,
                    "report_type": report_type.value,
                    "status": result.status.value,
                    "message": result.message,
                })

            except Exception as e:
                self._repo.update_item(item_id, ItemStatus.failed.value, f"处理失败: {e}")
                await self._emit_log(task_id, "error", code, str(e))
                await self._emit({
                    "type": "item_updated",
                    "task_id": task_id,
                    "item_id": item_id,
                    "code": code,
                    "year": year,
                    "report_type": report_type.value,
                    "status": ItemStatus.failed.value,
                    "message": str(e),
                })

        # Determine final task status
        stats = self._repo.count_items_by_status(task_id)
        if stats.failed > 0 and stats.success > 0:
            final_status = TaskStatus.completed  # partial success
        elif stats.failed > 0 and stats.success == 0:
            final_status = TaskStatus.failed
        else:
            final_status = TaskStatus.completed

        self._repo.update_task_status(
            task_id, final_status.value,
            finished_at=datetime.now().isoformat(),
        )
        await self._emit_log(task_id, "info", None, f"Task {final_status.value}")
        await self._emit({
            "type": "task_completed",
            "task_id": task_id,
            "status": final_status.value,
        })

    async def _emit_log(self, task_id: str, level: str, code: str | None, message: str) -> None:
        """Write log to DB and emit as SSE log event."""
        from datetime import datetime
        self._repo.add_log(task_id, level, code, message)
        await self._emit({
            "type": "log",
            "task_id": task_id,
            "code": code,
            "level": level,
            "message": message,
            "time": datetime.now().isoformat(),
        })

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a running task."""
        self._repo.update_task_status(task_id, TaskStatus.cancelled.value)
        await self._emit_log(task_id, "info", None, "Task cancelled")

    async def retry_failed_items(self, task_id: str) -> None:
        """Re-queue failed items for a task."""
        items = self._repo.get_items(task_id)
        has_failed = False
        for item_row in items:
            if item_row["status"] == ItemStatus.failed.value:
                self._repo.update_item(item_row["id"], ItemStatus.pending.value, "等待重试")
                has_failed = True
        if has_failed:
            self._repo.update_task_status(task_id, TaskStatus.pending.value)
            await self._queue.put(task_id)
