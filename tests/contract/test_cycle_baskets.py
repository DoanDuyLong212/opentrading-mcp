"""Contract: VN sector baskets v2 (members + aliases + version guard).

Structural tests run everywhere; DB tests need a throwaway Postgres in
TEST_DATABASE_URL (CI starts one; locally e.g.
`docker run -d -p 55432:5432 -e POSTGRES_PASSWORD=pw postgres:16` and
TEST_DATABASE_URL=postgresql://postgres:pw@localhost:55432/postgres).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pandas as pd
import psycopg
import pytest

from opentrading_mcp import dbinit
from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.tools import cycle_db
from opentrading_mcp.tools.cycle_stats import (
    ALL_SYMBOLS,
    BASKETS,
    CHAIN_PAIRS,
    INDICES,
    MEMBERS_VERSION,
    TROUGH_BASKETS,
    _canon_basket,
)

TEST_DB = os.environ.get("TEST_DATABASE_URL", "").strip()
needs_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")

EXPECTED_BASKETS = {
    "bank", "securities", "insurance", "realestate", "vin", "construction",
    "steel", "chemical", "oilgas", "utility", "tech", "retail", "consumer",
    "food", "transport",
}


def test_baskets_shape() -> None:
    assert set(BASKETS) == EXPECTED_BASKETS
    for name, members in BASKETS.items():
        assert len(members) >= 3, f"{name} too thin: {members}"
        assert members == [s.upper() for s in members], name
    seen: dict[str, str] = {}
    for name, members in BASKETS.items():
        for s in members:
            assert s not in seen, f"{s} in both {seen[s]} and {name}"
            seen[s] = name


def test_members_v2_moves() -> None:
    assert set(BASKETS["vin"]) == {"VIC", "VHM", "VRE", "VPL"}
    assert not {"VIC", "VHM", "VRE"} & set(BASKETS["realestate"])
    # dead/suspended members were dropped
    assert "ITA" not in BASKETS["realestate"]
    assert "POM" not in BASKETS["steel"]
    assert "SFN" not in BASKETS["food"]
    # telecom merged into tech
    assert {"VGI", "FOX", "ICT"} <= set(BASKETS["tech"])
    assert "telecom" not in BASKETS
    # supplemented thin baskets
    for name, floor in {
        "insurance": 6, "construction": 8, "steel": 6, "chemical": 7,
        "food": 9, "transport": 8,
    }.items():
        assert len(BASKETS[name]) >= floor, name


def test_chains_and_trough_reference_real_baskets() -> None:
    assert isinstance(CHAIN_PAIRS, list) and CHAIN_PAIRS
    for a, b in CHAIN_PAIRS:
        assert a in BASKETS and b in BASKETS, (a, b)
    assert {("bank", "vin"), ("vin", "realestate"), ("realestate", "vin")} <= set(CHAIN_PAIRS)
    assert "vin" in TROUGH_BASKETS
    for b in TROUGH_BASKETS:
        assert b in BASKETS


def test_all_symbols_is_indices_plus_members() -> None:
    members = {s for v in BASKETS.values() for s in v}
    assert set(ALL_SYMBOLS) == set(INDICES) | members
    assert "VPL" in ALL_SYMBOLS and "FOX" in ALL_SYMBOLS


def test_members_version_is_v2() -> None:
    assert MEMBERS_VERSION == "v2"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("bank", "bank"),
        ("ngân hàng", "bank"),
        ("Chứng khoán", "securities"),
        ("bất động sản", "realestate"),
        ("BĐS", "realestate"),
        ("Vin", "vin"),
        ("họ Vin", "vin"),
        ("xây dựng", "construction"),
        ("thép", "steel"),
        ("hóa chất", "chemical"),
        ("dầu khí", "oilgas"),
        ("Dau Khi", "oilgas"),
        ("điện", "utility"),
        ("tiện ích", "utility"),
        ("CNTT", "tech"),
        ("viễn thông", "tech"),
        ("công nghệ", "tech"),
        ("bán lẻ", "retail"),
        ("tiêu dùng", "consumer"),
        ("thực phẩm", "food"),
        ("bảo hiểm", "insurance"),
        ("vận tải", "transport"),
    ],
)
def test_canon_basket(raw: str, expected: str) -> None:
    assert _canon_basket(raw) == expected


def test_canon_basket_passthrough_and_none() -> None:
    assert _canon_basket("khong-ton-tai") == "khong-ton-tai"
    assert _canon_basket(None) is None


def test_tool_docstring_lists_every_basket() -> None:
    """The description is what the model reads before choosing basket=."""
    doc = _fn("cycle_seasonality").__doc__ or ""
    missing = [b for b in BASKETS if b not in doc]
    assert not missing, f"basket keys missing from cycle_seasonality docstring: {missing}"


def test_finalize_refuses_when_schema_ensure_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentrading_mcp.tools import cycle_stats

    monkeypatch.setattr(dbinit, "ensure_tables", lambda: False)
    with pytest.raises(Exception, match="schema"):
        cycle_stats._finalize_compute(None, [])


def _seed_trough_cycle(conn: Any) -> None:
    """Synthetic VNINDEX + one bank name: -20% drawdown then +25% recovery."""
    dates = [pd.Timestamp("2020-01-01") + pd.Timedelta(days=i) for i in range(95)]
    vn = []
    v = 100.0
    for i in range(95):
        if i < 5:
            pass
        elif i < 20:
            v *= 0.985  # ~ -20% by day 20
        elif i < 35:
            v *= 1.02  # recovery > 20%
        vn.append(round(v, 2))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO cycle_ohlcv(symbol,t,o,h,l,c,v) VALUES(%s,%s,%s,%s,%s,%s,0)"
            " ON CONFLICT DO NOTHING",
            [("VNINDEX", d.date(), c, c, c, c) for d, c in zip(dates, vn, strict=False)],
        )
        cur.executemany(
            "INSERT INTO cycle_ohlcv(symbol,t,o,h,l,c,v) VALUES(%s,%s,%s,%s,%s,%s,0)"
            " ON CONFLICT DO NOTHING",
            [("VCB", d.date(), c, c, c, c) for d, c in zip(dates, vn, strict=False)],
        )


@needs_db
def test_trough_insert_failure_aborts_finalize_instead_of_silently_skipping(
    db: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opentrading_mcp.tools import cycle_stats

    _seed_trough_cycle(db)
    with db.cursor() as cur:
        cur.execute("ALTER TABLE cycle_trough_events DROP COLUMN vin")
    # Simulate a DB where the migration cannot run, so ensure_tables cannot fix it.
    monkeypatch.setattr(dbinit, "ensure_tables", lambda: True)
    try:
        with pytest.raises(psycopg.Error):
            cycle_stats._finalize_compute(db, [])
        # A failed rebuild must not stamp a fresh members_version.
        with db.cursor() as cur:
            cur.execute("SELECT value FROM cycle_meta WHERE key='members_version'")
            row = cur.fetchone()
        assert row is None or row[0] != "v2"
    finally:
        with db.cursor() as cur:
            cur.execute(
                "ALTER TABLE cycle_trough_events"
                " ADD COLUMN IF NOT EXISTS vin DOUBLE PRECISION"
            )


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
        for table in ("cycle_meta", "cycle_watermark", "cycle_month_stats",
                      "cycle_ohlcv", "cycle_trough_events"):
            cur.execute(f"DELETE FROM {table}")
    yield conn
    conn.close()


@needs_db
def test_basket_alias_filters_end_to_end(db: Any) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cycle_month_stats(basket,month,mean_ret,hit_rate,rel_ret,n)"
            " VALUES('realestate',1,1.0,60,0.5,8), ('bank',1,2.0,70,1.0,8)"
        )
    out = asyncio.run(_fn("cycle_seasonality")(basket="BĐS"))
    rows = out["data"]["rows"]
    assert rows and all(r["basket"] == "realestate" for r in rows)


@needs_db
def test_members_version_mismatch_flags_refresh(db: Any) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cycle_month_stats(basket,month,mean_ret,hit_rate,rel_ret,n)"
            " VALUES('bank',1,1.0,60,0.5,8)"
        )
        cur.execute("INSERT INTO cycle_meta(key,value) VALUES('as_of', CURRENT_DATE::text)")
        cur.execute(
            "INSERT INTO cycle_watermark(symbol,last_date,mode,members_version)"
            " VALUES('VCB', CURRENT_DATE, 'incremental', 'v1')"
        )
    # meta has no members_version yet -> config unknown -> refresh recommended
    out = asyncio.run(_fn("cycle_stats_check")())["data"]
    assert out["needs_refresh"] is True
    # stale config v1 -> refresh recommended, warning explains why
    with db.cursor() as cur:
        cur.execute("INSERT INTO cycle_meta(key,value) VALUES('members_version','v1')")
    out = asyncio.run(_fn("cycle_stats_check")())
    assert out["data"]["needs_refresh"] is True
    assert any("members_version" in w for w in out["warnings"])
    # current config -> fresh
    with db.cursor() as cur:
        cur.execute("UPDATE cycle_meta SET value='v2' WHERE key='members_version'")
    out = asyncio.run(_fn("cycle_stats_check")())["data"]
    assert out["needs_refresh"] is False


@needs_db
def test_trough_events_vin_column_migration(db: Any) -> None:
    old_ddl = (
        "CREATE TABLE cycle_trough_events ("
        " trough DATE PRIMARY KEY, vnindex_3m DOUBLE PRECISION,"
        " bank DOUBLE PRECISION, securities DOUBLE PRECISION,"
        " realestate DOUBLE PRECISION, oilgas DOUBLE PRECISION,"
        " steel DOUBLE PRECISION, utility DOUBLE PRECISION,"
        " tech DOUBLE PRECISION)"
    )
    with db.cursor() as cur:
        cur.execute("DROP TABLE cycle_trough_events")
        cur.execute(old_ddl)
    dbinit._ensured = False  # type: ignore[attr-defined]
    assert dbinit.ensure_tables()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cycle_trough_events(trough,vnindex_3m,bank,vin)"
            " VALUES('2022-11-15', 30.0, 20.0, 42.0)"
        )
    out = asyncio.run(_fn("cycle_trough_events")())
    row = out["data"]["rows"][0]
    assert row["vin"] == 42.0


def _seed_yearly_cycle(conn: Any) -> None:
    """VNINDEX + one vin member (VIC): full 2024 + a partial current year."""
    frames = []
    for year, end in ((2024, f"{2024}-12-31"), (2026, "2026-10-20")):
        days = pd.date_range(f"{year}-01-01", end, freq="D")
        for sym in ("VNINDEX", "VIC"):
            frames.append(
                pd.DataFrame(
                    {"symbol": sym, "t": days.date, "c": 100.0}
                )
            )
    rows = pd.concat(frames)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO cycle_ohlcv(symbol,t,o,h,l,c,v)"
            " VALUES(%s,%s,100,100,100,%s,0) ON CONFLICT DO NOTHING",
            list(rows.itertuples(index=False, name=None)),
        )


@needs_db
def test_trough_events_carry_confirmation_and_window_metadata(db: Any) -> None:
    from opentrading_mcp.tools import cycle_stats

    _seed_trough_cycle(db)
    cycle_stats._finalize_compute(db, [])
    with db.cursor() as cur:
        cur.execute(
            "SELECT trough, confirmation, window_start, window_end, window_days,"
            " window_observations, window_complete, basket_observations"
            " FROM cycle_trough_events ORDER BY trough"
        )
        rows = cur.fetchall()
    assert rows, "the seeded -20%/+25% cycle must produce one event"
    trough, confirmation, w_start, w_end, w_days, w_obs, w_complete, basket_obs = rows[0]
    assert confirmation is not None and confirmation > trough
    assert w_days == 95  # the "3M" window is pinned as 95 calendar days
    assert w_start is not None
    assert w_start == (pd.Timestamp(trough) + pd.Timedelta(days=1)).date()
    assert w_end is not None
    # The seeded frame ends 2020-04-04, before trough + 95 days: the window is
    # incomplete and must say so instead of posing as a finished 3M study.
    assert w_complete is False
    assert 60 <= w_obs <= 80
    assert basket_obs and "bank" in basket_obs
    # rule provenance rides in cycle_meta, stamped in the same rebuild
    with db.cursor() as cur:
        cur.execute("SELECT key, value FROM cycle_meta WHERE key LIKE 'trough\\_%'")
        meta = dict(cur.fetchall())
    assert meta["trough_rule_version"] == "1"
    assert "drawdown_from_peak" in meta["trough_rule_thresholds"]
    assert meta["trough_window_days"] == "95"
    assert meta["trough_requires_future_data"] == "true"
    # the read tool exposes the metadata, rule context and per-basket counts
    out = asyncio.run(_fn("cycle_trough_events")())
    row = out["data"]["rows"][0]
    assert row["confirmation"] == str(confirmation)
    assert row["window_complete"] is False
    assert isinstance(row["basket_observations"], dict)
    assert out["data"]["rule"]["trough_rule_version"] == "1"
    assert out["data"]["rule"]["trough_requires_future_data"] == "true"


@needs_db
def test_cycle_yearly_rows_carry_period_metadata(db: Any) -> None:
    from opentrading_mcp.tools import cycle_stats

    _seed_yearly_cycle(db)
    cycle_stats._finalize_compute(db, [])
    with db.cursor() as cur:
        cur.execute(
            "SELECT basket, year, ret, is_partial_year, data_through, period_basis"
            " FROM cycle_yearly ORDER BY year"
        )
        rows = cur.fetchall()
    by_year = {r[1]: r for r in rows if r[0] == "vin"}
    assert 2024 in by_year and 2026 in by_year
    _, _, ret24, partial24, through24, basis24 = by_year[2024]
    assert ret24 == 0.0
    assert partial24 is False
    assert basis24 == "calendar_year"
    assert str(through24) == "2024-12-31"
    _, _, ret26, partial26, through26, basis26 = by_year[2026]
    assert ret26 == 0.0
    assert partial26 is True
    assert basis26 == "year_to_date"
    assert str(through26) == "2026-10-20"
    out = asyncio.run(_fn("cycle_yearly")(basket="vin", year=2026))
    row = out["data"]["rows"][0]
    assert row["is_partial_year"] is True
    assert row["period_basis"] == "year_to_date"
