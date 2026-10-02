"""P5 contract: enriched params for market/dnse/yf/brief/web tools (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


async def test_market_snapshot_records_as_of(monkeypatch):
    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0):
        return [{"symbol": "VCB", "close": 100.0}]

    import opentrading_mcp.tools.market as market_mod

    monkeypatch.setattr(market_mod, "run_blocking", fake_rb)
    fn = _tool_fn("market_snapshot", "market")
    env = await fn(as_of="2026-09-24T09:00:00+07:00")
    _check_envelope(env, "market_snapshot")
    assert env["data"]["requested_as_of"] == "2026-09-24T09:00:00+07:00"


async def test_symbol_lookup_limit(monkeypatch):
    import opentrading_mcp.tools.market as market_mod

    rows = [{"symbol": f"S{i}", "name": f"Name {i}"} for i in range(10)]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0):
        return rows

    monkeypatch.setattr(market_mod, "run_blocking", fake_rb)
    fn = _tool_fn("symbol_lookup", "market")
    env = await fn(query="S", limit=4)
    _check_envelope(env, "symbol_lookup")
    assert len(env["data"]["hits"]) == 4


async def test_breadth_scan_exchange_filter(monkeypatch):
    import opentrading_mcp.tools.market as market_mod

    rows = [
        {"code": "VCB", "change": 1.0, "exchange": "HOSE"},
        {"code": "ABC", "change": -1.0, "exchange": "HNX"},
    ]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0):
        return rows

    monkeypatch.setattr(market_mod, "run_blocking", fake_rb)
    fn = _tool_fn("breadth_scan", "market")
    env = await fn(exchange="HOSE")
    _check_envelope(env, "breadth_scan")
    assert env["data"]["advancers"] == 1
    assert env["data"]["decliners"] == 0


async def test_dnse_indices_accepts_symbols(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_mod

    seen: dict[str, Any] = {}

    def fake_snap(symbols):
        seen["symbols"] = symbols
        return {"ok": True}

    monkeypatch.setattr(dnse_mod, "ws_snapshot", fake_snap)
    fn = _tool_fn("dnse_indices", "market")
    env = await fn(symbols=["VN30"])
    _check_envelope(env, "dnse_indices")
    assert seen == {"symbols": ["VN30"]}


async def test_dnse_vn30f1m_live_bars_slice(monkeypatch):
    import opentrading_mcp.tools.dnse_ext as ext_mod

    bars = [{"t": i * 900, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10} for i in range(10)]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return bars

    monkeypatch.setattr(ext_mod, "_call", fake_call)
    fn = _tool_fn("dnse_vn30f1m_live", "market")
    env = await fn(bars=3)
    _check_envelope(env, "dnse_vn30f1m_live")
    assert len(env["data"]["bars"]) == 3


async def test_dnse_working_dates_year_filter(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_mod

    def fake_dates():
        return [{"date": "2026-01-05"}, {"date": "2025-12-31"}]

    monkeypatch.setattr(dnse_mod, "working_dates", fake_dates)
    fn = _tool_fn("dnse_working_dates", "market")
    env = await fn(year=2026)
    _check_envelope(env, "dnse_working_dates")
    assert env["data"]["dates"] == [{"date": "2026-01-05"}]


async def test_dnse_ohlc_accepts_to_date_page_size(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_mod

    seen: dict[str, Any] = {}

    def fake_ohlcv(
        symbol: str = "VN30F1M",
        bar_type: str = "derivative",
        resolution: int = 15,
        from_date: str = "2018-08-01",
        to_date: str | None = None,
        page_size: int = 10000,
    ):
        seen.update(symbol=symbol, to_date=to_date, page_size=page_size)
        return []

    monkeypatch.setattr(dnse_mod, "ohlc_history", fake_ohlcv)
    fn = _tool_fn("dnse_ohlc_history", "market")
    env = await fn(to_date="2026-09-01", page_size=500)
    _check_envelope(env, "dnse_ohlc_history")
    assert seen["to_date"] == "2026-09-01"
    assert seen["page_size"] == 500


async def test_dnse_latest_trade_summary_columns(monkeypatch):
    import opentrading_mcp.tools.dnse_tools as tools_mod

    rows = [
        {"symbol": "VCB", "matchPrice": 100.0, "totalVolumeTraded": 50},
        {"symbol": "HPG", "matchPrice": 200.0, "totalVolumeTraded": 60},
    ]

    async def fake_rb(fn: Any, tool: str, timeout_secs: float = 60.0):
        return rows

    monkeypatch.setattr(tools_mod, "run_blocking", fake_rb)
    fn = _tool_fn("dnse_latest_trade", "market")
    env = await fn(symbols=["VCB", "HPG"], summary=True)
    _check_envelope(env, "dnse_latest_trade")
    assert env["data"]["count"] == 2
    env2 = await fn(symbols=["VCB"], columns=["symbol", "matchPrice"])
    assert env2["data"]["trades"] == [
        {"symbol": "VCB", "matchPrice": 100.0},
        {"symbol": "HPG", "matchPrice": 200.0},
    ]


async def test_yf_global_indices_tickers_subset(monkeypatch):
    from opentrading_mcp.providers import yfinance as yf_p

    seen: dict[str, Any] = {}

    def fake_batch(tickers: list[str], period: str = "2d", interval: str = "1d"):
        seen.update(tickers=tickers, period=period, interval=interval)
        return [{"ticker": t} for t in tickers]

    monkeypatch.setattr(yf_p, "batch_last", fake_batch)
    fn = _tool_fn("yf_global_indices", "market")
    env = await fn(tickers=["^GSPC"], period="5d", interval="1d")
    _check_envelope(env, "yf_global_indices")
    assert seen == {"tickers": ["^GSPC"], "period": "5d", "interval": "1d"}


async def test_yf_oracle_groups_filter(monkeypatch):
    from opentrading_mcp.providers import yfinance as yf_p

    def fake_oracle(groups: list[str] | None = None):
        data = {"crypto": [1], "energy": [2]}
        if groups is None:
            return data
        wanted = {g.lower() for g in groups}
        return {k: v for k, v in data.items() if k.lower() in wanted}

    monkeypatch.setattr(yf_p, "oracle_markets", fake_oracle)
    fn = _tool_fn("yf_oracle_markets", "market")
    env = await fn(groups=["energy"])
    _check_envelope(env, "yf_oracle_markets")
    assert env["data"] == {"energy": [2]}


async def test_yf_mega_top_n(monkeypatch):
    from opentrading_mcp.providers import yfinance as yf_p

    def fake_mega(top_n: int = 15):
        assert top_n == 3
        return {"leaders": list(range(top_n))}

    monkeypatch.setattr(yf_p, "mega_flows", fake_mega)
    fn = _tool_fn("yf_mega_flows", "market")
    env = await fn(top_n=3)
    _check_envelope(env, "yf_mega_flows")
    assert env["data"]["leaders"] == [0, 1, 2]


async def test_brief_build_date_recorded(monkeypatch):
    import opentrading_mcp.tools.brief as brief_mod

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        if tool == "p":
            return None
        if tool == "n":
            return []
        return []

    monkeypatch.setattr(brief_mod, "_call", fake_call)
    fn = _tool_fn("brief_build", "brief")
    env = await fn(scope="vn", date="2026-09-24")
    _check_envelope(env, "brief_build")
    assert env["data"]["date"] == "2026-09-24"


async def test_news_market_sources_gdelt(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        if tool == "g":
            return {"articles": [{"title": "g"}]}
        raise AssertionError("vietstock must not be called")

    import opentrading_mcp.tools.brief as brief_mod

    monkeypatch.setattr(brief_mod, "_call", fake_call)

    def fake_gdelt(query: str = "x", max_records: int = 20):
        raise AssertionError("must go through _call router")

    monkeypatch.setattr(intel_p, "gdelt_events", fake_gdelt)
    fn = _tool_fn("news_market", "brief")
    env = await fn(limit=5, sources="gdelt")
    _check_envelope(env, "news_market")
    assert env["data"]["articles"] == [{"title": "g"}]


async def test_economic_calendar_limit(monkeypatch):
    import opentrading_mcp.tools.brief as brief_mod

    cats = [{"CategoryID": i, "CategoryName": f"C{i}", "HasData": True} for i in range(10)]

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return cats

    monkeypatch.setattr(brief_mod, "_call", fake_call)
    fn = _tool_fn("economic_calendar", "brief")
    env = await fn(limit=4)
    _check_envelope(env, "economic_calendar")
    assert len(env["data"]["series"]) == 4


async def test_corporate_calendar_limit(monkeypatch):
    import opentrading_mcp.tools.brief as brief_mod

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return [{"title": f"D{i}"} for i in range(10)]

    monkeypatch.setattr(brief_mod, "_call", fake_call)
    fn = _tool_fn("corporate_calendar", "brief")
    env = await fn(limit=3)
    _check_envelope(env, "corporate_calendar")
    assert len(env["data"]["docs"]) == 3


async def test_web_search_context_max_chars(monkeypatch):
    from opentrading_mcp.providers import websearch as ws_p

    monkeypatch.setattr(ws_p, "web_search_available", lambda: True)

    seen: dict[str, Any] = {}

    def fake_search(
        query: str,
        num_results: int = 8,
        livecrawl: str = "fallback",
        search_type: str = "auto",
        context_max_chars: int | None = None,
    ):
        seen.update(query=query, context_max_chars=context_max_chars)
        return {"output": "ok"}

    monkeypatch.setattr(ws_p, "search", fake_search)
    fn = _tool_fn("web_search", "intel")
    env = await fn(query="FED", context_max_chars=500)
    _check_envelope(env, "web_search")
    assert seen["context_max_chars"] == 500
