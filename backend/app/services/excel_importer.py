"""Excel/CSV import for batch stock codes."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.models import Market
from app.services.report_matcher import infer_market_from_code, normalize_stock_code


# Common column name patterns for stock code
_CODE_COLUMNS = [
    "股票代码", "代码", "code", "stock_code", "股票代码", "证券代码",
    "stock", "ticker", "symbol",
]

_NAME_COLUMNS = [
    "股票名称", "名称", "name", "stock_name", "证券名称", "公司名称",
]

_MARKET_COLUMNS = [
    "市场", "market", "板块", "board", "类型", "type",
]


class ExcelImporter:
    """Import stock codes from Excel or CSV files."""

    def import_file(self, file_path: Path) -> list[dict[str, str]]:
        """Import stock codes from a file.

        Returns list of dicts with 'code', 'name', 'market' keys.
        """
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            # Try multiple encodings
            for encoding in ("utf-8", "gbk", "gb2312", "utf-8-sig"):
                try:
                    df = pd.read_csv(file_path, encoding=encoding, dtype=str)
                    break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            else:
                raise ValueError(f"无法解析CSV文件: {file_path}")
        elif suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, dtype=str)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

        return self._parse_dataframe(df)

    def _parse_dataframe(self, df: pd.DataFrame) -> list[dict[str, str]]:
        """Parse a DataFrame and extract stock info."""
        code_col = self._find_column(df, _CODE_COLUMNS)
        if code_col is None:
            raise ValueError("未找到股票代码列，请确保包含'代码'或'code'列")

        name_col = self._find_column(df, _NAME_COLUMNS)
        market_col = self._find_column(df, _MARKET_COLUMNS)

        results: list[dict[str, str]] = []
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            if not code or code == "nan":
                continue

            # Normalize code
            raw_code = re.sub(r"\D", "", code)
            if not raw_code:
                continue

            # Infer market
            if market_col and str(row[market_col]).strip() not in ("nan", ""):
                market_str = str(row[market_col]).strip()
                market = Market.hk if "港" in market_str else Market.a_share
            else:
                market = infer_market_from_code(raw_code)

            norm_code = normalize_stock_code(raw_code, market)

            name = ""
            if name_col and str(row[name_col]).strip() not in ("nan", ""):
                name = str(row[name_col]).strip()

            results.append({
                "code": norm_code,
                "name": name,
                "market": market.value,
            })

        return results

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Find a column matching any of the candidate names (case-insensitive)."""
        cols_lower = {c.lower().strip(): c for c in df.columns}
        for candidate in candidates:
            if candidate.lower() in cols_lower:
                return cols_lower[candidate.lower()]
        return None
