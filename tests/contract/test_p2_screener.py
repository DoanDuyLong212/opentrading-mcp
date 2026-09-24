"""P2 contract: screener catalog + filters + stock_screener (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _scan_tool_fn(name: str):
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


def test_columns_catalog_has_pe_roe():
    from opentrading_mcp.providers import screener as sc

    assert hasattr(sc, "COLUMNS")
    for field in ("pe", "roe", "market_cap", "sector", "close", "change_pct"):
        assert field in sc.COLUMNS, f"COLUMNS missing {field!r}"
        entry = sc.COLUMNS[field]
        assert "group" in entry and "desc" in entry, f"{field}: need group+desc"
    groups = {v["group"] for v in sc.COLUMNS.values()}
    for g in ("valuation", "quality", "universe", "price"):
        assert g in groups, f"group {g!r} missing from catalog"


def test_apply_filters_min_max_null():
    from opentrading_mcp.providers.screener import apply_filters

    rows = [
        {"symbol": "A", "pe": 10.0, "roe": 0.20, "sector": "Bank"},
        {"symbol": "B", "pe": 30.0, "roe": 0.05, "sector": "Steel"},
        {"symbol": "C", "pe": None, "roe": 0.30, "sector": "Bank"},
    ]
    # max-only: null unbounded on min side, None values excluded
    out = apply_filters(rows, {"pe": [None, 20]})
    assert [r["symbol"] for r in out] == ["A"]
    # min-only
    out2 = apply_filters(rows, {"roe": [0.15, None]})
    assert sorted(r["symbol"] for r in out2) == ["A", "C"]
    # both bounds
    out3 = apply_filters(rows, {"pe": [5, 15], "roe": [0.1, 0.25]})
    assert [r["symbol"] for r in out3] == ["A"]
    # equality
    out4 = apply_filters(rows, {"sector": "Bank"})
    assert sorted(r["symbol"] for r in out4) == ["A", "C"]
    # empty filters -> all
    assert len(apply_filters(rows, None)) == 3
    assert len(apply_filters(rows, {})) == 3


async def test_signals_screener_columns_tool():
    fn = _scan_tool_fn("signals_screener_columns")
    env = await fn()
    _check_envelope(env, "signals_screener_columns")
    data = env["data"]
    blob = str(data)
    assert "pe" in blob and "roe" in blob
    env2 = await fn(group="valuation")
    assert "pe" in str(env2["data"])
    env3 = await fn(search="roe")
    assert "roe" in str(env3["data"])


async def test_stock_screener_does_not_break(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    fake_universe = [
        {"symbol": "VCB", "name": "Vietcombank"},
        {"symbol": "HPG", "name": "Hoa Phat"},
    ]
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: list(fake_universe))

    def fake_ratio(symbol: str, period: str = "year"):
        return {"symbol": symbol, "pe": 10.0 if symbol == "VCB" else 30.0, "roe": 0.20}

    monkeypatch.setattr(vn_p, "equity_fundamentals", fake_ratio)

    fn = _scan_tool_fn("stock_screener")
    # new-style filters
    env = await fn(filters={"pe": [None, 20]}, limit=20)
    _check_envelope(env, "stock_screener")
    assert env["data"]["universe"] == 2
    assert len(env["data"]["candidates"]) == 1
    assert env["data"]["candidates"][0]["symbol"] == "VCB"
    # backward-compat max_pe/min_roe
    env2 = await fn(max_pe=20, min_roe=0.1, limit=20)
    assert len(env2["data"]["candidates"]) == 1
    # fundamentals failure must not break whole batch
    def boom(symbol: str, period: str = "year"):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(vn_p, "equity_fundamentals", boom)
    env3 = await fn(limit=5)
    _check_envelope(env3, "stock_screener")
    assert env3["data"]["universe"] == 2
    assert len(env3["data"]["candidates"]) >= 1


def test_reference_equity_filters_by_exchange_field(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [
                {"symbol": "VCB", "exchange": "HOSE"},
                {"symbol": "HOSEMBER", "exchange": "HNX"},
            ]

    class FakeRef:
        class equity:
            @staticmethod
            def list():
                return FakeFrame()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Reference", lambda: FakeRef())
    rows = vn_p.reference_equity("HOSE")
    symbols = [r["symbol"] for r in rows]
    # must filter by exchange field, NOT by substring "HOSE" in symbol
    assert "VCB" in symbols
    assert "HOSEMBER" not in symbols


def test_scan_preset_cap():
    server = create_server("scan")
    tools = register_preset(server, "scan")
    assert len(tools) <= 50, f"scan preset has {len(tools)} tools over cap"
    names = [t["name"] for t in tools]
    assert "stock_screener" in names
    assert "signals_screener_columns" in names
