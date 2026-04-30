"""Rate limiter with per-domain tracking, auto-backoff, and recovery."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from app.config import Settings
from app.models import RateLimitSnapshot


class RateLimiter:
    """Global rate limiter for source site requests.

    All requests to cninfo.com.cn domains must go through this limiter.
    Supports auto-backoff on failures and gradual recovery on successes.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_interval = settings.default_request_interval_seconds
        self._min_interval = settings.min_request_interval_seconds
        self._max_backoff = settings.max_backoff_seconds
        self._domain_state: dict[str, _DomainState] = {}

    def _get_state(self, domain: str) -> _DomainState:
        if domain not in self._domain_state:
            self._domain_state[domain] = _DomainState(
                current_interval=self._base_interval,
                failure_count=0,
                last_request_at=None,
            )
        return self._domain_state[domain]

    async def acquire(self, domain: str) -> None:
        """Wait until a request to *domain* is allowed."""
        state = self._get_state(domain)
        now = time.monotonic()
        if state.last_request_at is not None:
            elapsed = now - state.last_request_at
            wait_time = state.current_interval - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        state.last_request_at = time.monotonic()

    async def record_success(self, domain: str) -> None:
        """Record a successful request; gradually reduce interval back to base."""
        state = self._get_state(domain)
        state.failure_count = 0
        # Step down: reduce by 25% toward base, but never below base
        if state.current_interval > self._base_interval:
            state.current_interval = max(
                self._base_interval,
                state.current_interval * 0.75,
            )

    async def record_failure(self, domain: str, reason: str = "") -> None:
        """Record a failed request; double the interval (exponential backoff)."""
        state = self._get_state(domain)
        state.failure_count += 1
        state.current_interval = min(
            state.current_interval * 2,
            self._max_backoff,
        )

    def snapshot(self, domain: str | None = None) -> list[RateLimitSnapshot]:
        """Return current rate limit state for one or all domains."""
        if domain:
            state = self._get_state(domain)
            return [RateLimitSnapshot(
                domain=domain,
                current_interval=state.current_interval,
                failure_count=state.failure_count,
                last_request_at=(
                    datetime.fromtimestamp(state.last_request_at)
                    if state.last_request_at
                    else None
                ),
            )]
        return [
            RateLimitSnapshot(
                domain=d,
                current_interval=s.current_interval,
                failure_count=s.failure_count,
                last_request_at=(
                    datetime.fromtimestamp(s.last_request_at)
                    if s.last_request_at
                    else None
                ),
            )
            for d, s in self._domain_state.items()
        ]

    def validate_interval(self, interval: float) -> bool:
        """Check if a user-provided interval meets the minimum."""
        return interval >= self._min_interval

    def validate_concurrency(self, concurrency: int, max_concurrency: int) -> bool:
        """Check if a user-provided concurrency is within limits."""
        return 1 <= concurrency <= max_concurrency

    @property
    def base_interval(self) -> float:
        return self._base_interval

    @base_interval.setter
    def base_interval(self, value: float) -> None:
        self._base_interval = value


class _DomainState:
    __slots__ = ("current_interval", "failure_count", "last_request_at")

    def __init__(
        self,
        current_interval: float,
        failure_count: int = 0,
        last_request_at: float | None = None,
    ) -> None:
        self.current_interval = current_interval
        self.failure_count = failure_count
        self.last_request_at = last_request_at
