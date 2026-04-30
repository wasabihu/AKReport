"""Settings read/update endpoint."""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.dependencies import get_rate_limiter, get_settings
from app.models import ErrorResponse, RateLimitSnapshot, SuccessResponse

router = APIRouter(tags=["settings"])


@router.get("/api/settings", response_model=SuccessResponse)
async def get_settings_api():
    """Get current application settings."""
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    return SuccessResponse(
        data={
            "request_interval_seconds": rate_limiter.base_interval,
            "concurrency": settings.default_concurrency,
            "auto_slowdown": settings.auto_slowdown,
            "default_save_dir": str(settings.default_save_dir),
            "default_request_interval_seconds": settings.default_request_interval_seconds,
            "min_request_interval_seconds": settings.min_request_interval_seconds,
            "max_concurrency": settings.max_concurrency,
            "max_retries": settings.max_retries,
            "score_threshold": settings.score_threshold,
            "rate_limit_snapshots": [s.model_dump() for s in rate_limiter.snapshot()],
        },
        message="ok",
    )


@router.put(
    "/api/settings",
    response_model=SuccessResponse,
    responses={400: {"model": ErrorResponse}},
)
async def update_settings(body: dict):
    """Update application settings (interval, concurrency limits)."""
    settings = get_settings()
    rate_limiter = get_rate_limiter()

    if "request_interval_seconds" in body or "default_request_interval_seconds" in body:
        new_interval = body.get("request_interval_seconds", body.get("default_request_interval_seconds"))
        if not rate_limiter.validate_interval(new_interval):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INTERVAL", "message": f"间隔不能低于{settings.min_request_interval_seconds}秒"},
            )
        settings.default_request_interval_seconds = new_interval
        rate_limiter.base_interval = new_interval

    if "concurrency" in body:
        new_concurrency = int(body["concurrency"])
        if not rate_limiter.validate_concurrency(new_concurrency, settings.max_concurrency):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CONCURRENCY", "message": f"并发数必须在 1-{settings.max_concurrency} 之间"},
            )
        settings.default_concurrency = new_concurrency

    if "auto_slowdown" in body:
        settings.auto_slowdown = bool(body["auto_slowdown"])

    if "default_save_dir" in body:
        settings.default_save_dir = Path(body["default_save_dir"]).expanduser()

    if "score_threshold" in body:
        settings.score_threshold = int(body["score_threshold"])

    return SuccessResponse(
        data={
            "request_interval_seconds": rate_limiter.base_interval,
            "concurrency": settings.default_concurrency,
            "auto_slowdown": settings.auto_slowdown,
            "default_save_dir": str(settings.default_save_dir),
            "default_request_interval_seconds": rate_limiter.base_interval,
            "min_request_interval_seconds": settings.min_request_interval_seconds,
            "max_concurrency": settings.max_concurrency,
            "score_threshold": settings.score_threshold,
        },
        message="设置已更新",
    )
