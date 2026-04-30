"""Tests for the report matcher module."""
import pytest

from app.models import Market, ReportType
from app.services.report_matcher import (
    derive_date_range,
    infer_market_from_code,
    normalize_stock_code,
    score_candidate,
    select_best_candidate,
)


# ── normalize_stock_code ──


def test_normalize_a_share_6_digits():
    assert normalize_stock_code("000001", Market.a_share) == "000001"


def test_normalize_a_share_with_spaces():
    assert normalize_stock_code(" 000001 ", Market.a_share) == "000001"


def test_normalize_hk_stock_pad_to_5():
    assert normalize_stock_code("700", Market.hk) == "00700"


def test_normalize_hk_stock_already_5():
    assert normalize_stock_code("00700", Market.hk) == "00700"


def test_normalize_hk_stock_1_digit():
    assert normalize_stock_code("1", Market.hk) == "00001"


# ── infer_market_from_code ──


def test_infer_a_share_from_6_digits():
    assert infer_market_from_code("000001") == Market.a_share


def test_infer_hk_from_5_digits():
    assert infer_market_from_code("00700") == Market.hk


def test_infer_hk_from_short():
    assert infer_market_from_code("700") == Market.hk


# ── score_candidate ──


def test_perfect_annual_report_score():
    """Title with year + report type + no 摘要 = 100"""
    score = score_candidate(
        "2024年年度报告", 2024, ReportType.annual, Market.a_share
    )
    assert score == 100  # 40(year) + 40(type) + 20(no摘要)


def test_summary_gets_penalized():
    """摘要 version should score lower than full report."""
    full = score_candidate(
        "2024年年度报告", 2024, ReportType.annual, Market.a_share
    )
    summary = score_candidate(
        "2024年年度报告摘要", 2024, ReportType.annual, Market.a_share
    )
    assert full > summary


def test_cancelled_report_below_threshold():
    """取消 or 作废 should drop score below 60."""
    score = score_candidate(
        "2024年年度报告取消", 2024, ReportType.annual, Market.a_share
    )
    assert score < 60


def test_void_report_below_threshold():
    score = score_candidate(
        "关于作废2024年年度报告的公告", 2024, ReportType.annual, Market.a_share
    )
    assert score < 60


def test_corrected_version_gets_bonus():
    corrected = score_candidate(
        "2024年年度报告（更正后）", 2024, ReportType.annual, Market.a_share
    )
    original = score_candidate(
        "2024年年度报告", 2024, ReportType.annual, Market.a_share
    )
    assert corrected > original


def test_english_version_penalized():
    english = score_candidate(
        "2024 Annual Report", 2024, ReportType.annual, Market.a_share
    )
    chinese = score_candidate(
        "2024年年度报告", 2024, ReportType.annual, Market.a_share
    )
    # English version won't match Chinese keywords so it gets 0 for type match
    assert chinese > english


def test_wrong_year_no_match():
    score = score_candidate(
        "2023年年度报告", 2024, ReportType.annual, Market.a_share
    )
    assert score < 100  # Missing year bonus


def test_hk_annual_keyword():
    """HK annual report should match 年报 keyword."""
    score = score_candidate(
        "2024年年报", 2024, ReportType.annual, Market.hk
    )
    assert score >= 60


def test_hk_half_year_keyword():
    """HK half-year should match 中期报告."""
    score = score_candidate(
        "2024年中期报告", 2024, ReportType.half, Market.hk
    )
    assert score >= 60


def test_hk_notification_letter_scores_lower_than_actual_annual_report():
    actual = score_candidate(
        "2022年年报", 2022, ReportType.annual, Market.hk
    )
    notification = score_candidate(
        "致登记股东之通知信函: (1)股东周年大会; 及(2) 2022年年报、通函、大会通告及有关大会之代表委任表格以及2022年可持续发展报告之发布通知",
        2022,
        ReportType.annual,
        Market.hk,
    )
    assert actual > notification


# ── select_best_candidate ──


def test_select_best_picks_highest_score():
    candidates = [
        {"announcement_title": "2024年年度报告摘要"},
        {"announcement_title": "2024年年度报告"},
        {"announcement_title": "2024年年度报告（英文版）"},
    ]
    best = select_best_candidate(candidates, 2024, ReportType.annual, Market.a_share)
    assert best is not None
    assert best["announcement_title"] == "2024年年度报告"


def test_select_best_returns_none_below_threshold():
    candidates = [
        {"announcement_title": "关于取消2024年年度报告的公告"},
    ]
    best = select_best_candidate(candidates, 2024, ReportType.annual, Market.a_share)
    assert best is None


def test_select_best_prefers_true_hk_annual_report_over_notification_letter():
    candidates = [
        {
            "announcement_title": "致登记股东之通知信函: (1)股东周年大会; 及(2) 2022年年报、通函、大会通告及有关大会之代表委任表格以及2022年可持续发展报告之发布通知"
        },
        {"announcement_title": "2022年年报"},
        {
            "announcement_title": "致新登记股东之信函:(1)股东周年大会；(2) 2022年年报及2022年可持续发展报告；及(3)选择公司通讯之语言版本及收取方式"
        },
    ]
    best = select_best_candidate(candidates, 2022, ReportType.annual, Market.hk)
    assert best is not None
    assert best["announcement_title"] == "2022年年报"


def test_select_best_filters_small_annual_report_candidates():
    candidates = [
        {"announcement_title": "2022年年报", "file_size": 377 * 1024},
        {"announcement_title": "2022年年报", "file_size": 15_585 * 1024},
    ]
    best = select_best_candidate(candidates, 2022, ReportType.annual, Market.hk)
    assert best is not None
    assert best["file_size"] == 15_585 * 1024


def test_select_best_reads_cninfo_adjunct_size_from_raw_json():
    candidates = [
        {"announcement_title": "2022年年报", "raw_json": '{"adjunctSize": 377}'},
        {"announcement_title": "2022年年报", "raw_json": '{"adjunctSize": 15585}'},
    ]
    best = select_best_candidate(candidates, 2022, ReportType.annual, Market.hk)
    assert best is not None
    assert best["raw_json"] == '{"adjunctSize": 15585}'


def test_small_file_filter_does_not_apply_to_quarterly_reports():
    candidates = [
        {"announcement_title": "2024年第一季度报告", "file_size": 200 * 1024},
    ]
    best = select_best_candidate(candidates, 2024, ReportType.q1, Market.a_share)
    assert best is not None


# ── derive_date_range ──


def test_annual_report_date_range():
    start, end = derive_date_range(2024, ReportType.annual)
    assert start == "2025-01-01"
    assert end == "2025-12-31"


def test_q1_report_date_range():
    start, end = derive_date_range(2024, ReportType.q1)
    assert start == "2024-03-01"
    assert end == "2024-06-30"


def test_half_year_report_date_range():
    start, end = derive_date_range(2024, ReportType.half)
    assert start == "2024-07-01"
    assert end == "2024-10-31"


def test_q3_report_date_range():
    start, end = derive_date_range(2024, ReportType.q3)
    assert start == "2024-09-01"
    assert end == "2024-12-31"
