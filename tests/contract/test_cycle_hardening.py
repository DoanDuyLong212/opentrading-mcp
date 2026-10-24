"""Contract: cycle tables (PR #7 review fixes).

DB tests need a throwaway Postgres in TEST_DATABASE_URL (CI starts one; locally e.g.
`docker run -d -p 55432:5432 -e POSTGRES_PASSWORD=pw postgres:16` and
TEST_DATABASE_URL=postgresql://postgres:pw@localhost:55432/postgres). They are skipped without it.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest

from opentrading_mcp import dbinit
from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.tools import cycle_db
from opentrading_mcp.tools.cycle_stats import MEMBERS_VERSION

TEST_DB = os.environ.get("TEST_DATABASE_URL", "").strip()
needs_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


def _fn(name: str) -> Any:
    server = create_server()
    register_all(server)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, name
    return tool.fn


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.delenv("MCP_DB_URL", raising=False)
    monkeypatch.setattr(dbinit, "_ensured", False)
    assert dbinit.ensure_tables()
    conn = cycle_db.connect()
    with conn.cursor() as cur:
        for table in (
            "cycle_meta",
            "cycle_watermark",
            "cycle_month_stats",
            "cycle_ohlcv",
            "vn_asset_meta",
            "vn_asset_monthly",
            "g_asset_meta",
            "g_asset_monthly",
        ):
            cur.execute(f"DELETE FROM {table}")
    yield conn
    conn.close()


@needs_db
def test_empty_tables_read_as_not_seeded_never_as_fresh(db: Any) -> None:
    check = asyncio.run(_fn("cycle_stats_check")())
    assert check["data"]["needs_refresh"] is True
    assert check["data"]["seeded"] is False
    assert any("chưa có dữ liệu" in w for w in check["warnings"])
    rows = asyncio.run(_fn("cycle_seasonality")())
    assert rows["availability"] == "unavailable"
    assert "chưa có dữ liệu" in rows["warnings"][0]
    assert asyncio.run(_fn("vn_asset_check")())["data"]["needs_refresh"] is True
    # A filter that matches nothing on a seeded table is "no match", not "not seeded".
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cycle_month_stats(basket,month,mean_ret,hit_rate,rel_ret,n)"
            " VALUES('bank',1,1.0,60,0.5,8)"
        )
        cur.execute("INSERT INTO cycle_meta(key,value) VALUES('as_of', CURRENT_DATE::text)")
        cur.execute(
            "INSERT INTO cycle_meta(key,value) VALUES('members_version', %s)",
            (MEMBERS_VERSION,),
        )
        cur.execute(
            "INSERT INTO cycle_watermark(symbol,last_date,mode,members_version)"
            " VALUES('VCB', CURRENT_DATE, 'incremental', 'v1')"
        )
    assert asyncio.run(_fn("cycle_seasonality")(basket="bank"))["data"]["rows"][0]["hit_rate"] == 60
    none = asyncio.run(_fn("cycle_seasonality")(basket="steel"))
    assert none["data"]["rows"] == [] and none["availability"] != "unavailable"
    fresh = asyncio.run(_fn("cycle_stats_check")())["data"]
    assert fresh["seeded"] is True and fresh["needs_refresh"] is False


@needs_db
def test_a_failed_rebuild_rolls_back_and_keeps_the_previous_rows(db: Any) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cycle_month_stats(basket,month,mean_ret,hit_rate,rel_ret,n)"
            " VALUES('bank',1,1.0,60,0.5,8)"
        )

    def rebuild(conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cycle_month_stats")
        raise RuntimeError("upstream died mid-rebuild")

    with pytest.raises(RuntimeError):
        cycle_db.transactional(rebuild)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cycle_month_stats")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM cycle_meta WHERE key LIKE 'trough\\_%'")
        assert cur.fetchone()[0] == 0  # rule provenance rides the same transaction


def test_unconfigured_and_unreachable_databases_say_different_things(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MCP_DB_URL", raising=False)
    out = asyncio.run(_fn("cycle_stats_check")())
    assert out["warnings"] == ["DATABASE_URL not configured"]
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")
    monkeypatch.setattr(dbinit, "_ensured", True)
    out = asyncio.run(_fn("cycle_seasonality")())
    assert out["warnings"][0].startswith("cannot connect to Postgres")


def test_reads_never_block_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_connect(autocommit: bool = True) -> Any:
        time.sleep(0.5)  # a Neon wake-up
        raise cycle_db.DbUnavailable("cannot connect to Postgres: slow")

    monkeypatch.setattr(cycle_db, "connect", slow_connect)
    fn = _fn("cycle_chains")

    async def scenario() -> float:
        lag = 0.0

        async def ticker() -> None:
            nonlocal lag
            for _ in range(30):
                started = time.monotonic()
                await asyncio.sleep(0.02)
                lag = max(lag, time.monotonic() - started - 0.02)

        async def call() -> None:
            await asyncio.sleep(0.05)
            await fn()

        await asyncio.gather(ticker(), call())
        return lag

    assert asyncio.run(scenario()) < 0.2


def test_refresh_takes_only_tracked_symbols_and_one_writer_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")
    out = asyncio.run(_fn("cycle_stats_refresh")(symbols=["NOTREAL", "ZZZ"]))
    assert "no tracked symbols" in out["warnings"][0]

    async def busy() -> dict[str, Any]:
        async with cycle_db.write_lock:
            return await _fn("cycle_stats_finalize")()

    assert "Đang có một refresh" in asyncio.run(busy())["warnings"][0]


def test_write_tools_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_CYCLE_WRITE", "0")
    server = create_server()
    names = {t["name"] for t in register_all(server)}
    assert "cycle_stats_check" in names
    assert not names & {
        "cycle_stats_refresh",
        "cycle_stats_finalize",
        "vn_asset_refresh",
        "g_asset_refresh",
    }


def test_server_web_fetch_refuses_names_resolving_to_private_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from opentrading_mcp.providers import webfetch
    from opentrading_mcp.providers.errors import ProviderBadData

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))])
    with pytest.raises(ProviderBadData, match="non-public"):
        webfetch.fetch_url("https://rebind.example/admin")
    with pytest.raises(ProviderBadData, match="local"):
        webfetch.fetch_url("http://localhost:8102/healthz")
