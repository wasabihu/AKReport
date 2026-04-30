"""CNInfo (巨潮资讯) API client."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models import Market, ReportType
from app.services.rate_limiter import RateLimiter
from app.services.report_matcher import (
    derive_date_range,
    get_keywords,
    normalize_stock_code,
    select_best_candidate,
)


class CNInfoClient:
    """Client for CNInfo public APIs with rate limiting and caching."""

    def __init__(self, settings: Settings, rate_limiter: RateLimiter) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        )
        self._stock_dicts: dict[str, dict[str, str]] = {}  # code -> orgId
        self._stock_dicts_loaded_at: float = 0

    async def _ensure_stock_dict(self, market: Market) -> dict[str, str]:
        """Load and cache stock dictionary for the given market."""
        cache_key = market.value
        now = time.time()
        if (
            cache_key in self._stock_dicts
            and now - self._stock_dicts_loaded_at < self._settings.stock_dict_cache_ttl_seconds
        ):
            return self._stock_dicts[cache_key]

        domain = "www.cninfo.com.cn"
        await self._rate_limiter.acquire(domain)

        if market == Market.hk:
            url = f"{self._settings.cninfo_base_url}/new/data/hke_stock.json"
        else:
            url = f"{self._settings.cninfo_base_url}/new/data/szse_stock.json"

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            await self._rate_limiter.record_success(domain)
        except Exception as e:
            await self._rate_limiter.record_failure(domain, str(e))
            raise

        data = resp.json()
        code_to_orgid: dict[str, str] = {}
        # stockList is the typical key
        items = data.get("stockList", data if isinstance(data, list) else [])
        for item in items:
            code = str(item.get("code", "")).strip()
            org_id = str(item.get("orgId", "")).strip()
            if code:
                code_to_orgid[code] = org_id

        self._stock_dicts[cache_key] = code_to_orgid
        self._stock_dicts_loaded_at = now
        return code_to_orgid

    async def search_announcements(
        self,
        code: str,
        market: Market,
        year: int,
        report_type: ReportType,
    ) -> list[dict[str, Any]]:
        """Search announcements on CNInfo and return raw candidate list."""
        norm_code = normalize_stock_code(code, market)
        stock_dict = await self._ensure_stock_dict(market)
        org_id = stock_dict.get(norm_code, "")

        column = "hke" if market == Market.hk else "szse"
        start_date, end_date = derive_date_range(year, report_type)
        keywords = get_keywords(market, report_type)

        all_candidates: list[dict[str, Any]] = []
        page_num = 1

        for keyword in keywords:
            page_num = 1
            has_more = True
            while has_more:
                domain = "www.cninfo.com.cn"
                await self._rate_limiter.acquire(domain)

                payload = {
                    "pageNum": str(page_num),
                    "pageSize": "30",
                    "column": column,
                    "tabName": "fulltext",
                    "stock": f"{norm_code},{org_id}" if org_id else norm_code,
                    "searchkey": keyword,
                    "category": "",
                    "seDate": f"{start_date}~{end_date}",
                    "isHLtitle": "true",
                }

                try:
                    resp = await self._client.post(
                        f"{self._settings.cninfo_base_url}/new/hisAnnouncement/query",
                        data=payload,
                    )
                    resp.raise_for_status()
                    await self._rate_limiter.record_success(domain)
                except Exception as e:
                    await self._rate_limiter.record_failure(domain, str(e))
                    break

                result = resp.json()
                announcements = result.get("announcements", [])
                if not announcements:
                    has_more = False
                    continue

                for ann in announcements:
                    title = ann.get("announcementTitle", "")
                    adjunct_url = ann.get("adjunctUrl", "")
                    ann_date_ts = ann.get("announcementTime", 0)

                    # Convert timestamp to date string
                    if ann_date_ts:
                        ann_date = date.fromtimestamp(ann_date_ts / 1000)
                    else:
                        ann_date = date.today()

                    pdf_url = (
                        f"{self._settings.cninfo_static_base_url}/{adjunct_url}"
                        if adjunct_url
                        else ""
                    )

                    all_candidates.append({
                        "announcement_title": title,
                        "announcement_date": ann_date.isoformat(),
                        "announcement_id": ann.get("announcementId", ""),
                        "org_id": ann.get("orgId", org_id),
                        "detail_url": ann.get("adjunctUrl", ""),
                        "pdf_url": pdf_url,
                        "adjunct_url": adjunct_url,
                        "raw_json": json.dumps(ann, ensure_ascii=False),
                    })

                total_ann = result.get("totalAnnouncement", 0)
                has_more = page_num * 30 < total_ann
                page_num += 1

            # If we found candidates with this keyword, try next keyword only if empty
            if all_candidates:
                break

        return all_candidates

    async def find_best_report(
        self,
        code: str,
        market: Market,
        year: int,
        report_type: ReportType,
    ) -> dict | None:
        """Search and select the best matching report candidate."""
        candidates = await self.search_announcements(code, market, year, report_type)
        if not candidates:
            # Try expanding date range by ±1 year
            expanded_candidates = await self._search_with_expanded_range(
                code, market, year, report_type
            )
            candidates = expanded_candidates

        best = select_best_candidate(
            candidates, year, report_type, market, self._settings.score_threshold
        )

        # Extract sec_name from the best candidate's raw_json
        if best and best.get("raw_json"):
            try:
                raw = json.loads(best["raw_json"])
                sec_name = raw.get("secName", "")
                if sec_name:
                    best["sec_name"] = sec_name
            except (json.JSONDecodeError, TypeError):
                pass

        return best

    async def _search_with_expanded_range(
        self,
        code: str,
        market: Market,
        year: int,
        report_type: ReportType,
    ) -> list[dict[str, Any]]:
        """Fallback: search with a wider date range."""
        # This is a simplified expansion - search year-1 to year+2
        norm_code = normalize_stock_code(code, market)
        stock_dict = await self._ensure_stock_dict(market)
        org_id = stock_dict.get(norm_code, "")

        column = "hke" if market == Market.hk else "szse"
        keywords = get_keywords(market, report_type)

        all_candidates: list[dict[str, Any]] = []

        for keyword in keywords:
            domain = "www.cninfo.com.cn"
            await self._rate_limiter.acquire(domain)

            payload = {
                "pageNum": "1",
                "pageSize": "30",
                "column": column,
                "tabName": "fulltext",
                "stock": f"{norm_code},{org_id}" if org_id else norm_code,
                "searchkey": keyword,
                "category": "",
                "seDate": f"{year - 1}-01-01~{year + 2}-12-31",
                "isHLtitle": "true",
            }

            try:
                resp = await self._client.post(
                    f"{self._settings.cninfo_base_url}/new/hisAnnouncement/query",
                    data=payload,
                )
                resp.raise_for_status()
                await self._rate_limiter.record_success(domain)
            except Exception as e:
                await self._rate_limiter.record_failure(domain, str(e))
                continue

            result = resp.json()
            for ann in result.get("announcements", []):
                title = ann.get("announcementTitle", "")
                adjunct_url = ann.get("adjunctUrl", "")
                ann_date_ts = ann.get("announcementTime", 0)

                if ann_date_ts:
                    ann_date = date.fromtimestamp(ann_date_ts / 1000)
                else:
                    ann_date = date.today()

                pdf_url = (
                    f"{self._settings.cninfo_static_base_url}/{adjunct_url}"
                    if adjunct_url
                    else ""
                )

                all_candidates.append({
                    "announcement_title": title,
                    "announcement_date": ann_date.isoformat(),
                    "announcement_id": ann.get("announcementId", ""),
                    "org_id": ann.get("orgId", org_id),
                    "detail_url": ann.get("adjunctUrl", ""),
                    "pdf_url": pdf_url,
                    "adjunct_url": adjunct_url,
                    "raw_json": json.dumps(ann, ensure_ascii=False),
                })

            if all_candidates:
                break

        return all_candidates

    async def close(self) -> None:
        await self._client.aclose()
