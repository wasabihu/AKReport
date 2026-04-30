"""Report matching and scoring logic."""
from __future__ import annotations

import json
import re

from app.models import Market, ReportType


MIN_ANNUAL_REPORT_FILE_SIZE_BYTES = 1024 * 1024

# A-share keyword strategies
A_SHARE_KEYWORDS: dict[ReportType, list[str]] = {
    ReportType.annual: ["年度报告", "年报"],
    ReportType.q1: ["第一季度报告", "一季报"],
    ReportType.half: ["半年度报告", "半年报"],
    ReportType.q3: ["第三季度报告", "三季报"],
}

# HK keyword strategies
HK_KEYWORDS: dict[ReportType, list[str]] = {
    ReportType.annual: ["年报", "年度报告"],
    ReportType.half: ["中期报告", "半年报", "中报"],
    ReportType.q1: ["第一季度", "一季报", "季度报告"],
    ReportType.q3: ["第三季度", "三季报", "季度报告"],
}

HK_COMPANION_KEYWORDS = (
    "通知信函",
    "通函",
    "大会通告",
    "代表委任表格",
    "发布通知",
    "可持续发展报告",
    "環境、社會及管治報告",
    "环境、社会及管治报告",
    "esg report",
)

HTML_TAG_RE = re.compile(r"<[^>]+>")
NON_WORD_RE = re.compile(r"[\s()（）:：,，;；、.\-_/]+")


def get_keywords(market: Market, report_type: ReportType) -> list[str]:
    """Return ordered keyword list for searching."""
    if market == Market.hk:
        return HK_KEYWORDS.get(report_type, [])
    return A_SHARE_KEYWORDS.get(report_type, [])


def score_candidate(
    title: str,
    target_year: int,
    target_report_type: ReportType,
    market: Market,
) -> int:
    """Score a candidate announcement title.

    Scoring rules from the spec:
    - Title contains target year: +40
    - Title contains target report type keyword: +40
    - Title does NOT contain "摘要": +20
    - Title contains "更正后": +10
    - Title contains "英文版": -20
    - Title contains "摘要": -40
    - Title contains "取消" or "作废": -100
    """
    score = 0
    clean_title = _clean_title(title)

    # Year match
    if str(target_year) in clean_title:
        score += 40

    # Report type keyword match
    keywords = get_keywords(market, target_report_type)
    if any(kw in clean_title for kw in keywords):
        score += 40

    # 正本优先
    if "摘要" not in clean_title:
        score += 20
    else:
        score -= 40

    if "更正后" in clean_title:
        score += 10

    if "英文版" in clean_title:
        score -= 20

    if "取消" in clean_title or "作废" in clean_title:
        score -= 100

    # Prefer the standalone report body over HK companion notifications.
    if market == Market.hk:
        lowered = clean_title.lower()
        if any(keyword in clean_title for keyword in HK_COMPANION_KEYWORDS) or any(
            keyword in lowered for keyword in HK_COMPANION_KEYWORDS
        ):
            score -= 70

        if _is_standalone_report_title(clean_title, target_year, target_report_type, market):
            score += 30

    return score


def _clean_title(title: str) -> str:
    return HTML_TAG_RE.sub("", title).strip()


def _normalize_title_for_match(title: str) -> str:
    title = _clean_title(title)
    title = NON_WORD_RE.sub("", title)
    return title.lower()


def _is_standalone_report_title(
    title: str,
    target_year: int,
    target_report_type: ReportType,
    market: Market,
) -> bool:
    normalized = _normalize_title_for_match(title)

    if market == Market.hk and target_report_type == ReportType.annual:
        candidates = {
            f"{target_year}年报",
            f"{target_year}年報",
            f"{target_year}年度报告",
            f"{target_year}annualreport",
        }
        return normalized in candidates

    if market == Market.a_share:
        patterns = {
            ReportType.annual: {f"{target_year}年年度报告"},
            ReportType.q1: {f"{target_year}年第一季度报告"},
            ReportType.half: {f"{target_year}年半年度报告"},
            ReportType.q3: {f"{target_year}年第三季度报告"},
        }
        return normalized in patterns.get(target_report_type, set())

    return False


def extract_year_from_title(title: str) -> int | None:
    """Try to extract a 4-digit year from the title."""
    match = re.search(r"(20\d{2})", title)
    if match:
        return int(match.group(1))
    return None


def is_valid_score(score: int, threshold: int = 60) -> bool:
    """Check if score meets the minimum threshold."""
    return score >= threshold


def select_best_candidate(
    candidates: list[dict],
    target_year: int,
    target_report_type: ReportType,
    market: Market,
    threshold: int = 60,
    min_annual_report_file_size_bytes: int = MIN_ANNUAL_REPORT_FILE_SIZE_BYTES,
) -> dict | None:
    """Score all candidates and return the best one above threshold.

    Each candidate dict should have at least an 'announcement_title' key.
    Returns the candidate dict with an added 'score' key, or None.
    """
    scored: list[tuple[int, dict]] = []

    for cand in candidates:
        title = cand.get("announcement_title", "")
        s = score_candidate(title, target_year, target_report_type, market)
        if is_valid_score(s, threshold) and meets_file_size_requirement(
            cand, target_report_type, min_annual_report_file_size_bytes
        ):
            scored.append((s, cand))

    if not scored:
        return None

    # Sort by score descending, pick the best
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1].copy()
    best["score"] = scored[0][0]
    return best


def meets_file_size_requirement(
    candidate: dict,
    target_report_type: ReportType,
    min_annual_report_file_size_bytes: int = MIN_ANNUAL_REPORT_FILE_SIZE_BYTES,
) -> bool:
    """Reject obviously-small annual report candidates when file size is known."""
    if target_report_type != ReportType.annual:
        return True

    file_size = _candidate_file_size(candidate)
    if file_size is None:
        return True

    return file_size >= min_annual_report_file_size_bytes


def _candidate_file_size(candidate: dict) -> int | None:
    value = candidate.get("file_size")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    raw_json = candidate.get("raw_json")
    if not raw_json:
        return None

    try:
        raw = json.loads(raw_json)
        adjunct_size = raw.get("adjunctSize")
        return int(adjunct_size) * 1024
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def normalize_stock_code(code: str, market: Market) -> str:
    """Normalize stock code format.

    A-shares: 6 digits.
    HK stocks: 5 digits, left-padded with 0.
    """
    digits = re.sub(r"\D", "", code)

    if market == Market.hk:
        return digits.zfill(5)
    return digits.zfill(6)


def infer_market_from_code(code: str) -> Market:
    """Infer market from stock code format.

    - 5-digit codes starting with 0: HK (e.g., 00700)
    - 6-digit codes: A-share
    """
    digits = re.sub(r"\D", "", code)
    # HK codes are 1-5 digits, A-share codes are 6 digits
    if len(digits) <= 5:
        return Market.hk
    return Market.a_share


def derive_date_range(year: int, report_type: ReportType) -> tuple[str, str]:
    """Derive the disclosure date search range for a given year and report type.

    Returns (start_date, end_date) in YYYY-MM-DD format.
    """
    ranges: dict[ReportType, tuple[str, str]] = {
        ReportType.annual: (f"{year + 1}-01-01", f"{year + 1}-12-31"),
        ReportType.q1: (f"{year}-03-01", f"{year}-06-30"),
        ReportType.half: (f"{year}-07-01", f"{year}-10-31"),
        ReportType.q3: (f"{year}-09-01", f"{year}-12-31"),
    }
    return ranges[report_type]
