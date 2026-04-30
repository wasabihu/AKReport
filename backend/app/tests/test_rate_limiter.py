"""Tests for the rate limiter module."""
import asyncio
import time

import pytest

from app.config import Settings
from app.services.rate_limiter import RateLimiter


def _make_settings(**overrides) -> Settings:
    defaults = {
        "default_request_interval_seconds": 2.0,
        "min_request_interval_seconds": 1.0,
        "max_backoff_seconds": 60.0,
        "max_concurrency": 3,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_default_interval_is_2_seconds():
    settings = _make_settings()
    limiter = RateLimiter(settings)
    assert limiter.base_interval == 2.0


@pytest.mark.asyncio
async def test_reject_interval_below_minimum():
    settings = _make_settings(min_request_interval_seconds=1.0)
    limiter = RateLimiter(settings)
    assert not limiter.validate_interval(0.5)
    assert not limiter.validate_interval(0.9)
    assert limiter.validate_interval(1.0)
    assert limiter.validate_interval(2.0)


@pytest.mark.asyncio
async def test_consecutive_requests_to_same_domain_wait():
    settings = _make_settings(default_request_interval_seconds=0.1)
    limiter = RateLimiter(settings)

    start = time.monotonic()
    await limiter.acquire("cninfo.com.cn")
    await limiter.acquire("cninfo.com.cn")
    elapsed = time.monotonic() - start

    # Should take at least 0.1s between the two requests
    assert elapsed >= 0.09  # small tolerance


@pytest.mark.asyncio
async def test_429_doubles_interval():
    settings = _make_settings(default_request_interval_seconds=1.0)
    limiter = RateLimiter(settings)

    await limiter.acquire("cninfo.com.cn")
    await limiter.record_failure("cninfo.com.cn", "429 Too Many Requests")

    snap = limiter.snapshot("cninfo.com.cn")
    assert len(snap) == 1
    assert snap[0].current_interval == 2.0  # doubled from 1.0


@pytest.mark.asyncio
async def test_success_recovery():
    settings = _make_settings(default_request_interval_seconds=1.0, max_backoff_seconds=60.0)
    limiter = RateLimiter(settings)

    # Backoff to 4.0
    await limiter.record_failure("cninfo.com.cn", "429")
    await limiter.record_failure("cninfo.com.cn", "429")

    snap = limiter.snapshot("cninfo.com.cn")
    assert snap[0].current_interval == 4.0

    # Success should reduce interval
    await limiter.record_success("cninfo.com.cn")
    snap = limiter.snapshot("cninfo.com.cn")
    assert snap[0].current_interval == 3.0  # 4.0 * 0.75

    # More successes should recover toward base
    await limiter.record_success("cninfo.com.cn")
    snap = limiter.snapshot("cninfo.com.cn")
    assert snap[0].current_interval == 2.25  # 3.0 * 0.75

    # Eventually reaches base
    await limiter.record_success("cninfo.com.cn")
    await limiter.record_success("cninfo.com.cn")
    await limiter.record_success("cninfo.com.cn")
    snap = limiter.snapshot("cninfo.com.cn")
    assert snap[0].current_interval == 1.0  # back to base


@pytest.mark.asyncio
async def test_max_backoff():
    settings = _make_settings(default_request_interval_seconds=30.0, max_backoff_seconds=60.0)
    limiter = RateLimiter(settings)

    await limiter.record_failure("cninfo.com.cn", "429")
    snap = limiter.snapshot("cninfo.com.cn")
    assert snap[0].current_interval == 60.0  # capped at max

    await limiter.record_failure("cninfo.com.cn", "429")
    snap = limiter.snapshot("cninfo.com.cn")
    assert snap[0].current_interval == 60.0  # still capped


@pytest.mark.asyncio
async def test_different_domains_independent():
    settings = _make_settings(default_request_interval_seconds=0.05)
    limiter = RateLimiter(settings)

    start = time.monotonic()
    await limiter.acquire("a.cninfo.com.cn")
    await limiter.acquire("b.cninfo.com.cn")
    elapsed = time.monotonic() - start

    # Different domains should not block each other (within tolerance)
    assert elapsed < 0.08


@pytest.mark.asyncio
async def test_validate_concurrency():
    settings = _make_settings(max_concurrency=3)
    limiter = RateLimiter(settings)

    assert not limiter.validate_concurrency(0, 3)
    assert not limiter.validate_concurrency(4, 3)
    assert limiter.validate_concurrency(1, 3)
    assert limiter.validate_concurrency(3, 3)
