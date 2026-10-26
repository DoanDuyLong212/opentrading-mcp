"""P05 oracle — the vnstock batch pool is a process-wide singleton bounded at
3 workers: hung legs occupy a worker but can never multiply live threads."""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderUnavailable


def test_expired_batches_do_not_accumulate_or_run_after_recovery(monkeypatch):
    pool = ThreadPoolExecutor(max_workers=3)
    slots = threading.BoundedSemaphore(3)
    release = threading.Event()
    started = threading.Semaphore(0)
    calls = []

    class Market:
        def equity(self, chunk):
            self.chunk = chunk
            return self

        def quote(self):
            calls.append(self.chunk)
            started.release()
            assert release.wait(5)
            return SimpleNamespace(to_dict=lambda **kwargs: [{"symbol": self.chunk[0]}])

    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace(Market=Market))
    monkeypatch.setattr(vn_p, "_VN_BATCH_POOL", pool)
    monkeypatch.setattr(vn_p, "_VN_BATCH_SLOTS", slots)
    monkeypatch.setattr(vn_p, "_VN_BATCH_WAIT_SECONDS", 0.05)
    # Bypass circuit state only; exercise the actual provider batch lifecycle.
    batch = vn_p.equity_quote_batch.__wrapped__
    try:
        t0 = time.monotonic()
        with pytest.raises(ProviderUnavailable):
            batch([f"S{i}" for i in range(30)])
        assert time.monotonic() - t0 < 0.5  # one budget, no extra 0.5s per chunk
        for _ in range(3):
            assert started.acquire(timeout=1)
        for _ in range(5):
            with pytest.raises(ProviderUnavailable):
                batch(["EXPIRED"])
        assert len(calls) == 3
        assert pool._work_queue.qsize() == 0
    finally:
        release.set()
        pool.shutdown(wait=True)
    assert len(calls) == 3  # no old request replayed after recovery
    assert all(slots.acquire(blocking=False) for _ in range(3))


def test_batch_submission_rejection_releases_slot(monkeypatch):
    class RejectingPool:
        def submit(self, *args):
            raise RuntimeError("shutting down")

    slots = threading.BoundedSemaphore(3)
    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace(Market=object))
    monkeypatch.setattr(vn_p, "_VN_BATCH_POOL", RejectingPool())
    monkeypatch.setattr(vn_p, "_VN_BATCH_SLOTS", slots)
    with pytest.raises(RuntimeError):
        vn_p.equity_quote_batch.__wrapped__(["AAA"])
    assert all(slots.acquire(blocking=False) for _ in range(3))


def test_p05_shared_pool_is_singleton():
    a = vn_p._shared_batch_pool(3)
    b = vn_p._shared_batch_pool(3)
    assert a is b, "repeated calls must reuse ONE bounded pool"
    assert a._max_workers == 3, a._max_workers


def test_p05_shared_pool_bounds_live_threads_under_hang():
    pool = vn_p._shared_batch_pool(3)
    release = threading.Event()
    hung = threading.Semaphore(0)

    def hang():
        hung.release()
        release.wait(timeout=15)

    # 3 hanging legs saturate every worker of the shared pool
    futs = [pool.submit(hang) for _ in range(3)]
    for _ in range(3):
        assert hung.acquire(timeout=5), "all 3 workers should be running hangs"
    live_during_hang = threading.active_count()

    # a 4th submission must QUEUE, not spawn a 4th worker (the P05 hard bound)
    pool.submit(hang)
    time.sleep(0.3)
    assert threading.active_count() <= live_during_hang, (
        "a queued 4th leg must not spawn an extra worker"
    )

    release.set()
    for f in futs:
        f.result(timeout=5)
    time.sleep(0.1)  # let completed workers settle
    assert threading.active_count() <= live_during_hang
