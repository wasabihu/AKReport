from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──


class Market(str, Enum):
    a_share = "A股"
    hk = "港股"
    auto = "auto"


class ReportType(str, Enum):
    annual = "年报"
    q1 = "一季报"
    half = "半年报"
    q3 = "三季报"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ItemStatus(str, Enum):
    pending = "pending"
    searching = "searching"
    downloading = "downloading"
    success = "success"
    failed = "failed"
    skipped = "skipped"


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warn = "warn"
    error = "error"


# ── API Request Models ──


class ReportSearchRequest(BaseModel):
    code: str
    market: Market
    year: int
    report_type: ReportType


class CreateTaskRequest(BaseModel):
    codes: list[str] = Field(..., min_length=1)
    market_mode: Market = Market.auto
    years: list[int] = Field(..., min_length=1)
    report_types: list[ReportType] = Field(..., min_length=1)
    save_dir: Path
    request_interval_seconds: float = 2.0
    concurrency: int = 1
    auto_slowdown: bool = True
    overwrite_existing: bool = False


# ── Service Layer Models ──


class ReportCandidate(BaseModel):
    market: Market
    code: str
    name: str | None = None
    year: int
    report_type: ReportType
    announcement_title: str
    announcement_date: date
    announcement_id: str | None = None
    org_id: str | None = None
    detail_url: str | None = None
    pdf_url: str
    score: int


class DownloadResult(BaseModel):
    task_id: str
    code: str
    market: Market
    year: int
    report_type: ReportType
    status: ItemStatus
    file_path: Path | None = None
    message: str


class RateLimitSnapshot(BaseModel):
    domain: str
    current_interval: float
    failure_count: int
    last_request_at: datetime | None = None


# ── API Response Models ──


class TaskItemResponse(BaseModel):
    id: str
    code: str
    market: str
    year: int
    report_type: str
    status: ItemStatus
    message: str
    name: str | None = None
    file_path: str | None = None
    announcement_title: str | None = None
    pdf_url: str | None = None


class TaskStats(BaseModel):
    total: int
    success: int
    failed: int
    skipped: int
    pending: int


class TaskDetailResponse(BaseModel):
    id: str
    status: TaskStatus
    market_mode: str
    save_dir: str
    request_interval_seconds: float
    concurrency: int
    auto_slowdown: bool
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    items: list[TaskItemResponse] = []
    stats: TaskStats


class TaskLogEvent(BaseModel):
    time: str
    level: LogLevel
    task_id: str
    code: str | None = None
    message: str


class ItemUpdatedEvent(BaseModel):
    task_id: str
    code: str
    status: ItemStatus
    message: str | None = None


class TaskCompletedEvent(BaseModel):
    task_id: str
    status: TaskStatus


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ErrorDetail(BaseModel):
    code: str
    message: str


class SuccessResponse(BaseModel):
    data: Any = None
    message: str = "ok"


class ItemsResponse(BaseModel):
    items: list[Any] = []
    total: int = 0


# ── Internal Models ──


class TaskItem(BaseModel):
    """Internal model for a single item within a task."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    code: str
    market: Market
    year: int
    report_type: ReportType
    status: ItemStatus = ItemStatus.pending
    message: str = ""
    file_path: str | None = None
    name: str | None = None
    announcement_title: str | None = None
    pdf_url: str | None = None


class Task(BaseModel):
    """Internal model for a download task."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.pending
    market_mode: Market = Market.auto
    save_dir: Path
    request_interval_seconds: float = 2.0
    concurrency: int = 1
    auto_slowdown: bool = True
    overwrite_existing: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    items: list[TaskItem] = []
