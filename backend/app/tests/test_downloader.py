"""Tests for the downloader module."""
import pytest

from app.models import Market, ReportType
from app.services.filename import build_filename, sanitize_filename


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
        result = sanitize_filename('test:file*name?"with|chars.pdf')
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
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
