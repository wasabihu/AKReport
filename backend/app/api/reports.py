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
    """Search for financial report announcements on CNInfo.

    Returns a list of candidate announcements with scores.
    """
    settings = get_settings()
    cninfo = get_cninfo_client()

    try:
        candidates = await cninfo.search_announcements(
            code=req.code,
            market=req.market,
            year=req.year,
            report_type=req.report_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "SEARCH_ERROR", "message": str(e)})

    if not candidates:
        return SuccessResponse(
            data=[],
            message=f"未找到 {req.code} {req.year}年{req.report_type.value} 的匹配公告",
        )

    # Score all candidates and sort by score descending
    from app.services.report_matcher import (
        is_valid_score,
        meets_file_size_requirement,
        score_candidate,
    )

    scored = []
    for c in candidates:
        title = c.get("announcement_title", "")
        s = score_candidate(title, req.year, req.report_type, req.market)
        if is_valid_score(s, settings.score_threshold) and meets_file_size_requirement(
            c, req.report_type, settings.min_annual_report_file_size_bytes
        ):
            c["score"] = s
            # Map sec_name -> name so frontend can display it
            if "sec_name" in c and "name" not in c:
                c["name"] = c["sec_name"]
            scored.append(c)

    scored.sort(key=lambda x: x["score"], reverse=True)

    if not scored:
        return SuccessResponse(
            data=[],
            message=f"未找到 {req.code} {req.year}年{req.report_type.value} 的匹配公告",
        )

    return SuccessResponse(data=scored, message=f"找到 {len(scored)} 条候选公告")
