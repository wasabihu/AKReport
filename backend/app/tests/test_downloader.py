"""Tests for the downloader module."""
import httpx
import pytest

from app.config import Settings
from app.models import ItemStatus, Market, ReportType
from app.services.downloader import Downloader
from app.services.filename import build_filename, sanitize_filename
from app.services.rate_limiter import RateLimiter


class FakePDFClient:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def get(self, url: str) -> httpx.Response:
        return httpx.Response(
            200,
            content=self._content,
            request=httpx.Request("GET", url),
        )

    async def aclose(self) -> None:
        return None


class TestFilename:
    def test_build_a_share_filename(self):
        name = build_filename(
            Market.a_share, "000001", "平安银行", 2024, ReportType.annual, "2025-03-15"
        )
        assert name == "A股_000001_平安银行_2024_年报_2025-03-15.pdf"

    def test_build_hk_filename(self):
        name = build_filename(
            Market.hk, "00700", "腾讯控股", 2024, ReportType.annual, "2025-04-10"
        )
        assert name == "港股_00700_腾讯控股_2024_年报_2025-04-10.pdf"

    def test_build_filename_no_name(self):
        name = build_filename(
            Market.a_share, "000001", None, 2024, ReportType.half, "2024-08-20"
        )
        assert "未知" in name

    def test_sanitize_illegal_chars(self):
        result = sanitize_filename('test:file*name?\\bad/name"with|chars.pdf')
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert "\\" not in result
        assert "/" not in result
        assert '"' not in result
        assert "|" not in result
        assert result.endswith(".pdf")

    def test_sanitize_preserves_valid_filename(self):
        result = sanitize_filename("A股_000001_平安银行_2024_年报.pdf")
        assert result == "A股_000001_平安银行_2024_年报.pdf"

    def test_sanitize_truncates_long_filename(self):
        long_name = "A" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 180
        assert result.endswith(".pdf")


@pytest.mark.asyncio
async def test_annual_report_under_one_mb_is_rejected(tmp_path):
    settings = Settings(
        _env_file=None,
        default_request_interval_seconds=0,
        min_request_interval_seconds=0,
        min_annual_report_file_size_bytes=1024 * 1024,
    )
    downloader = Downloader(settings, RateLimiter(settings))
    downloader._client = FakePDFClient(b"%PDF" + b"x" * 100)

    result = await downloader.download_report(
        task_id="task-1",
        code="00001",
        name="长和",
        market=Market.hk,
        year=2022,
        report_type=ReportType.annual,
        pdf_url="http://static.cninfo.com.cn/test.pdf",
        announcement_date="2023-04-17",
        save_dir=tmp_path,
    )

    assert result.status == ItemStatus.failed
    assert result.file_size == 104
    assert "小于1MB" in result.message
    assert not list(tmp_path.glob("*.pdf"))


@pytest.mark.asyncio
async def test_small_non_annual_pdf_can_be_saved(tmp_path):
    settings = Settings(
        _env_file=None,
        default_request_interval_seconds=0,
        min_request_interval_seconds=0,
        min_annual_report_file_size_bytes=1024 * 1024,
    )
    downloader = Downloader(settings, RateLimiter(settings))
    downloader._client = FakePDFClient(b"%PDF" + b"x" * 100)

    result = await downloader.download_report(
        task_id="task-1",
        code="000001",
        name="平安银行",
        market=Market.a_share,
        year=2024,
        report_type=ReportType.q1,
        pdf_url="http://static.cninfo.com.cn/test.pdf",
        announcement_date="2024-04-20",
        save_dir=tmp_path,
    )

    assert result.status == ItemStatus.success
    assert result.file_size == 104
    assert list(tmp_path.glob("*.pdf"))
