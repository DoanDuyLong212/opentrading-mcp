"""P5 contract: enriched params for vn.py + vn_ext.py tools (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "market"):
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


async def test_vn_listing_accepts_limit(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    rows = [{"symbol": f"S{i:03d}", "name": f"Name {i}"} for i in range(10)]
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: list(rows))
    fn = _tool_fn("vn_listing")
    env = await fn(limit=3)
    _check_envelope(env, "vn_listing")
    assert env["data"]["count"] == 10
    assert len(env["data"]["symbols"]) == 3


async def test_vn_fundamentals_accepts_report_type():
    import inspect

    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool("vn_fundamentals")
    assert tool is not None
    assert "report_type" in inspect.signature(tool.fn).parameters


async def test_vn_retail_gold_accepts_source(monkeypatch):
    seen: dict[str, Any] = {}

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [{"SJC 1L": 1}]

    class FakeRetail:
        def gold(self, source="sjc", **kwargs):
            seen["source"] = source
            return FakeFrame()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Retail", lambda: FakeRetail())
    fn = _tool_fn("vn_retail_gold")
    env = await fn(source="sjc")
    _check_envelope(env, "vn_retail_gold")
    assert seen["source"] == "sjc"


async def test_vn_index_ohlcv_accepts_interval(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    seen: dict[str, Any] = {}

    def fake_ohlcv(symbol: str = "VNINDEX", count: int = 100, interval: str = "1D"):
        seen.update(symbol=symbol, count=count, interval=interval)
        return [{"t": 1, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}]

    monkeypatch.setattr(vn_p, "index_ohlcv", fake_ohlcv)
    fn = _tool_fn("vn_index_ohlcv")
    env = await fn(symbol="VN30", count=5, interval="1W")
    _check_envelope(env, "vn_index_ohlcv")
    assert seen == {"symbol": "VN30", "count": 5, "interval": "1W"}


async def test_vn_forex_ohlcv_accepts_summary_columns(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    def fake_fx(pair: str = "USDVND", count: int = 30):
        return [{"t": 1, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10.0}]

    monkeypatch.setattr(vn_p, "forex_ohlcv", fake_fx)
    fn = _tool_fn("vn_forex_ohlcv")
    env = await fn(pair="EURUSD", count=5, summary=True)
    _check_envelope(env, "vn_forex_ohlcv")
    assert env["data"]["count"] == 1


async def test_vn_reference_accepts_by_key(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    seen: dict[str, Any] = {}

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [{"symbol": "VCB", "group": "Banks"}]

    class FakeEquity:
        @staticmethod
        def list_by_group(key):
            seen["key"] = key
            return FakeFrame()

        @staticmethod
        def list():
            raise AssertionError("should use list_by_group")

    class FakeRef:
        equity = FakeEquity()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Reference", lambda: FakeRef())
    rows = vn_p.reference_equity(by="group", key="Banks")
    assert seen == {"key": "Banks"}
    assert rows[0]["symbol"] == "VCB"


async def test_vn_company_detail_controls_extras(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    calls: list[str] = []

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [{"symbol": "VCB"}]

    class FakeClient:
        def info(self):
            calls.append("info")
            return FakeFrame()

        def shareholders(self):
            calls.append("shareholders")
            return FakeFrame()

        def officers(self):
            calls.append("officers")
            return FakeFrame()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Company", lambda source, symbol: FakeClient())
    vn_p.company_info("VCB", detail=False)
    assert calls == ["info"]
    vn_p.company_info("VCB", detail=True)
    assert "shareholders" in calls and "officers" in calls


async def test_vn_msn_fx_gold_accepts_symbols_days(monkeypatch):
    import inspect

    from opentrading_mcp.providers import vnstock as vn_p

    sig = inspect.signature(vn_p.msn_fx_gold)
    assert "symbols" in sig.parameters and "days" in sig.parameters
    assert sig.parameters["days"].default == 35


async def test_vn_trades_accepts_board_range(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    seen: dict[str, Any] = {}

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [{"t": 1}]

    class FakeEquity:
        def trades(self, **kwargs):
            seen.update(kwargs)
            return FakeFrame()

    class FakeMarket:
        def equity(self, symbol):
            assert symbol == "VCB"
            return FakeEquity()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Market", lambda: FakeMarket())
    vn_p.equity_trades("VCB", 5, board="HOSE", from_date="2026-01-01", to_date="2026-02-01")
    assert seen.get("board") == "HOSE"
