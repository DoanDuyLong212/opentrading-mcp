"""Shared Postgres plumbing for the cycle tools (cycle_stats.py, asset_cycle.py).

Fixes from the review of PR #7:
- every query runs in a worker thread with its own connection (psycopg is sync; on the
  0.1-CPU Render instance a connect on the event loop stalls /healthz);
- an empty table reads as "no data yet" (availability unavailable), never as fresh;
- "DATABASE_URL not set" and "cannot connect" are different messages;
- rebuilds run inside one transaction, so readers never see half-rebuilt tables and a
  failure leaves the previous data in place;
- one refresh/finalize at a time per process; write tools can be turned off with
  MCP_CYCLE_WRITE=0 (default on, so a deploy does not remove them).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from opentrading_mcp import dbinit
from opentrading_mcp.schemas import make_envelope

STALE_DAYS = 90
NOT_SEEDED = (
    "Bảng chưa có dữ liệu (chưa seed hoặc refresh). Không kết luận từ bảng này; "
    "chạy refresh (tool *_refresh hoặc `opentrading-mcp cycle-refresh`) rồi thử lại."
)

# One writer at a time: refreshes share symbols and finalize rebuilds every table.
write_lock = asyncio.Lock()


class DbUnavailable(Exception):
    """No database: not configured, or not reachable."""


def writes_enabled() -> bool:
    return os.environ.get("MCP_CYCLE_WRITE", "1").strip() != "0"


def connect(autocommit: bool = True) -> Any:
    url = dbinit.db_url().strip()
    if not url:
        raise DbUnavailable("DATABASE_URL not configured")
    try:
        import psycopg
    except ImportError as exc:
        raise DbUnavailable("psycopg not installed") from exc
    dbinit.ensure_tables()
    try:
        # Neon wakes from idle in a few seconds: 5s was too tight.
        return psycopg.connect(url, autocommit=autocommit, connect_timeout=15)
    except Exception as exc:
        raise DbUnavailable(f"cannot connect to Postgres: {str(exc)[:160]}") from exc


def na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def in_thread[R](fn: Callable[..., R], *args: Any) -> R:
    return await asyncio.to_thread(fn, *args)


def _select(sql: str, args: Sequence[Any]) -> list[tuple[Any, ...]]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, list(args))
            return list(cur.fetchall())
    finally:
        conn.close()


async def read_rows(
    tool: str,
    source: str,
    sql: str,
    args: Sequence[Any],
    cols: Sequence[str],
    filtered: bool = False,
) -> dict[str, Any]:
    """SELECT in a thread; rows as dicts. Empty: 'not seeded' (or 'no match' when filtered)."""
    try:
        rows = await in_thread(_select, sql, args)
    except DbUnavailable as exc:
        return na(tool, str(exc))
    if not rows:
        if filtered:
            return make_envelope(
                {"rows": []}, source=source, warnings=["Không có dòng khớp bộ lọc."]
            )
        return na(tool, NOT_SEEDED)
    out = [
        {c: (str(v) if isinstance(v, date) else v) for c, v in zip(cols, r, strict=False)}
        for r in rows
    ]
    return make_envelope({"rows": out}, source=source)


def _meta(meta_table: str, count_sql: str | None) -> tuple[dict[str, str], int | None]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT key, value FROM {meta_table}")
            meta = {str(k): str(v) for k, v in cur.fetchall()}
            count = None
            if count_sql:
                cur.execute(count_sql)
                count = int(cur.fetchone()[0])
        return meta, count
    finally:
        conn.close()


async def check_freshness(
    tool: str,
    source: str,
    meta_table: str,
    count_sql: str | None,
    extra: dict[str, Any] | None = None,
    expect_meta: dict[str, str] | None = None,
) -> dict[str, Any]:
    """as_of / days_stale / needs_refresh. Never seeded (no as_of, or no rows) needs a refresh.

    expect_meta: meta keys the server's current config requires (e.g. members_version).
    A missing or different value means the stored tables predate the config -> refresh.
    """
    try:
        meta, count = await in_thread(_meta, meta_table, count_sql)
    except DbUnavailable as exc:
        return na(tool, str(exc))
    as_of = meta.get("as_of", "")
    try:
        stale = (date.today() - date.fromisoformat(as_of)).days if as_of else None
    except ValueError:
        stale = None
    mismatch = {k: (meta.get(k), v) for k, v in (expect_meta or {}).items() if meta.get(k) != v}
    seeded = bool(as_of) and (count is None or count > 0)
    stale_or_mismatch = (stale is not None and stale > STALE_DAYS) or bool(mismatch)
    data = {
        "as_of": as_of or None,
        "stats_version": meta.get("stats_version"),
        "days_stale": stale,
        "seeded": seeded,
        "needs_refresh": (not seeded) or stale_or_mismatch,
        **(extra or {}),
    }
    if count is not None:
        data["rows"] = count
    warnings: list[str] | None = None
    if not seeded:
        warnings = [NOT_SEEDED]
    elif mismatch:
        detail = ", ".join(f"{k}={have or 'none'}→{want}" for k, (have, want) in mismatch.items())
        warnings = [
            f"Bảng được tạo từ cấu hình cũ ({detail}); "
            "chạy refresh + finalize trước khi kết luận."
        ]
    return make_envelope(data, source=source, warnings=warnings)


def transactional[R](fn: Callable[..., R], *args: Any) -> R:
    """Run `fn(conn, *args)` in one transaction on its own connection (thread side)."""
    conn = connect(autocommit=False)
    try:
        with conn.transaction():
            return fn(conn, *args)
    finally:
        conn.close()


async def guarded_write(tool: str, work: Callable[[], Any]) -> dict[str, Any] | Any:
    """Writes are off (MCP_CYCLE_WRITE=0), busy (another refresh running) or run one at a time."""
    if not writes_enabled():
        return na(tool, "Ghi bảng chu kỳ đang tắt trên server (MCP_CYCLE_WRITE=0).")
    if write_lock.locked():
        return na(tool, "Đang có một refresh/finalize khác chạy; thử lại sau khi nó xong.")
    async with write_lock:
        return await work()
