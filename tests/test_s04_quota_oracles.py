"""S04 oracles — quota admission is transactional and timezone-locked."""

from __future__ import annotations

import asyncio
from typing import Any
import datetime
import zoneinfo

import pytest

from opentrading_mcp import quota as quota_mod


class _RecordingConn:
    """Minimal conn double: records the statement sequence, feeds canned rows."""

    def __init__(self, fetch_results: list[Any]):
        self.statements: list[str] = []
        self._fetch_results = list(fetch_results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, query, params=None):
        self.statements.append(" ".join(str(query).split())[:60])
        self.params_by_stmt = getattr(self, "params_by_stmt", {})
        self.params_by_stmt[self.statements[-1]] = params

    async def fetchone(self, query, params):
        self.statements.append(" ".join(str(query).split())[:60])
        return self._fetch_results.pop(0) if self._fetch_results else (1000, 0)

    async def commit(self):
        self.statements.append("COMMIT")


def test_s04_quota_sequence_is_transactional_and_uses_vn_day(monkeypatch):
    """check_and_record must: BEGIN → per-user advisory lock → quota read on the
    Asia/Ho_Chi_Minh day → usage upsert → COMMIT. Missing statements fail."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    conn = _RecordingConn([(1000, 0)])

    async def fake_factory():
        return conn

    monkeypatch.setattr(quota_mod, "_connect", fake_factory)
    allowed, _ = asyncio.run(quota_mod.check_and_record("u1", "market_snapshot", 15))
    assert allowed is True

    joined = " | ".join(conn.statements)
    assert "BEGIN" in joined, joined
    assert "pg_advisory_xact_lock" in joined, joined  # per-user serialization
    assert "INSERT INTO mcp_tool_usage" in joined, joined
    assert "COMMIT" in joined, joined
    # the recorded day must be the Asia/Ho_Chi_Minh date (in the INSERT params,
    # not the PG session's CURRENT_DATE)
    vn_day = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    insert_params = next(
        (p for stmt, p in conn.params_by_stmt.items() if stmt.startswith("INSERT INTO")), ()
    )
    assert vn_day in insert_params, insert_params


def test_s04_quota_day_uses_vn_midnight_boundary():
    """At 16:59:59 UTC it is still the previous VN day; at 17:00 UTC the VN day
    rolls over (UTC+7). retry_after counts to VN midnight."""
    import os

    from opentrading_mcp import quota as quota_mod

    assert "Asia/Ho_Chi_Minh" in quota_mod.QUOTA_TZ
    now_vn = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh"))
    day, remaining = quota_mod._quota_day_and_remaining()
    assert day == now_vn.date().isoformat()
    # remaining must be <= 24h and point at VN midnight (≤2s slack: the value
    # is integer-truncated and time passes between the two clocks)
    assert 1 <= remaining <= 86400
    vn_midnight = now_vn + datetime.timedelta(seconds=remaining)
    target = (now_vn + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    assert abs((vn_midnight - target).total_seconds()) <= 2
