"""P2 contract: screener catalog + filters + stock_screener (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers import vs_ratios as vsr_mod
from opentrading_mcp.server import create_server, register_all, register_preset


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
    # equality (symbol/exchange)
    out4 = apply_filters(rows, {"symbol": "A"})
    assert [r["symbol"] for r in out4] == ["A"]
    # sector/industry/index non-filterable (not enriched in universe rows) → ignored
    assert len(apply_filters(rows, {"sector": "Bank"})) == 3
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
        return {
            "symbol": symbol,
            "pe": 10.0 if symbol == "VCB" else 30.0,
            "roe": 0.20,
            "eps": 5000.0,
        }

    monkeypatch.setattr(vsr_mod, "equity_fundamentals", fake_ratio)
    prices = {"VCB": 50000.0, "HPG": 250000.0}

    def fake_quotes(symbols):
        return [
            {"symbol": s, "close_price": prices.get(s), "time": "2026-11-18 14:45:00"}
            for s in symbols
        ]

    monkeypatch.setattr(vn_p, "equity_quote_batch", fake_quotes)

    fn = _scan_tool_fn("stock_screener")
    # new-style filters; default pe_basis=current_ttm: VCB 50000/5000 = 10 passes,
    # HPG 250000/5000 = 50 fails its period-end PE of 30 would also fail.
    env = await fn(filters={"pe": [None, 20]}, limit=20)
    _check_envelope(env, "stock_screener")
    assert env["data"]["universe"] == 2
    assert env["data"]["pe_basis"] == "current_ttm"
    assert len(env["data"]["candidates"]) == 1
    assert env["data"]["candidates"][0]["symbol"] == "VCB"
    # backward-compat max_pe/min_roe
    env2 = await fn(max_pe=20, min_roe=0.1, limit=20)
    assert len(env2["data"]["candidates"]) == 1

    # fundamentals failure must not break whole batch
    def boom(symbol: str, period: str = "year"):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(vsr_mod, "equity_fundamentals", boom)
    env3 = await fn(limit=5)
    _check_envelope(env3, "stock_screener")
    assert env3["data"]["universe"] == 2
    assert len(env3["data"]["candidates"]) >= 1


async def test_stock_screener_current_ttm_pe_is_price_over_trailing_eps(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "FPT"}])
    monkeypatch.setattr(
        vsr_mod,
        "equity_fundamentals",
        lambda symbol, period="year": {
            "symbol": symbol,
            "pe": 5.0,  # period-end table PE — must be ignored under current_ttm
            "roe": 0.2,
            "eps": 6000.0,
            "period_label": "2025",
        },
    )
    monkeypatch.setattr(
        vn_p,
        "equity_quote_batch",
        lambda symbols: [
            {"symbol": s, "close_price": 48000.0, "time": "2026-11-18 14:45:00"}
            for s in symbols
        ],
    )
    fn = _scan_tool_fn("stock_screener")
    env = await fn(limit=5)
    _check_envelope(env, "stock_screener")
    assert env["data"]["pe_basis"] == "current_ttm"
    cand = env["data"]["candidates"][0]
    assert cand["pe"] == 8.0  # 48000 / 6000, not the table's 5.0
    assert cand["pe_basis"] == "current_ttm"
    assert cand["pe_as_of"] == "2026-11-18 14:45:00"
    assert cand["fundamentals_period"] == "2025"


async def test_stock_screener_current_ttm_without_price_never_fakes_a_pe(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "FPT"}])
    monkeypatch.setattr(
        vsr_mod,
        "equity_fundamentals",
        lambda symbol, period="year": {"symbol": symbol, "pe": 5.0, "roe": 0.2, "eps": 6000.0},
    )
    monkeypatch.setattr(vn_p, "equity_quote_batch", lambda symbols: [])
    fn = _scan_tool_fn("stock_screener")
    env = await fn(filters={"pe": [None, 20]}, limit=5)
    _check_envelope(env, "stock_screener")
    # No price → no pe → the pe filter has no evaluated conclusion for this symbol.
    assert env["data"]["candidates"] == []
    assert any("current_ttm" in str(w) for w in env["warnings"])


async def test_stock_screener_period_end_basis_keeps_table_pe(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "FPT"}])
    monkeypatch.setattr(
        vsr_mod,
        "equity_fundamentals",
        lambda symbol, period="year": {"symbol": symbol, "pe": 15.91, "roe": 0.2, "eps": 6000.0},
    )
    monkeypatch.setattr(
        vn_p,
        "equity_quote_batch",
        lambda symbols: [{"symbol": s, "close_price": 48000.0} for s in symbols],
    )
    fn = _scan_tool_fn("stock_screener")
    env = await fn(pe_basis="period_end", limit=5)
    _check_envelope(env, "stock_screener")
    assert env["data"]["pe_basis"] == "period_end"
    assert env["data"]["candidates"][0]["pe"] == 15.91
    assert "pe_as_of" not in env["data"]["candidates"][0]


async def test_stock_screener_rejects_unknown_pe_basis():
    fn = _scan_tool_fn("stock_screener")
    env = await fn(pe_basis="tomorrow")
    assert env["availability"] == "unavailable"
    assert any("pe_basis" in str(w) for w in env["warnings"])


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
            def list_by_exchange(exchange=None):  # gen-6 shape (see test_vnstock_signatures)
                return FakeFrame()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Reference", lambda source=None: FakeRef())
    rows = vn_p.reference_equity("HOSE")
    symbols = [r["symbol"] for r in rows]
    # must filter by exchange field, NOT by substring "HOSE" in symbol
    assert "VCB" in symbols
    assert "HOSEMBER" not in symbols


def test_full_surface_contains_scan_tools():
    server = create_server()
    tools = register_all(server)
    names = [t["name"] for t in tools]
    assert "stock_screener" in names
    assert "signals_screener_columns" in names


def test_apply_filters_ignores_unknown_fields():
    from opentrading_mcp.providers.screener import apply_filters

    rows = [
        {"symbol": "A", "pe": 10.0},
        {"symbol": "B", "pe": 30.0},
    ]
    # unknown string-equality form must keep all rows (was: excluded all)
    assert len(apply_filters(rows, {"foo": "bar"})) == 2
    # unknown range form must also keep all rows
    assert len(apply_filters(rows, {"foo": [1, 2]})) == 2
    # unknown mixed with a real filter: only the real one applies
    out = apply_filters(rows, {"foo": "bar", "pe": [None, 20]})
    assert [r["symbol"] for r in out] == ["A"]


def test_price_fields_non_filterable_catalog():
    from opentrading_mcp.providers import screener as sc
    from opentrading_mcp.providers.screener import apply_filters

    for field in ("close", "change_pct", "sector", "industry", "index"):
        assert "non-filterable" in sc.COLUMNS[field]["desc"].lower()
    rows = [{"symbol": "A"}, {"symbol": "B", "close": 50.0}]
    # price filters are ignored (no live price enrichment) → all rows kept
    assert len(apply_filters(rows, {"close": [None, 100]})) == 2
    assert len(apply_filters(rows, {"change_pct": [0, 10]})) == 2


def test_reference_equity_fail_closed_no_exchange_key(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderBadData

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [{"symbol": "VCB"}, {"symbol": "HPG"}]

    class FakeRef:
        class equity:
            @staticmethod
            def list_by_exchange(exchange=None):  # gen-6 shape (see test_vnstock_signatures)
                return FakeFrame()

    import vnstock as _vs

    monkeypatch.setattr(_vs, "Reference", lambda source=None: FakeRef())
    try:
        rows = vn_p.reference_equity("HOSE")
    except ProviderBadData:
        return
    # fail-closed alternative: empty list is acceptable, unfiltered is not
    assert rows == [], "must not return unfiltered rows when no exchange key"


async def test_stock_screener_bounded_enrich_no_valuation_filter(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    fake_universe = [{"symbol": f"S{i:03d}"} for i in range(20)]
    calls: list[str] = []

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: list(fake_universe))

    def fake_ratio(symbol: str, period: str = "year"):
        calls.append(symbol)
        return {"symbol": symbol, "pe": 10.0, "roe": 0.2, "market_cap": 1000.0, "eps": 5000.0}

    monkeypatch.setattr(vsr_mod, "equity_fundamentals", fake_ratio)
    monkeypatch.setattr(
        vn_p,
        "equity_quote_batch",
        lambda symbols: [{"symbol": s, "close_price": 50000.0} for s in symbols],
    )
    fn = _scan_tool_fn("stock_screener")
    # no valuation filter → enrich capped at 10
    env = await fn(limit=5)
    _check_envelope(env, "stock_screener")
    assert len(calls) <= 10, f"unbounded enrich: {len(calls)} calls"
    assert env["data"]["universe"] == 20

    # valuation filter → wider enrich (up to 15, here 20 rows, limit 5 → 15)
    calls.clear()
    env2 = await fn(filters={"pe": [None, 20]}, limit=5)
    assert len(calls) > 10, "valuation filter should enrich beyond the no-filter cap"
    assert len(env2["data"]["candidates"]) >= 1
