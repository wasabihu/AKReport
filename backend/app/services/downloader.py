"""PDF downloader with temp-file write, validation, and atomic rename."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.config import Settings
from app.models import DownloadResult, ItemStatus, Market, ReportType
from app.services.filename import build_filename
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# PDF magic bytes
PDF_HEADER = b"%PDF"


class Downloader:
    """Download PDFs with validation and atomic file writes."""

    def __init__(self, settings: Settings, rate_limiter: RateLimiter) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        )

    async def download_report(
        self,
        task_id: str,
        code: str,
        name: str | None,
        market: Market,
        year: int,
        report_type: ReportType,
        pdf_url: str,
        announcement_date: str,
        save_dir: Path,
        overwrite: bool = False,
    ) -> DownloadResult:
        """Download a single report PDF.

        Steps:
        1. Build target filename
        2. Check if file exists (skip unless overwrite)
        3. Download to .partial temp file
        4. Validate HTTP 200 + size > 0 + PDF header
        5. Atomic rename from .partial to final name
        """
        filename = build_filename(market, code, name, year, report_type, announcement_date)
        target_path = save_dir / filename

        # Skip existing
        if target_path.exists() and not overwrite:
            return DownloadResult(
                task_id=task_id,
                code=code,
                market=market,
                year=year,
                report_type=report_type,
                status=ItemStatus.skipped,
                file_path=target_path,
                message=f"文件已存在: {filename}",
            )

        # Ensure save directory exists
        save_dir.mkdir(parents=True, exist_ok=True)

        partial_path = save_dir / f"{filename}.partial"

        try:
            # Rate limit
            domain = self._extract_domain(pdf_url)
            await self._rate_limiter.acquire(domain)

            # Download
            resp = await self._client.get(pdf_url)
            resp.raise_for_status()
            await self._rate_limiter.record_success(domain)

            content = resp.content

            # Validate size
            if len(content) == 0:
                await self._rate_limiter.record_failure(domain, "Empty response")
                return DownloadResult(
                    task_id=task_id,
                    code=code,
                    market=market,
                    year=year,
                    report_type=report_type,
                    status=ItemStatus.failed,
                    message="下载文件为空",
                )

            # Validate PDF header
            if not content[:4] == PDF_HEADER:
                return DownloadResult(
                    task_id=task_id,
                    code=code,
                    market=market,
                    year=year,
                    report_type=report_type,
                    status=ItemStatus.failed,
                    message="文件不是有效PDF (缺少%PDF头)",
                )

            # Write to .partial then atomic rename
            partial_path.write_bytes(content)
            partial_path.rename(target_path)

            logger.info("Downloaded %s -> %s", pdf_url, target_path)
            return DownloadResult(
                task_id=task_id,
                code=code,
                market=market,
                year=year,
                report_type=report_type,
                status=ItemStatus.success,
                file_path=target_path,
                message=f"下载成功: {filename}",
            )

        except httpx.HTTPStatusError as e:
            domain = self._extract_domain(pdf_url)
            await self._rate_limiter.record_failure(domain, str(e))
            # Clean up partial file
            if partial_path.exists():
                partial_path.unlink()
            return DownloadResult(
                task_id=task_id,
                code=code,
                market=market,
                year=year,
                report_type=report_type,
                status=ItemStatus.failed,
                message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            domain = self._extract_domain(pdf_url)
            await self._rate_limiter.record_failure(domain, str(e))
            if partial_path.exists():
                partial_path.unlink()
            return DownloadResult(
                task_id=task_id,
                code=code,
                market=market,
                year=year,
                report_type=report_type,
                status=ItemStatus.failed,
                message=f"下载失败: {e}",
            )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL for rate limiting."""
        try:
            # Simple extraction: between :// and first /
            start = url.find("://") + 3
            end = url.find("/", start)
            if end == -1:
                end = len(url)
            return url[start:end]
        except Exception:
            return "unknown"

    async def close(self) -> None:
        await self._client.aclose()
