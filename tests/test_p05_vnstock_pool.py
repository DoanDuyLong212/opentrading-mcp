"""P05 oracle — the vnstock batch pool is a process-wide singleton bounded at
3 workers: hung legs occupy a worker but can never multiply live threads."""

from __future__ import annotations

import threading
import time

from opentrading_mcp.providers import vnstock as vn_p


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
