"""Health check endpoint."""
from fastapi import APIRouter

from app.dependencies import get_settings
from app.models import SuccessResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=SuccessResponse)
async def health_check():
    settings = get_settings()
    return SuccessResponse(
        data={
            "status": "ok",
            "app_name": settings.app_name,
            "version": settings.app_version,
        },
        message="ok",
    )
