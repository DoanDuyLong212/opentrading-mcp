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
    now = datetime.datetime.now().astimezone()
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


async def check_and_record(
    user_id: str, tool: str, duration_ms: float, quota_default: int = DEFAULT_QUOTA_DAY
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds); records one billable call."""
    if not os.environ.get("DATABASE_URL", "").strip():
        return True, 0
    try:
        conn = await _connect()
    except _NoDatabaseError:
        return True, 0
    async with conn:
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
