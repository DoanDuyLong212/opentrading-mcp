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


async def test_full_surface_contains_corp_tools():
    from opentrading_mcp.server import register_all

    server = create_server()
    tools = register_all(server)
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


async def test_futures_basis_falls_back_to_ohlc(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import vnstock as vn_p

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        target = getattr(fn, "func", None)
        if target is dnse_p.latest_trade:
            return [{"symbol": "VN30F1M", "trades": []}]
        if target is vn_p.index_ohlcv:
            return [
                {
                    "time": "2026-09-30",
                    "open": 1790.0,
                    "high": 1805.0,
                    "low": 1785.0,
                    "close": 1800.0,
                    "volume": 1.0,
                }
            ]
        if target is dnse_p.ohlc_history:
            return [{"t": 1, "o": 1805.0, "h": 1812.0, "l": 1804.0, "c": 1810.0, "v": 9}]
        raise AssertionError(f"unexpected upstream {target}")

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("futures_basis")
    env = await fn()
    assert env["availability"] == "available"
    assert env["data"]["basis"] == 10.0
    assert env["data"]["spot"] == 1800.0


async def test_is_macro_title_keywords():
    from opentrading_mcp.providers.vn_public import is_macro_title

    assert is_macro_title("Nhận định vĩ mô quý 3: GDP tăng 7%") in ("GDP", "VI MO")
    assert is_macro_title("Dự báo CPI tháng 10 và lãi suất điều hành") is not None
    assert is_macro_title("VCB: Khuyến nghị MUA giá 75,000") is None
    assert is_macro_title("Phân tích kỹ thuật VNINDEX") is None


async def test_analyst_consensus_macro_mode(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "title": "Vĩ mô tháng 10: CPI hạ nhiệt, kỳ vọng giảm lãi suất",
                "source": "DSC",
                "date": "02/10/2026",
                "url": "https://x",
                "symbol": None,
                "rating": None,
                "target": None,
                "macro_topic": "CPI",
            }
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    from tests.contract.test_p6_corp2 import _tool_fn as _tf

    fn = _tf("analyst_consensus")
    env = await fn(report_type="macro")
    assert env["data"]["report_type"] == "macro"
    assert env["data"]["reports"][0]["macro_topic"] == "CPI"


async def test_analyst_consensus_page_gt1_empty_with_warning(monkeypatch):
    async def boom(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        raise AssertionError("provider must not be called for page>1")

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", boom)
    fn = _tool_fn("analyst_consensus")
    env = await fn(page=2)
    _check_envelope(env, "analyst_consensus")
    assert env["data"]["reports"] == []
    assert env["data"]["page"] == 2
    assert env["data"]["has_more"] is False
    assert any("pagination" in w for w in env["warnings"])


async def test_analyst_consensus_page_clamped(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return []

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("analyst_consensus")
    env = await fn(page=0)
    assert env["data"]["page"] == 1
    assert env["data"]["reports"] == []


async def test_analyst_consensus_days_filter(monkeypatch):
    import datetime

    today = datetime.date.today()
    in_range = today.strftime("%d/%m/%Y")
    old = (today - datetime.timedelta(days=90)).strftime("%d/%m/%Y")

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "title": "AAA: Khuyến nghị MUA với giá mục tiêu 10,000 đồng/cổ phiếu",
                "source": None,
                "date": in_range,
                "url": "https://x/1",
                "symbol": "AAA",
                "rating": "MUA",
                "target": 10000.0,
            },
            {
                "title": "BBB: Khuyến nghị MUA với giá mục tiêu 20,000 đồng/cổ phiếu",
                "source": None,
                "date": old,
                "url": "https://x/2",
                "symbol": "BBB",
                "rating": "MUA",
                "target": 20000.0,
            },
            {
                "title": "CCC: Khuyến nghị MUA với giá mục tiêu 30,000 đồng/cổ phiếu",
                "source": None,
                "date": None,
                "url": "https://x/3",
                "symbol": "CCC",
                "rating": "MUA",
                "target": 30000.0,
            },
        ]

    import opentrading_mcp.tools.corp as corp_mod

    monkeypatch.setattr(corp_mod, "run_blocking", fake_block)
    fn = _tool_fn("analyst_consensus")
    env = await fn(days=60)
    _check_envelope(env, "analyst_consensus")
    syms = [r["symbol"] for r in env["data"]["reports"]]
    assert "AAA" in syms
    assert "BBB" not in syms
    assert "CCC" in syms
    ccc = next(r for r in env["data"]["reports"] if r["symbol"] == "CCC")
    assert ccc["date_uncertain"] is True
    assert env["data"]["days"] == 60
    assert env["data"]["cutoff"] is not None
    assert any("date_uncertain" in w for w in env["warnings"])


def test_analyst_consensus_docstring_has_harness_recipe():
    from tests.contract.test_p6_corp2 import _tool_fn as _tf

    fn = _tf("analyst_consensus")
    doc = fn.__doc__ or ""
    for marker in ("Nguồn:", "Tải về", "edocs", "Max 3"):
        assert marker in doc, f"docstring missing harness marker {marker!r}"


def test_provider_analyst_reports_page_gt1_empty():
    from opentrading_mcp.providers import vn_public as pub_p

    assert pub_p.analyst_reports(10, "equity", page=2) == []
