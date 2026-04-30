"""Report search endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies import get_cninfo_client, get_settings
from app.models import ErrorResponse, Market, ReportSearchRequest, ReportType, SuccessResponse

router = APIRouter(tags=["reports"])


@router.post(
    "/api/reports/search",
    response_model=SuccessResponse,
    responses={400: {"model": ErrorResponse}},
)
async def search_reports(req: ReportSearchRequest):
    """Search for financial report announcements on CNInfo."""
    settings = get_settings()
    cninfo = get_cninfo_client()

    try:
        best = await cninfo.find_best_report(
            code=req.code,
            market=req.market,
            year=req.year,
            report_type=req.report_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "SEARCH_ERROR", "message": str(e)})

    if not best:
        return SuccessResponse(
            data=None,
            message=f"未找到 {req.code} {req.year}年{req.report_type.value} 的匹配公告",
        )

    return SuccessResponse(data=best, message="ok")
