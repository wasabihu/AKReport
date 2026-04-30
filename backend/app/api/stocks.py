"""Stock search endpoint – search by code or Chinese name."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.dependencies import get_cninfo_client

router = APIRouter(tags=["stocks"])


@router.get("/api/stocks/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="股票代码或中文名称关键词"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search stocks by code or Chinese name.

    Uses local CNInfo stock dictionaries for instant fuzzy matching.
    Returns: { data: [{ code, name, market }, ...] }
    """
    client = get_cninfo_client()
    results = await client.search_stocks(q, limit=limit)
    return {"data": results, "message": "ok"}
