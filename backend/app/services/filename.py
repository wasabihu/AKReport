"""File naming utility for downloaded PDFs."""
from __future__ import annotations

import re

from app.models import Market, ReportType


# Characters forbidden in filenames on Windows/macOS/Linux
_ILLEGAL_CHARS = re.compile(r'[/:*?"<>|]')
_MULTI_SPACE = re.compile(r"\s+")

# Maximum filename length (leave room for path)
MAX_FILENAME_LENGTH = 180


def build_filename(
    market: Market,
    code: str,
    name: str | None,
    year: int,
    report_type: ReportType,
    announcement_date: str,
) -> str:
    """Build a standardized PDF filename.

    Format: {market}_{code}_{name}_{year}_{report_type}_{announcement_date}.pdf

    Example: A股_000001_平安银行_2024_年报_2025-03-15.pdf
    """
    market_label = market.value if market != Market.auto else "A股"
    name_part = name if name else "未知"
    parts = [market_label, code, name_part, str(year), report_type.value, announcement_date]
    filename = "_".join(parts) + ".pdf"
    return sanitize_filename(filename)


def sanitize_filename(filename: str) -> str:
    """Clean illegal characters and normalize whitespace in a filename."""
    # Replace illegal chars with underscore
    filename = _ILLEGAL_CHARS.sub("_", filename)
    # Collapse multiple spaces into one
    filename = _MULTI_SPACE.sub(" ", filename)
    # Trim to max length, preserving .pdf extension
    if len(filename) > MAX_FILENAME_LENGTH:
        base = filename[:-4]  # remove .pdf
        base = base[: MAX_FILENAME_LENGTH - 4]
        filename = base + ".pdf"
    return filename
