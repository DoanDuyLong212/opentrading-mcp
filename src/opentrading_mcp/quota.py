"""Per-user daily quota backed by Postgres (Phase 2).

Uses mcp_auth_tokens (quota_day, default 1000) and mcp_tool_usage.
Team-bearer callers bypass quota (internal, unlimited). When DATABASE_URL
is unset, quota is skipped (local dev) — never fail closed on infra.
"""

from __future__ import annotations

import datetime
import os
from typing import Any

DEFAULT_QUOTA_DAY = 1000
QUOTA_TZ = "Asia/Ho_Chi_Minh"  # S04: quota day locked to the business timezone


async def _connect() -> Any:
    import psycopg

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise _NoDatabaseError
    conn = await psycopg.AsyncConnection.connect(url, autocommit=True, connect_timeout=5)
    return _PgConn(conn)


class _NoDatabaseError(Exception):
    pass


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
    """Seconds to the next quota-day boundary in the quota timezone (S04:
    quota day is Asia/Ho_Chi_Minh — the server's declared business timezone —
    independent of host/PG session timezone; boundary = VN midnight, UTC+7)."""
    _, remaining = _quota_day_and_remaining()
    return remaining


def _quota_day_and_remaining() -> tuple[str, int]:
    import zoneinfo

    now = datetime.datetime.now(zoneinfo.ZoneInfo(QUOTA_TZ))
    day = now.date().isoformat()
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return day, max(1, int((midnight - now).total_seconds()))


async def check_and_record(
    user_id: str, tool: str, duration_ms: float, quota_default: int = DEFAULT_QUOTA_DAY
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds); records one billable call.

    S04: check+increment run in ONE transaction serialized by a per-user
    advisory lock, so concurrent calls can never exceed the daily quota. The
    recorded day and retry-after use the explicit quota timezone, not the
    PG session timezone."""
    if not os.environ.get("DATABASE_URL", "").strip():
        return True, 0
    try:
        conn = await _connect()
    except _NoDatabaseError:
        return True, 0
    day, retry_after = _quota_day_and_remaining()
    async with conn:
        await conn.execute("BEGIN")
        try:
            # per-user transaction lock: serializes concurrent quota decisions
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_id,))
            row = await conn.fetchone(
                "SELECT COALESCE((SELECT quota_day FROM mcp_auth_tokens WHERE user_id = %s), %s),"
                " COALESCE((SELECT SUM(count) FROM mcp_tool_usage"
                " WHERE user_id = %s AND day = %s), 0)",
                (user_id, quota_default, user_id, day),
            )
            quota_day, used = (row[0], row[1]) if row else (quota_default, 0)
            if int(used) >= int(quota_day):
                await conn.execute("COMMIT")
                return False, retry_after
            await conn.execute(
                "INSERT INTO mcp_tool_usage (user_id, tool, day, count, total_ms)"
                " VALUES (%s, %s, %s, 1, %s)"
                " ON CONFLICT (user_id, tool, day) DO UPDATE SET"
                " count = mcp_tool_usage.count + 1,"
                " total_ms = mcp_tool_usage.total_ms + EXCLUDED.total_ms",
                (user_id, tool, day, int(duration_ms)),
            )
            await conn.execute("COMMIT")
            return True, 0
        except Exception:
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
