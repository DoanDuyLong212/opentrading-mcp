"""P01 acceptance oracles — run_blocking admission accounting covers the five
lifecycle paths: completion, timeout, explicit cancellation, submission
failure, and recovery. The count must never undercount physically queued or
running work, and must always return to baseline (no leaks)."""

from __future__ import annotations

import asyncio
import time

import pytest

from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.tools import shared as shared_mod


def _pending() -> int:
    return shared_mod._pending


def _run(coro):
    return asyncio.run(coro)


def test_p01_completion_releases_admission():
    baseline = _pending()
    assert _run(shared_mod.run_blocking(lambda: 42, "p01", 5.0)) == 42
    assert _pending() == baseline


def test_p01_timeout_retains_count_until_thread_completes():
    """A caller timeout must never UNDERCOUNT: a running thread keeps its
    admission until it finishes; a queued-and-cancelled future releases
    immediately (it costs nothing). Either way the count recovers to baseline
    once the thread ends — never below, never stuck above."""
    baseline = _pending()

    async def main():
        with pytest.raises(ProviderUnavailable, match="timed out"):
            await shared_mod.run_blocking(lambda: time.sleep(0.6) or "late", "p01", 0.05)
        # never below baseline (no double-release), never stuck >baseline+1
        assert baseline <= _pending() <= baseline + 1, _pending()
        await asyncio.sleep(0.9)  # let the thread finish (if it started)
        assert _pending() == baseline, _pending()

    _run(main())


def test_p01_explicit_cancellation_releases_admission():
    baseline = _pending()

    async def main():
        task = asyncio.create_task(
            shared_mod.run_blocking(lambda: time.sleep(5.0) or "x", "p01", 30.0)
        )
        await asyncio.sleep(0.15)  # let it start (or queue)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # the admission must release whether the leg was running (thread
        # finished later) or queued (done-callback) — poll for recovery
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if _pending() <= baseline:
                break
            await asyncio.sleep(0.05)
        assert _pending() <= baseline, _pending()

    _run(main())


def test_p01_executor_submission_failure_releases_admission(monkeypatch):
    baseline = _pending()

    class _RejectingPool:
        def submit(self, fn, /, *args, **kwargs):
            raise RuntimeError("executor shutting down")

    async def main():
        original = shared_mod._EXECUTOR
        shared_mod._EXECUTOR = _RejectingPool()
        try:
            with pytest.raises(RuntimeError, match="shutting down"):
                await shared_mod.run_blocking(lambda: 1, "p01", 5.0)
        finally:
            shared_mod._EXECUTOR = original
        assert _pending() == baseline, _pending()

    _run(main())


def test_p01_recovery_after_timeout_storm():
    """A burst of timing-out legs must not poison later calls: after every
    thread finishes, fresh calls run normally (eventual recovery)."""
    baseline = _pending()

    async def main():
        for _ in range(3):
            with pytest.raises(ProviderUnavailable):
                await shared_mod.run_blocking(
                    lambda: time.sleep(0.3) or "x", "p01-storm", 0.05
                )
        deadline = time.monotonic() + 3.0
        # ASYNC110 intentional: we poll a thread-side counter, not an awaitable
        while time.monotonic() < deadline and _pending() > baseline:  # noqa: ASYNC110
            await asyncio.sleep(0.05)
        assert _pending() == baseline
        # a DIFFERENT call key is unaffected by the storm's negative cache
        assert await shared_mod.run_blocking(lambda: "ok", "p01-final", 5.0) == "ok"

    _run(main())
