"""Stock history endpoint (recent / favourite stocks)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import get_cninfo_client, get_repo
from app.models import ErrorResponse, Market, SuccessResponse
from app.services.report_matcher import infer_market_from_code, normalize_stock_code

router = APIRouter(tags=["stock-history"])


class StockHistoryUpsert(BaseModel):
    code: str
    name: str | None = None
    market: str


@router.get(
    "/api/stock-history",
    response_model=SuccessResponse,
    responses={500: {"model": ErrorResponse}},
)
async def list_stock_history(limit: int = 20):
    """Return recent stock history."""
    repo = get_repo()
    rows = repo.get_stock_history(limit=limit)
    rows = await _enrich_stock_history_rows(rows)
    return SuccessResponse(data=rows, message="ok")


@router.post(
    "/api/stock-history",
    response_model=SuccessResponse,
    responses={500: {"model": ErrorResponse}},
)
async def upsert_stock_history(body: StockHistoryUpsert):
    """Upsert a stock into history."""
    repo = get_repo()
    stock_info = await _resolve_stock_info(body.code, body.market)
    repo.upsert_stock_history(
        code=stock_info["code"],
        name=stock_info["name"] or body.name or None,
        market=stock_info["market"],
    )
    return SuccessResponse(message="ok")


async def _enrich_stock_history_rows(rows: list[dict]) -> list[dict]:
    repo = get_repo()
    enriched: list[dict] = []

    for row in rows:
        stock_info = await _resolve_stock_info(str(row["code"]), str(row["market"]))
        next_row = row.copy()
        next_row["code"] = stock_info["code"]
        next_row["name"] = stock_info["name"] or row.get("name") or None
        next_row["market"] = stock_info["market"]
        enriched.append(next_row)

        if (
            next_row["code"] != row.get("code")
            or next_row["name"] != row.get("name")
            or next_row["market"] != row.get("market")
        ):
            repo.update_stock_history_metadata(
                original_code=str(row["code"]),
                code=next_row["code"],
                name=next_row["name"],
                market=next_row["market"],
            )

    return enriched


async def _resolve_stock_info(code: str, market: str) -> dict[str, str]:
    try:
        market_value = Market(market)
    except ValueError:
        market_value = Market.auto

    try:
        return await get_cninfo_client().get_stock_info(code, market_value)
    except Exception:
        resolved_market = infer_market_from_code(code) if market_value == Market.auto else market_value
        return {
            "code": normalize_stock_code(code, resolved_market),
            "name": "",
            "market": resolved_market.value,
            "org_id": "",
        }


@router.delete(
    "/api/stock-history/{code}",
    response_model=SuccessResponse,
    responses={500: {"model": ErrorResponse}},
)
async def delete_stock_history(code: str):
    """Remove a single stock from history."""
    repo = get_repo()
    repo.delete_stock_history(code)
    return SuccessResponse(message="ok")


@router.delete(
    "/api/stock-history",
    response_model=SuccessResponse,
    responses={500: {"model": ErrorResponse}},
)
async def clear_stock_history():
    """Clear all stock history."""
    repo = get_repo()
    repo.clear_stock_history()
    return SuccessResponse(message="ok")
