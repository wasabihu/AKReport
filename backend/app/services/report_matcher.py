"""Report matching and scoring logic."""
from __future__ import annotations

import re

from app.config import Settings
from app.models import Market, ReportCandidate, ReportType


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

    # Year match
    if str(target_year) in title:
        score += 40

    # Report type keyword match
    keywords = get_keywords(market, target_report_type)
    if any(kw in title for kw in keywords):
        score += 40

    # 正本优先
    if "摘要" not in title:
        score += 20
    else:
        score -= 40

    if "更正后" in title:
        score += 10

    if "英文版" in title:
        score -= 20

    if "取消" in title or "作废" in title:
        score -= 100

    return score


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
) -> dict | None:
    """Score all candidates and return the best one above threshold.

    Each candidate dict should have at least an 'announcement_title' key.
    Returns the candidate dict with an added 'score' key, or None.
    """
    scored: list[tuple[int, dict]] = []

    for cand in candidates:
        title = cand.get("announcement_title", "")
        s = score_candidate(title, target_year, target_report_type, market)
        if is_valid_score(s, threshold):
            scored.append((s, cand))

    if not scored:
        return None

    # Sort by score descending, pick the best
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1].copy()
    best["score"] = scored[0][0]
    return best


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
