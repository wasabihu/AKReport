"""Custom exception handlers to unify error response format."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    """Convert FastAPI HTTPException detail to { error: { code, message } } format."""
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        # Our custom format
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )
    # Default FastAPI format
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc.detail)}},
    )


async def validation_exception_handler(request: Request, exc) -> JSONResponse:
    """Convert Pydantic validation errors to our format."""
    errors = exc.errors()
    messages = [f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "; ".join(messages)}},
    )
