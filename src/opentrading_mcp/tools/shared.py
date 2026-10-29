"""Shared tool annotation + context alias (imported by all tool modules)."""

from __future__ import annotations

import asyncio
import contextvars
import copy
import functools
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
READ_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
# Phân loại write để client (OpenTrading RwLock, Claude permission, Cursor review)
# quyết định chạy song song vs hỏi duyệt:
READ_WRITE_CREATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
READ_WRITE_DELETE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)
READ_WRITE_STATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
# Tools gọi mạng ngoài (web/yfinance/Binance/GDELT/Polymarket/FRED): open-world.
READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)

AnyContext = Context[Any, Any, Any]


CLOSE_KEYS = ("c", "close", "Close", "CLOSE")
HIGH_KEYS = ("h", "high", "High", "HIGH")
LOW_KEYS = ("l", "low", "Low", "LOW")


def pick_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first matching key's value, or None (P1 shared helper)."""
    for k in keys:
        if k in row:
            return row[k]
    return None


def project_rows(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    """Project rows to a column subset; None/empty returns rows as-is (P1 shared)."""
    if not columns:
        return rows
    return [{k: r[k] for k in columns if k in r} for r in rows]


TIME_KEYS = ("t", "time", "Time", "date", "Date")


def last_bar_time(rows: list[dict[str, Any]]) -> str | None:
    """Newest bar timestamp in a candle series (or None) for data_time provenance."""
    for r in reversed(rows):
        if not isinstance(r, dict):
            continue
        t = pick_value(r, TIME_KEYS)
        if t not in (None, ""):
            return str(t)
    return None


def in_vn_session(now: Any = None) -> bool:
    """True during HOSE continuous hours (Mon-Fri 09:00-15:00 ICT), best-effort.

    Holidays are not consulted (calendar unverified); a holiday behaves like a
    normal day here, which only costs shorter TTLs, never stale data.
    Pass `now` (a ZoneInfo-aware datetime) in tests.
    """
    try:
        if now is None:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        elif getattr(now, "tzinfo", None) is not None:
            # F12: normalize ANY timezone-aware input to VN time — a UTC-aware
            # caller at 16:59/17:00 UTC (VN midnight boundary) must not be
            # evaluated with UTC hours.
            from zoneinfo import ZoneInfo

            now = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    except Exception:
        return True  # fail-open to short TTLs: fresh data over saved fetches
    if now.weekday() >= 5:
        return False
    return 9 * 60 <= now.hour * 60 + now.minute < 15 * 60


def seconds_until_session(now: Any = None) -> float:
    """Seconds until the next HOSE open (Mon-Fri 09:00 ICT); 0 during the session."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    moment = now.astimezone(tz) if now is not None else datetime.now(tz)
    if in_vn_session(moment):
        return 0.0
    opening = moment.replace(hour=9, minute=0, second=0, microsecond=0)
    if moment >= opening:
        opening += timedelta(days=1)
    while opening.weekday() >= 5:
        opening += timedelta(days=1)
    return (opening - moment).total_seconds()


def price_ttl(now: Any = None) -> int:
    """TTL for price/board data: short in session, long when HOSE cannot move.

    The long off-hours TTL never reaches past the next open: a quote fetched at
    08:59 must not still be served at 10:00.
    """
    from opentrading_mcp.cache import TTL_SECONDS

    if in_vn_session(now):
        return TTL_SECONDS["market"]
    try:
        until_open = int(seconds_until_session(now))
    except Exception:
        return TTL_SECONDS["market"]
    return max(1, min(TTL_SECONDS["market_offhours"], until_open))


async def _cache_key_for(tool: str, fingerprint: str) -> str:
    from opentrading_mcp.cache import cache_key

    # S05: no conditional shortening — cache_key hashes the complete raw
    # fingerprint (full SHA-256), so distinct financial arguments never share
    # a payload key.
    return cache_key(tool, fingerprint)


async def cache_lookup(tool: str, fingerprint: str) -> dict[str, Any] | None:
    """Rebuilt envelope on cache hit (with data_time + age warning), else None.

    Callers check this FIRST and return immediately on hit. Failures and
    unavailable/error envelopes are never stored, so a hit is always a
    successful past response. The original provider stays in
    provenance.source; provenance.cached / cached_at disclose the reuse.

    On a miss, concurrent callers for the SAME key coalesce: the first becomes
    the leader (returns None, fetches upstream), the rest wait for the leader's
    cache_store and get its envelope — stored or not, so an empty result is
    shared instead of re-fetched. A leader that returns without cache_store
    (an error envelope, an exception) is released when its request task ends;
    waiters then re-read and one of them leads the retry. This stops a cold-key
    stampede from executing the same 45-90s upstream N times on the 2-slot
    executor.
    """
    from opentrading_mcp.providers.store import acache_get

    key = await _cache_key_for(tool, fingerprint)
    deadline = time.monotonic() + _WAITER_TIMEOUT
    while True:
        hit = await acache_get(key)
        if hit is not None:
            return _envelope_from_cache(hit)
        waiter = _join_inflight(key)
        if waiter is None:
            return None  # leader: caller fetches, then cache_store resolves us
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None  # leader too slow: fetch ourselves
        try:
            shared = await asyncio.wait_for(asyncio.shield(waiter), remaining)
        except (TimeoutError, asyncio.CancelledError):
            return None
        if isinstance(shared, dict):
            return copy.deepcopy(shared)
        # The leader ended without a result: re-read, or lead the retry.


def _envelope_from_cache(hit: str) -> dict[str, Any] | None:
    import json

    from opentrading_mcp.schemas import make_envelope

    try:
        cached = json.loads(hit)
        data = cached.get("data")
    except (ValueError, TypeError, AttributeError):
        return None
    if data is None:
        return None
    cached_at = cached.get("as_of")
    env = make_envelope(
        data,
        # Entries written before the source was stored fall back to "cache".
        source=cached.get("source") or "cache",
        warnings=list(cached.get("warnings") or []),
        availability=cached.get("availability"),
        page=cached.get("page"),
        data_time=cached.get("data_time") or cached_at,
    )
    env["provenance"]["cached"] = True
    env["provenance"]["cached_at"] = cached_at
    env["warnings"] = [*env["warnings"], f"dữ liệu lấy lúc {cached_at}, dùng lại bản đã lưu"]
    return env


async def cache_store(
    tool: str,
    fingerprint: str,
    ttl_seconds: int,
    data: Any,
    source: str,
    warnings: list[str] | None = None,
    availability: str | None = None,
    page: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    data_time: str | None = None,
) -> dict[str, Any]:
    """Build the envelope AND store a successful one for later hits."""
    from opentrading_mcp.providers.store import acache_set
    from opentrading_mcp.schemas import make_envelope

    env = make_envelope(
        data,
        source=source,
        warnings=warnings,
        availability=availability,
        page=page,
        error=error,
        data_time=data_time,
    )
    key = await _cache_key_for(tool, fingerprint)
    # Never persist failures — or empties: "not found" is often transient
    # (a just-listed symbol, a pre-open board), and a cached empty would hide
    # recovery until TTL expiry. Partial results (some legs failed) are kept
    # only briefly, for the same reason.
    availability = env.get("availability")
    if availability not in ("unavailable", "failed", "empty") and not env.get("error"):
        if availability == "partial":
            ttl_seconds = min(ttl_seconds, _PARTIAL_TTL)
        await acache_set(
            key,
            {
                "data": env["data"],
                "warnings": env.get("warnings", []),
                "availability": availability,
                "page": env.get("page"),
                "source": env["provenance"]["source"],
                "as_of": env["provenance"]["as_of"],
                "data_time": env["provenance"].get("data_time"),
            },
            ttl_seconds,
        )
    # Waiters get this envelope whether or not it was stored.
    _resolve_inflight(key, env)
    return env


# --- Single-flight: coalesce concurrent misses for the same cache key --------
# Leader = first misser (fetches upstream, cache_store resolves). Waiters =
# later missers (await the leader's envelope). Entries are
# (loop, future, created_at, owner task); stale entries (>_INFLIGHT_TTL) are
# ignored so a crashed leader can never wedge waiters forever. The owner task
# looking the key up again leads again instead of waiting on itself, and the
# end of that task releases whatever it still holds. Loop-pinned so multi-loop
# processes (tests) simply skip coalescing instead of cross-loop awaiting.
_inflight: dict[
    str, tuple[asyncio.AbstractEventLoop, asyncio.Future, float, asyncio.Task | None]
] = {}
_inflight_guard = threading.Lock()
_INFLIGHT_TTL = 120.0
_WAITER_TIMEOUT = 60.0
_PARTIAL_TTL = 60


def _join_inflight(key: str) -> asyncio.Future | None:
    """None = you are the leader (fetch). Future = wait on it for the leader's envelope."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    task = asyncio.current_task()
    now = time.monotonic()
    with _inflight_guard:
        ent = _inflight.get(key)
        if ent is not None and ent[0] is loop and not ent[1].done():
            if task is not None and ent[3] is task:
                return None  # the leader itself, looking the key up again
            if now - ent[2] < _INFLIGHT_TTL:
                return ent[1]
        if len(_inflight) > 2000:  # pathological keyspace: drop oldest
            _inflight.pop(next(iter(_inflight)))
        future = loop.create_future()
        _inflight[key] = (loop, future, now, task)
    if task is not None:
        task.add_done_callback(lambda _task: _release_inflight(key, future))
    return None


def _resolve_inflight(key: str, result: dict[str, Any] | None = None) -> None:
    """Wake waiters with the leader's envelope (best-effort, never raises)."""
    with _inflight_guard:
        ent = _inflight.pop(key, None)
    if ent is not None:
        _wake(ent[0], ent[1], result)


def _release_inflight(key: str, future: asyncio.Future) -> None:
    """The leader's task ended: release its entry if it still holds it."""
    with _inflight_guard:
        ent = _inflight.get(key)
        if ent is None or ent[1] is not future:
            return
        _inflight.pop(key, None)
    _wake(ent[0], future, None)


def _wake(loop: asyncio.AbstractEventLoop, future: asyncio.Future, result: Any) -> None:
    def _set() -> None:
        if not future.done():
            future.set_result(result)

    try:
        loop.call_soon_threadsafe(_set)
    except RuntimeError:
        pass  # loop already closed


def summarize_rows(
    symbol: str, rows: list[dict[str, Any]], *, uppercase: bool = True
) -> dict[str, Any]:
    """Summarize OHLC rows to {symbol, count, last, high, low, last_t} (P1 shared).

    uppercase=True preserves vn.py/vn_ext.py behavior (symbol.upper());
    uppercase=False preserves market.py/dnse_tools.py behavior (symbol as-is).
    Key aliases cover c/close/Close/CLOSE etc (superset of dnse's old subset).
    `last_t` is the newest bar timestamp (or None) so callers can judge
    staleness without the full series.
    """
    name = symbol.upper() if uppercase else symbol
    if not rows:
        return {"symbol": name, "count": 0, "last": None, "high": None, "low": None}
    closes = [pick_value(r, CLOSE_KEYS) for r in rows]
    highs = [pick_value(r, HIGH_KEYS) for r in rows]
    lows = [pick_value(r, LOW_KEYS) for r in rows]
    last_close = closes[-1] if closes[-1] is not None else rows[-1]
    try:
        high = max(h for h in highs if isinstance(h, (int, float)))
    except ValueError:
        high = None
    try:
        low = min(lo for lo in lows if isinstance(lo, (int, float)))
    except ValueError:
        low = None
    last_t = last_bar_time(rows)
    return {
        "symbol": name,
        "count": len(rows),
        "last": last_close,
        "high": high,
        "low": low,
        "last_t": last_t,
    }


def blocking_slots() -> int:
    """How many blocking upstream calls may run at once (env MCP_BLOCKING_SLOTS, default 2).

    vnstock/pandas work is CPU-bound and holds the GIL. On a 0.1-CPU host (Render free)
    five of them at once starved the event loop until /healthz timed out and the
    instance was killed (10/10/2026). Extra calls wait for a slot instead.
    """
    try:
        return max(1, int(os.environ.get("MCP_BLOCKING_SLOTS", "2")))
    except ValueError:
        return 2


# Blocking upstream work runs here, not in asyncio's default pool: a queued call holds no
# thread, so Redis reads (to_thread) and /readyz never wait behind a burst of tool calls.
_EXECUTOR = ThreadPoolExecutor(max_workers=blocking_slots(), thread_name_prefix="upstream")


def compute_slots() -> int:
    """Slots for CPU/DB-bound compute jobs (env MCP_COMPUTE_SLOTS, default 1).

    Long jobs (backtests, cycle/asset refresh, snapshots) must not sit on the
    interactive pool: on 0.1 CPU one 900s job held 50% of server capacity.
    """
    try:
        return max(1, int(os.environ.get("MCP_COMPUTE_SLOTS", "1")))
    except ValueError:
        return 1


_HEAVY_EXECUTOR = ThreadPoolExecutor(max_workers=compute_slots(), thread_name_prefix="compute")


def shed_limit() -> int:
    """Max queued+running blocking calls before fast-reject (env MCP_QUEUE_SHED, default 50).

    Without a cap the queue is unbounded and wait time counts toward each
    caller's timeout — a stampede fails slowly (60s timeouts) instead of fast.
    Past this many outstanding calls, new ones fail immediately with a
    retryable error instead of joining the pile.
    """
    try:
        return max(1, int(os.environ.get("MCP_QUEUE_SHED", "50")))
    except ValueError:
        return 50


_pending = 0
_pending_guard = threading.Lock()


def neg_ttl() -> float:
    """Seconds a timed-out/slow-failed leg stays failed-fast (env MCP_NEG_TTL, default 90).

    Only timeouts and slow upstream failures are remembered — auth-missing and
    bad-data raise different errors and are never marked (auth flips on login,
    bad params fail fast anyway). 0 disables.
    """
    try:
        return max(0.0, float(os.environ.get("MCP_NEG_TTL", "90")))
    except ValueError:
        return 90.0


_neg: dict[str, float] = {}
_neg_guard = threading.Lock()


# A ProviderUnavailable counts as slow (worth remembering) past this many seconds;
# fast ones (rate limit, 4xx, unknown symbol) say nothing about the next call.
_NEG_SLOW_SECONDS = 10.0


def _neg_key(tool: str, fn: Callable[..., Any]) -> str:
    """Tool label plus the call's arguments: one slow symbol must not block the others."""
    if isinstance(fn, functools.partial):
        try:
            args = repr((fn.args, sorted(fn.keywords.items())))
        except Exception:
            return tool
        return f"{tool}|{args[:200]}"
    return tool


def _neg_hit(key: str) -> bool:
    ttl = neg_ttl()
    if ttl <= 0:
        return False
    with _neg_guard:
        until = _neg.get(key)
        if until is None:
            return False
        if time.monotonic() < until:
            return True
        _neg.pop(key, None)
        return False


def _neg_mark(key: str) -> None:
    ttl = neg_ttl()
    if ttl <= 0:
        return
    with _neg_guard:
        if len(_neg) > 2000:
            _neg.pop(next(iter(_neg)))
        _neg[key] = time.monotonic() + ttl


RATE_LIMITED = "upstream rate limit reached"


def no_exit[T](fn: Callable[[], T]) -> T:
    """vnai (vnstock) calls sys.exit() when its 60 req/min quota is hit. In a worker thread
    the SystemExit travels through the future into the event loop and stops the server
    (a 502 for every client). Turn it into an ordinary provider error."""
    from opentrading_mcp.providers.errors import ProviderUnavailable

    try:
        return fn()
    except SystemExit as exc:
        raise ProviderUnavailable(f"{RATE_LIMITED}: {str(exc)[:160]}") from None


async def run_blocking[T](
    fn: Callable[[], T], tool: str, timeout_secs: float = 60.0, heavy: bool = False
) -> T:
    """Run a blocking upstream call in a worker thread with a hard timeout.

    Prevents one stalled upstream (e.g. retail endpoints from certain
    regions) from hanging the tool past the client's call timeout.

    At most ``blocking_slots()`` calls run at once; the rest queue. Queue time counts
    toward ``timeout_secs``. On a timeout a call that has not started is cancelled and
    never runs; one that is running keeps its worker until it really ends (threads
    cannot be killed), so the cap holds even for stalled upstreams.

    heavy=True routes to the separate compute pool (backtests, cycle/asset
    refresh, snapshots) so long CPU/DB jobs never starve interactive tools.

    When more than ``shed_limit()`` calls are already outstanding, new calls
    fail fast ("server busy") instead of queueing toward a certain timeout.

    Slow legs are also remembered briefly: a timeout (or an upstream failure
    that took over ``_NEG_SLOW_SECONDS``) marks that call — tool label plus
    arguments — for ``neg_ttl()`` seconds, so retries and concurrent waiters
    fail in milliseconds instead of re-paying the full 45-90s upstream cost.
    """
    from opentrading_mcp.providers.errors import ProviderUnavailable

    global _pending
    neg_key = _neg_key(tool, fn)
    if _neg_hit(neg_key):
        raise ProviderUnavailable(f"{tool} briefly unavailable (recent timeout), retry shortly")
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    pool = _HEAVY_EXECUTOR if heavy else _EXECUTOR
    with _pending_guard:
        if _pending >= shed_limit():
            raise ProviderUnavailable(
                f"{tool} shed: server busy ({_pending} calls outstanding), retry shortly"
            )
        _pending += 1
    started = time.monotonic()

    # P01: exactly ONE release per admission — the thread's real completion OR
    # a cancelled-while-queued skip, never both (a wrapper cancel plus a late
    # thread finish would otherwise double-release below baseline).
    released = False

    def _release_once() -> None:
        nonlocal released
        global _pending
        with _pending_guard:
            if released:
                return
            released = True
            _pending -= 1

    def _tracked():
        # the admission stays counted until the thread ACTUALLY finishes
        try:
            return ctx.run(no_exit, fn)
        finally:
            _release_once()

    # Only the executor Future knows whether cancellation prevented execution.
    # An asyncio wrapper can be cancelled while its thread is still running.
    try:
        submitted = pool.submit(_tracked)
    except BaseException:
        _release_once()
        raise
    submitted.add_done_callback(lambda _future: _release_once())
    try:
        future = asyncio.wrap_future(submitted, loop=loop)
        try:
            return await asyncio.wait_for(future, timeout_secs)
        except TimeoutError as exc:
            _neg_mark(neg_key)
            raise ProviderUnavailable(f"{tool} timed out after {timeout_secs}s") from exc
    except ProviderUnavailable:
        if time.monotonic() - started >= _NEG_SLOW_SECONDS:
            _neg_mark(neg_key)
        raise
