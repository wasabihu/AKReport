"""Tests for stock history metadata enrichment."""
import sqlite3

import pytest

from app.config import Settings
from app.models import Market
from app.services.cninfo_client import CNInfoClient
from app.services.rate_limiter import RateLimiter
from app.storage.repositories import TaskRepository


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHTTPClient:
    async def get(self, url: str):
        if "hke_stock" in url:
            return FakeResponse({
                "stockList": [
                    {
                        "code": "00700",
                        "category": "港股",
                        "orgId": "gshk0000700",
                        "zwjc": "腾讯控股",
                    }
                ]
            })
        return FakeResponse({
            "stockList": [
                {
                    "code": "600519",
                    "category": "A股",
                    "orgId": "gssh0600519",
                    "zwjc": "贵州茅台",
                }
            ]
        })

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_get_stock_info_normalizes_auto_hk_code_and_name():
    settings = Settings(
        _env_file=None,
        default_request_interval_seconds=0,
        min_request_interval_seconds=0,
    )
    client = CNInfoClient(settings, RateLimiter(settings))
    client._client = FakeHTTPClient()

    result = await client.get_stock_info("700", Market.auto)

    assert result["code"] == "00700"
    assert result["name"] == "腾讯控股"
    assert result["market"] == "港股"


def test_update_stock_history_metadata_merges_normalized_code_collision():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE stock_history (
        code TEXT PRIMARY KEY,
        name TEXT,
        market TEXT NOT NULL,
        last_used_at TEXT NOT NULL,
        use_count INTEGER NOT NULL DEFAULT 1
    );
    INSERT INTO stock_history VALUES ('700', '错误名称', 'auto', '2026-04-30T10:00:00', 2);
    INSERT INTO stock_history VALUES ('00700', '腾讯控股', '港股', '2026-04-30T09:00:00', 3);
    """)
    repo = TaskRepository(conn)

    repo.update_stock_history_metadata("700", "00700", "腾讯控股", "港股")

    rows = conn.execute(
        "SELECT code, name, market, use_count FROM stock_history ORDER BY code"
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {"code": "00700", "name": "腾讯控股", "market": "港股", "use_count": 5}
    ]
