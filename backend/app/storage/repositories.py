"""Repository layer for SQLite CRUD operations."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.models import (
    ItemStatus,
    LogLevel,
    Task,
    TaskDetailResponse,
    TaskItem,
    TaskItemResponse,
    TaskStats,
    TaskStatus,
)


class TaskRepository:
    """CRUD for tasks, items, candidates, and logs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Tasks ──

    def create_task(self, task: Task) -> None:
        self._conn.execute(
            """INSERT INTO tasks
               (id, status, market_mode, save_dir, request_interval_seconds,
                concurrency, auto_slowdown, overwrite_existing, created_at,
                started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.status.value, task.market_mode.value,
                str(task.save_dir), task.request_interval_seconds,
                task.concurrency, int(task.auto_slowdown),
                int(task.overwrite_existing), task.created_at,
                task.started_at, task.finished_at,
            ),
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_task_status(
        self, task_id: str, status: str, **kwargs: Any
    ) -> None:
        sets = ["status = ?"]
        values: list[Any] = [status]
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            values.append(val)
        values.append(task_id)
        self._conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values
        )
        self._conn.commit()

    def list_tasks(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Items ──

    def create_item(self, item: TaskItem) -> None:
        self._conn.execute(
            """INSERT INTO task_items
               (id, task_id, code, market, year, report_type, status,
                message, file_path, file_size, name, announcement_title, pdf_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id, item.task_id, item.code, item.market.value,
                item.year, item.report_type.value, item.status.value,
                item.message, item.file_path, item.file_size,
                item.name,
                item.announcement_title, item.pdf_url,
            ),
        )
        self._conn.commit()

    def create_items(self, items: list[TaskItem]) -> None:
        data = [
            (
                item.id, item.task_id, item.code, item.market.value,
                item.year, item.report_type.value, item.status.value,
                item.message, item.file_path, item.file_size,
                item.name,
                item.announcement_title, item.pdf_url,
            )
            for item in items
        ]
        self._conn.executemany(
            """INSERT INTO task_items
               (id, task_id, code, market, year, report_type, status,
                message, file_path, file_size, name, announcement_title, pdf_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            data,
        )
        self._conn.commit()

    def get_items(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM task_items WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_item(
        self, item_id: str, status: str, message: str = "",
        file_path: str | None = None,
        file_size: int | None = None,
        announcement_title: str | None = None,
        pdf_url: str | None = None,
        name: str | None = None,
    ) -> None:
        sets = ["status = ?", "message = ?"]
        values: list[Any] = [status, message]
        if file_path is not None:
            sets.append("file_path = ?")
            values.append(file_path)
        if file_size is not None:
            sets.append("file_size = ?")
            values.append(file_size)
        if announcement_title is not None:
            sets.append("announcement_title = ?")
            values.append(announcement_title)
        if pdf_url is not None:
            sets.append("pdf_url = ?")
            values.append(pdf_url)
        if name is not None:
            sets.append("name = ?")
            values.append(name)
        values.append(item_id)
        self._conn.execute(
            f"UPDATE task_items SET {', '.join(sets)} WHERE id = ?", values
        )
        self._conn.commit()

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM task_items WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row) if row else None

    def count_items_by_status(self, task_id: str) -> TaskStats:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM task_items WHERE task_id = ? GROUP BY status",
            (task_id,),
        ).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}
        total = sum(counts.values())
        return TaskStats(
            total=total,
            success=counts.get("success", 0),
            failed=counts.get("failed", 0),
            skipped=counts.get("skipped", 0),
            pending=counts.get("pending", 0) + counts.get("searching", 0) + counts.get("downloading", 0),
        )

    # ── Candidates ──

    def save_candidates(
        self, item_id: str, candidates: list[dict[str, Any]]
    ) -> None:
        data = [
            (
                item_id,
                c.get("announcement_title", ""),
                c.get("announcement_date", ""),
                c.get("pdf_url", ""),
                c.get("score", 0),
                c.get("raw_json", ""),
            )
            for c in candidates
        ]
        self._conn.executemany(
            """INSERT INTO report_candidates
               (task_item_id, announcement_title, announcement_date, pdf_url, score, raw_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            data,
        )
        self._conn.commit()

    def get_candidates(self, item_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM report_candidates WHERE task_item_id = ?",
            (item_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Logs ──

    def add_log(
        self,
        task_id: str,
        level: str = "info",
        code: str | None = None,
        message: str = "",
    ) -> None:
        self._conn.execute(
            """INSERT INTO task_logs (task_id, code, level, message, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (task_id, code, level, message, datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_logs(
        self, task_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM task_logs WHERE task_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Composite ──

    def get_task_detail(self, task_id: str) -> TaskDetailResponse | None:
        """Get full task detail including items and stats."""
        task_row = self.get_task(task_id)
        if not task_row:
            return None

        item_rows = self.get_items(task_id)
        stats = self.count_items_by_status(task_id)

        items = [
            TaskItemResponse(
                id=r["id"],
                code=r["code"],
                market=r["market"],
                year=r["year"],
                report_type=r["report_type"],
                status=ItemStatus(r["status"]),
                message=r["message"],
                name=r.get("name"),
                file_path=r.get("file_path"),
                file_size=r.get("file_size"),
                announcement_title=r.get("announcement_title"),
                pdf_url=r.get("pdf_url"),
            )
            for r in item_rows
        ]

        return TaskDetailResponse(
            id=task_row["id"],
            status=TaskStatus(task_row["status"]),
            market_mode=task_row["market_mode"],
            save_dir=task_row["save_dir"],
            request_interval_seconds=task_row["request_interval_seconds"],
            concurrency=task_row["concurrency"],
            auto_slowdown=bool(task_row["auto_slowdown"]),
            created_at=task_row["created_at"],
            started_at=task_row.get("started_at"),
            finished_at=task_row.get("finished_at"),
            items=items,
            stats=stats,
        )
