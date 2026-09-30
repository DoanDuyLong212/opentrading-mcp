"""P6 contract: corp2 + brief2 tools (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "scan"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"


async def test_event_calendar_dividends(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "event_id": 1,
                "code": "VCB",
                "note": "Trả cổ tức 450 đồng/CP",
                "ex_date": "2026-07-23",
                "record_date": "2026-07-24",
                "file_url": "https://static2.vietstock.vn/x.pdf",
            }
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("event_calendar_vn")
    env = await fn(event="dividends", symbol="VCB")
    _check_envelope(env, "event_calendar_vn")
    row = env["data"]["events"][0]
    assert row["code"] == "VCB"
    assert row["ex_date"].startswith("2026-07-2")


async def test_block_trades_pt_split(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "date": "2026-09-28",
                "close": 58400,
                "mt_vol": 973100,
                "mt_val": 56820140000,
                "pt_vol": 100000,
                "pt_val": 5840000000,
            }
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("block_trades")
    env = await fn(symbol="VCB")
    _check_envelope(env, "block_trades")
    day = env["data"]["days"][0]
    assert day["pt_vol"] == 100000
    assert day["pt_pct"] > 9.0
    assert env["data"]["totals"]["pt_val"] == 5840000000


async def test_analyst_consensus_parses_title(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "title": "VCB: Khuyến nghị MUA với giá mục tiêu 75,000 đồng/cổ phiếu",
                "source": "DSC",
                "date": "26/09/2026",
                "url": "https://x",
                "symbol": "VCB",
                "rating": "MUA",
                "target": 75000.0,
            }
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("analyst_consensus")
    env = await fn(symbol="VCB")
    _check_envelope(env, "analyst_consensus")
    row = env["data"]["reports"][0]
    assert row["rating"] == "MUA"
    assert row["target"] == 75000.0


async def test_ipo_calendar_empty_ok(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return {"auctions": [], "note": "no upcoming auctions"}

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("ipo_calendar_vn")
    env = await fn()
    _check_envelope(env, "ipo_calendar_vn")
    assert env["data"]["auctions"] == []


async def test_futures_basis_no_oi_claim(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import vnstock as vn_p

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        target = getattr(fn, "func", None)
        if target is dnse_p.latest_trade:
            return [{"symbol": "VN30F1M", "price": 1810.0}]
        if target is vn_p.index_ohlcv:
            return [
                {"t": "2026-09-30", "o": 1790.0, "h": 1805.0, "l": 1785.0, "c": 1800.0, "v": 1.0}
            ]
        raise AssertionError(f"unexpected upstream {target}")

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("futures_basis")
    env = await fn()
    _check_envelope(env, "futures_basis")
    assert env["data"]["basis"] == 10.0
    assert "open_interest" not in env["data"]


async def test_sbv_rates_structure(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return {
            "policy": [{"name": "Tái cấp vốn", "value": "4.50%"}],
            "interbank": [],
            "as_of": "28/09/2026",
        }

    import opentrading_mcp.tools.brief as brief_mod

    monkeypatch.setattr(brief_mod, "run_blocking", fake_block)
    server = create_server("brief")
    register_preset(server, "brief")
    tool = server._tool_manager.get_tool("sbv_rates")
    assert tool is not None
    env = await tool.fn()
    _check_envelope(env, "sbv_rates")
    assert env["data"]["policy"][0]["value"] == "4.50%"


async def test_macro_events_vn_lists_releases(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "indicator": "CPI tháng 8",
                "reference": "08/2026",
                "published": "03/09/2026",
                "next": "06/10/2026",
            }
        ]

    import opentrading_mcp.tools.brief as brief_mod

    monkeypatch.setattr(brief_mod, "run_blocking", fake_block)
    server = create_server("brief")
    register_preset(server, "brief")
    tool = server._tool_manager.get_tool("macro_events_vn")
    assert tool is not None
    env = await tool.fn()
    _check_envelope(env, "macro_events_vn")
    assert env["data"]["releases"][0]["next"] == "06/10/2026"


async def test_scan_preset_counts_under_cap():
    server = create_server("scan")
    tools = register_preset(server, "scan")
    assert len(tools) <= 60
    names = {t["name"] for t in tools}
    assert {
        "event_calendar_vn",
        "block_trades",
        "analyst_consensus",
        "ipo_calendar_vn",
        "futures_basis",
    } <= names


def test_ms_date_parses_dotnet_json():
    from opentrading_mcp.providers import vietstock as vs_p

    assert vs_p._ms_date("/Date(1784739600000)/") == "2026-07-23"
    assert vs_p._ms_date("2026-09-30") == "2026-09-30"
    assert vs_p._ms_date(None) is None


def test_consensus_title_parser():
    from opentrading_mcp.providers import vn_public as pub_p

    parsed = pub_p._parse_consensus_title(
        "VCB: Khuyến nghị MUA với giá mục tiêu 75,000 đồng/cổ phiếu"
    )
    assert parsed == {"symbol": "VCB", "rating": "MUA", "target": 75000.0}


async def test_futures_basis_auth_missing_is_unavailable(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers.errors import ProviderAuthMissing

    def boom(symbols: list[str]) -> list[dict[str, Any]]:
        raise ProviderAuthMissing("DNSE_API_KEY/DNSE_SECRET are not set")

    monkeypatch.setattr(dnse_p, "latest_trade", boom)
    fn = _tool_fn("futures_basis")
    env = await fn()
    assert env["availability"] == "unavailable"
