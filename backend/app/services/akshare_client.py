"""AKShare client with compatibility isolation."""
from __future__ import annotations

from typing import Any

import akshare as ak
import pandas as pd

from app.config import Settings
from app.models import Market
from app.services.rate_limiter import RateLimiter


class AKShareClient:
    """Thin wrapper around AKShare with rate limiting.

    Purpose: isolate AKShare API compatibility so the rest of the codebase
    doesn't depend on AKShare internals directly.
    """

    def __init__(self, settings: Settings, rate_limiter: RateLimiter) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter

    async def get_stock_info(self, code: str, market: Market) -> dict[str, Any] | None:
        """Look up stock name and basic info from AKShare."""
        try:
            if market == Market.hk:
                df = ak.stock_hk_spot_em()
                # HK: 代码 column, 名称 column
                match = df[df["代码"] == code]
                if match.empty:
                    return None
                row = match.iloc[0]
                return {
                    "code": code,
                    "name": str(row.get("名称", "")),
                    "market": "港股",
                }
            else:
                df = ak.stock_zh_a_spot_em()
                match = df[df["代码"] == code]
                if match.empty:
                    return None
                row = match.iloc[0]
                return {
                    "code": code,
                    "name": str(row.get("名称", "")),
                    "market": "A股",
                }
        except Exception:
            return None

    async def get_hk_stock_list(self) -> list[dict[str, str]]:
        """Return list of HK stocks with code and name."""
        try:
            df = ak.stock_hk_spot_em()
            return [
                {"code": str(row["代码"]), "name": str(row["名称"])}
                for _, row in df.iterrows()
            ]
        except Exception:
            return []

    async def get_a_share_list(self) -> list[dict[str, str]]:
        """Return list of A-share stocks with code and name."""
        try:
            df = ak.stock_zh_a_spot_em()
            return [
                {"code": str(row["代码"]), "name": str(row["名称"])}
                for _, row in df.iterrows()
            ]
        except Exception:
            return []
