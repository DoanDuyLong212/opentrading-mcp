"""Per-upstream circuit breaker (sync, thread-safe).

Trips only on ProviderUnavailable (flaky network/upstream). Auth and data
errors are config/upstream-shape problems — retrying won't fix them, so
they never count toward the threshold.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from opentrading_mcp.providers.errors import ProviderAuthMissing, ProviderUnavailable

T = TypeVar("T")

_lock = threading.Lock()
_breakers: dict[str, CircuitBreaker] = {}


class CircuitOpenError(ProviderUnavailable):
    """Raised when the breaker is open; no upstream call was attempted.

    Subclasses ProviderUnavailable so existing tool handlers (which catch
    the provider taxonomy) degrade to unavailable envelopes instead of
    crashing when the breaker trips mid-run.
    """


class CircuitBreaker:
    def __init__(
        self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(0.0, recovery_timeout)
        self._failures = 0
        self._opened_at: float | None = None
        self._state_lock = threading.Lock()

    def _is_open(self, now: float) -> bool:
        return self._opened_at is not None and now - self._opened_at < self.recovery_timeout

    def call(self, fn: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._state_lock:
            if self._is_open(now):
                raise CircuitOpenError(f"circuit {self.name!r} is open")
        try:
            result = fn()
        except ProviderAuthMissing:
            raise
        except ProviderUnavailable:
            with self._state_lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = time.monotonic()
            raise
        with self._state_lock:
            self._failures = 0
            self._opened_at = None
        return result


def get_circuit(name: str) -> CircuitBreaker:
    with _lock:
        breaker = _breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(name)
            _breakers[name] = breaker
        return breaker


def reset(name: str) -> None:
    with _lock:
        _breakers.pop(name, None)


def guarded(upstream: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator routing a provider call through the named breaker."""

    def decorate(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            from opentrading_mcp import obs
            from opentrading_mcp.providers.errors import ProviderUnavailable

            try:
                return get_circuit(upstream).call(lambda: fn(*args, **kwargs))
            except ProviderUnavailable:
                obs.record_upstream_failure(upstream)
                raise

        return wrapper

    return decorate
