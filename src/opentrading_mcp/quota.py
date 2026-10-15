"""Per-user daily quota backed by Postgres (Phase 2).

Uses mcp_auth_tokens (quota_day, default 1000) and mcp_tool_usage.
Team-bearer callers bypass quota (internal, unlimited). When DATABASE_URL
is unset, quota is skipped (local dev) — never fail closed on infra.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import threading
from typing import Any

DEFAULT_QUOTA_DAY = 1000
_POOL_SIZE = 3  # concurrent JWT quota checkouts; quota path must never fan out PG
_POOL_WAIT_SECS = 5.0


class _NoDatabaseError(Exception):
    pass


class _PoolBusy(Exception):
    pass


_pools: dict[int, asyncio.Queue] = {}
_pool_sizes: dict[int, int] = {}
_pool_guard = threading.Lock()


async def _new_conn(url: str) -> Any:
    import psycopg

    return await psycopg.AsyncConnection.connect(url, autocommit=True, connect_timeout=5)


async def _checkout(url: str) -> tuple[int, Any]:
    """Take a pooled PG conn (loop-pinned). Raises _NoDatabaseError/_PoolBusy."""
    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        raise _PoolBusy from None
    with _pool_guard:
        q = _pools.get(loop_key)
        if q is None:
            q = asyncio.Queue(maxsize=_POOL_SIZE)
            _pools[loop_key] = q
            _pool_sizes[loop_key] = 0
    while True:
        try:
            conn = q.get_nowait()
        except asyncio.QueueEmpty:
            with _pool_guard:
                if _pool_sizes[loop_key] < _POOL_SIZE:
                    _pool_sizes[loop_key] += 1
                    fresh = True
                else:
                    fresh = False
            if fresh:
                try:
                    return loop_key, await _new_conn(url)
                except Exception:
                    with _pool_guard:
                        _pool_sizes[loop_key] -= 1
                    raise
            try:
                conn = await asyncio.wait_for(q.get(), _POOL_WAIT_SECS)
            except TimeoutError:
                raise _PoolBusy from None
        if getattr(conn, "closed", False):
            with _pool_guard:
                _pool_sizes[loop_key] -= 1
            continue
        return loop_key, conn


async def _checkin(loop_key: int, conn: Any, broken: bool) -> None:
    with _pool_guard:
        q = _pools.get(loop_key)
    if broken or getattr(conn, "closed", False) or q is None:
        with _pool_guard:
            if loop_key in _pool_sizes:
                _pool_sizes[loop_key] = max(0, _pool_sizes[loop_key] - 1)
        try:
            await conn.close()
        except Exception:
            pass
        return
    try:
        q.put_nowait(conn)
    except asyncio.QueueFull:
        with _pool_guard:
            _pool_sizes[loop_key] = max(0, _pool_sizes[loop_key] - 1)
        try:
            await conn.close()
        except Exception:
            pass


async def _connect() -> Any:
    import psycopg

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise _NoDatabaseError
    conn = await psycopg.AsyncConnection.connect(url, autocommit=True, connect_timeout=5)
    return _PgConn(conn)


class _PgConn:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def __aenter__(self) -> _PgConn:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        await self._conn.close()
        return False

    async def fetchone(self, query: str, params: tuple[Any, ...]) -> Any:
        async with self._conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()

    async def execute(self, query: str, params: tuple[Any, ...]) -> None:
        async with self._conn.cursor() as cur:
            await cur.execute(query, params)


def _seconds_until_midnight() -> int:
    now = datetime.datetime.now().astimezone()
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


async def check_and_record(
    user_id: str, tool: str, duration_ms: float, quota_default: int = DEFAULT_QUOTA_DAY
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds); records one billable call.

    Pooled PG (max 3 conns), fail-open whenever the database — not the user —
    is the problem: missing DATABASE_URL, connection failure, or pool
    exhaustion never blocks a legitimate request.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return True, 0
    try:
        loop_key, raw = await _checkout(url)
    except (_NoDatabaseError, _PoolBusy, Exception):
        return True, 0
    conn = _PgConn(raw)
    broken = False
    try:
        row = await conn.fetchone(
            "SELECT COALESCE((SELECT quota_day FROM mcp_auth_tokens WHERE user_id = %s), %s),"
            " COALESCE((SELECT SUM(count) FROM mcp_tool_usage"
            " WHERE user_id = %s AND day = CURRENT_DATE), 0)",
            (user_id, quota_default, user_id),
        )
        quota_day, used = (row[0], row[1]) if row else (quota_default, 0)
        if int(used) >= int(quota_day):
            return False, _seconds_until_midnight()
        await conn.execute(
            "INSERT INTO mcp_tool_usage (user_id, tool, day, count, total_ms)"
            " VALUES (%s, %s, CURRENT_DATE, 1, %s)"
            " ON CONFLICT (user_id, tool, day) DO UPDATE SET"
            " count = mcp_tool_usage.count + 1,"
            " total_ms = mcp_tool_usage.total_ms + EXCLUDED.total_ms",
            (user_id, tool, int(duration_ms)),
        )
        return True, 0
    except Exception:
        broken = True
        return True, 0
    finally:
        await _checkin(loop_key, raw, broken)
