"""Executor admission follows physical work, including caller cancellation."""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.tools import shared as shared_mod


@pytest.fixture
def executor(monkeypatch):
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(shared_mod, "_EXECUTOR", pool)
    monkeypatch.setenv("MCP_NEG_TTL", "0")
    yield pool
    pool.shutdown(wait=True, cancel_futures=True)


async def _started(event):
    assert await asyncio.to_thread(event.wait, 2), "worker did not start"


# Longer than _started's 2s wait, so the timeout can only fire on a running thread.
_RUNNING_TIMEOUT = 2.5


@pytest.mark.asyncio
async def test_completion_releases(executor):
    baseline = shared_mod._pending
    assert await shared_mod.run_blocking(lambda: 42, "p01", 5) == 42
    assert shared_mod._pending == baseline


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_running_thread_retains_admission(executor, cancel):
    started, release = threading.Event(), threading.Event()
    baseline = shared_mod._pending

    def work():
        started.set()
        assert release.wait(10)

    # #95: with a 0.5s timeout a loaded runner could time out before the worker
    # thread even started; run_blocking then cancelled the queued job, `work`
    # never ran and the test failed with "worker did not start". The timeout
    # under test is run_blocking's own, so keep it, but long enough that the
    # worker always starts first (the thread stays blocked on `release`).
    timeout = _RUNNING_TIMEOUT if not cancel else 10
    task = asyncio.create_task(shared_mod.run_blocking(work, "p01", timeout))
    try:
        await _started(started)
        if not cancel:
            assert not task.done(), "timed out before the worker was seen running"
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else ProviderUnavailable):
            await task
        assert shared_mod._pending == baseline + 1
    finally:
        release.set()
        await asyncio.wrap_future(executor.submit(lambda: None))
    assert shared_mod._pending == baseline
    assert await shared_mod.run_blocking(lambda: "ok", "recovered", 5) == "ok"


@pytest.mark.asyncio
async def test_queued_cancellation_never_runs(executor):
    started, release, queued_ran = threading.Event(), threading.Event(), threading.Event()
    baseline = shared_mod._pending

    def work():
        started.set()
        assert release.wait(10)

    running = asyncio.create_task(shared_mod.run_blocking(work, "running", 10))
    try:
        await _started(started)
        queued = asyncio.create_task(shared_mod.run_blocking(queued_ran.set, "queued", 0.1))
        with pytest.raises(ProviderUnavailable):
            await queued
        assert shared_mod._pending == baseline + 1
    finally:
        release.set()
        await running
    assert not queued_ran.is_set()
    assert shared_mod._pending == baseline


@pytest.mark.asyncio
async def test_submission_rejection_releases(monkeypatch):
    baseline = shared_mod._pending

    class RejectingPool:
        def submit(self, fn):
            raise RuntimeError("executor shutting down")

    monkeypatch.setattr(shared_mod, "_EXECUTOR", RejectingPool())
    with pytest.raises(RuntimeError, match="shutting down"):
        await shared_mod.run_blocking(lambda: None, "rejected", 5)
    assert shared_mod._pending == baseline


@pytest.mark.asyncio
async def test_running_timeout_still_sheds(executor, monkeypatch):
    baseline = shared_mod._pending
    monkeypatch.setattr(shared_mod, "shed_limit", lambda: baseline + 1)
    started, release = threading.Event(), threading.Event()

    def work():
        started.set()
        assert release.wait(10)

    task = asyncio.create_task(shared_mod.run_blocking(work, "storm", 0.5))
    try:
        await _started(started)
        with pytest.raises(ProviderUnavailable, match="timed out"):
            await task
        with pytest.raises(ProviderUnavailable, match="shed"):
            await shared_mod.run_blocking(lambda: None, "new", 5)
    finally:
        release.set()
        await asyncio.wrap_future(executor.submit(lambda: None))
    assert shared_mod._pending == baseline
