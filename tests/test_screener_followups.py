"""Screener sau review 24/10: P/E âm và khoảng lọc rỗng (#44 mục 1)."""

from __future__ import annotations

import pytest


def test_negative_pe_does_not_pass_an_upper_bound():
    from opentrading_mcp.providers.screener import apply_filters

    rows = [{"symbol": "NVL", "pe": -3.1}, {"symbol": "FPT", "pe": 9.5}, {"symbol": "X", "pe": 0.0}]
    assert [r["symbol"] for r in apply_filters(rows, {"pe": [None, 10]})] == ["FPT"]
    # an explicit lower bound is the caller's choice: no positivity rule
    assert [r["symbol"] for r in apply_filters(rows, {"pe": [-5, None]})] == ["NVL", "FPT", "X"]
    assert [r["symbol"] for r in apply_filters(rows, {"pe": [-5, 10]})] == ["NVL", "FPT", "X"]


async def test_empty_range_is_not_a_required_metric(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "AAA"}, {"symbol": "BBB"}])
    monkeypatch.setattr(
        vn_p, "equity_fundamentals",
        lambda symbol, period="year": {"symbol": symbol, "roe": 0.2, "period_label": "2025"},
    )
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"pe": [None, None]}, limit=5
    )
    assert env["data"]["filters"] == {}
    assert not any("pe missing" in w for w in env["warnings"])
    assert [c["symbol"] for c in env["data"]["candidates"]] == ["AAA", "BBB"]


# --- #44 mục 4: nhánh dữ liệu kiểu cũ không trả NaN/inf ------------------------------


def test_legacy_ratio_paths_skip_non_finite(monkeypatch):
    import sys
    import types

    import pandas as pd

    from opentrading_mcp.providers import vnstock as vn_p

    frame = pd.DataFrame({"P/E": [12.0, float("inf")], "ROE": [0.18, 0.2]})
    assert vn_p._pick_ratio_number(frame, "pe") is None  # newest is inf: not a value
    assert vn_p._pick_ratio_number(frame, "roe") == 0.2

    class _Equity:
        def ratio(self, period: str = "year"):
            return {"pe": float("nan"), "roe": 0.15, "market_cap": 1000}

    fundamental = types.SimpleNamespace(equity=lambda s: _Equity())
    fake = types.SimpleNamespace(Fundamental=lambda: fundamental)
    monkeypatch.setitem(sys.modules, "vnstock", fake)
    out = vn_p.equity_fundamentals("AAA")
    assert out["pe"] is None and out["roe"] == 0.15
    assert out["market_cap"] == 1000
    assert out["market_cap_status"] == "unverified_unit_time_basis"


# --- #44 mục 5: valuation_run hiển thị EPS/BVPS bằng 0 -------------------------------


async def test_valuation_run_echoes_a_reported_zero(monkeypatch):
    from typing import Any

    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if fn is comp_fin.vn_p.equity_quote_batch:
            return [{"symbol": "AAA", "close_price": 10000}]
        if fn is comp_fin.vn_p.equity_fundamentals:
            return {"eps": 0.0, "bvps": 8000.0, "period_label": "2025"}
        return {"data": []}

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("valuation_run").fn(symbol="AAA")
    data = env["data"]
    assert data["eps"] == 0.0 and "per" not in data  # 0 shown, PER not computed
    assert data["pb"] == 1.25


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), "nan", "inf", True, False]
)
@pytest.mark.parametrize("condition", [[0, 20], 1])
def test_filter_numeric_boundary_rejects_invalid_values(value, condition):
    from opentrading_mcp.providers.screener import apply_filters

    assert apply_filters([{"roe": value}], {"roe": condition}) == []
    assert apply_filters([{"roe": 0}], {"roe": [0, 20]}) == [{"roe": 0}]


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), "nan", "inf", True, False, 0.0]
)
async def test_screener_finite_coverage_matches_filter_boundary(monkeypatch, value):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def fake_run(fn, tool, **kwargs):
        return fn()

    monkeypatch.setattr(scan, "run_blocking", fake_run)
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "AAA"}])
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"roe": value})
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(filters={"roe": [0, 1]})
    valid = value == 0.0 and not isinstance(value, bool)
    assert env["data"]["coverage"]["evaluated"] == int(valid)
    assert len(env["data"]["candidates"]) == int(valid)
    if not valid:
        assert env["availability"] == "partial"


@pytest.mark.parametrize("condition", [None, [None, None]])
@pytest.mark.parametrize("shortcut", [False, True])
async def test_noop_filters_normalized_before_shortcuts_and_coverage(
    monkeypatch, condition, shortcut
):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def fake_run(fn, tool, **kwargs):
        return fn()

    monkeypatch.setattr(scan, "run_blocking", fake_run)
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "AAA"}])
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"roe": 0.0})
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"pe": condition, "roe": condition}, min_roe=0.0 if shortcut else None
    )
    assert env["data"]["filters"] == ({"roe": [0.0, None]} if shortcut else {})
    coverage = env["data"]["coverage"]
    assert coverage["stage"] == ("fundamentals" if shortcut else "local")
    assert coverage["evaluated"] == 1
    assert len(env["data"]["candidates"]) == 1
    assert not any("pe missing" in w for w in env["warnings"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"),
                                 "nan", "inf", "not-a-number", True, False])
@pytest.mark.parametrize("field,bound", [("roe", 0), ("roe", 1),
                                          ("market_cap", 0), ("pe", 1)])
def test_direct_range_rejects_invalid_bound_even_without_rows(bad, field, bound):
    from opentrading_mcp.providers.screener import apply_filters

    condition = [0, 20]
    condition[bound] = bad
    with pytest.raises(ValueError, match=field):
        apply_filters([], {field: condition})


@pytest.mark.parametrize("condition", [[2, 1], [1], [1, 2, 3]])
def test_direct_range_rejects_inversion_and_shape(condition):
    from opentrading_mcp.providers.screener import apply_filters

    with pytest.raises(ValueError, match="roe"):
        apply_filters([], {"roe": condition})


def test_explicit_zero_negative_and_noop_ranges():
    from opentrading_mcp.providers.screener import apply_filters, normalize_filters

    rows = [{"roe": -1}, {"roe": 0}, {"roe": 1}]
    assert apply_filters(rows, {"roe": [-1, 0]}) == rows[:2]
    assert apply_filters(rows, {"roe": [None, None]}) == rows
    assert normalize_filters({"roe": None, "pe": [None, None]}) == {}
    assert apply_filters([{"pe": -2}, {"pe": 2}], {"pe": [None, 3]}) == [{"pe": 2}]
    assert apply_filters([{"market_cap": 1000}], {"market_cap": [500, 1500]}) == [
        {"market_cap": 1000}
    ]


def test_nonfilterable_price_fields_ignore_invalid_numeric_conditions():
    from opentrading_mcp.providers.screener import apply_filters, normalize_filters

    rows = [{"symbol": "AAA"}, {"symbol": "BBB", "close": 50}]
    ignored = {"close": [2, 1], "change_pct": [float("nan"), float("inf")]}
    assert normalize_filters(ignored) == {}
    assert apply_filters(rows, ignored) == rows


@pytest.mark.parametrize("kwargs,field", [
    ({"filters": {"roe": ["nan", 1]}}, "roe"),
    ({"filters": {"roe": [0, float("inf")]}}, "roe"),
    ({"filters": {"market_cap": [2, 1]}}, "market_cap"),
    ({"filters": {"pe": [True, 10]}}, "pe"),
    ({"max_pe": "nan"}, "max_pe"),
    ({"min_roe": False}, "min_roe"),
    ({"filters": {"pe": [0, 10]}, "max_pe": float("nan")}, "max_pe"),
])
async def test_invalid_filter_fails_before_cache_and_listing(monkeypatch, kwargs, field):
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def forbidden(*args, **kwargs):
        pytest.fail("invalid filter reached cache or provider")

    monkeypatch.setattr(scan, "cache_lookup", forbidden)
    monkeypatch.setattr(scan, "run_blocking", forbidden)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(**kwargs)
    assert env["availability"] == "unavailable"
    assert field in env["warnings"][0]


async def test_market_cap_missing_has_no_evaluated_conclusion_and_cap_is_visible(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def fake_run(fn, tool, **kwargs):
        return fn()

    async def fake_lookup(*args):
        return None

    async def fake_store(tool, fingerprint, ttl, data, **kwargs):
        from opentrading_mcp.schemas import make_envelope

        return make_envelope(data, **kwargs)

    monkeypatch.setattr(scan, "run_blocking", fake_run)
    monkeypatch.setattr(scan, "cache_lookup", fake_lookup)
    monkeypatch.setattr(scan, "cache_store", fake_store)
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [
        {"symbol": f"S{i:03d}"} for i in range(35)
    ])
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {
        "symbol": symbol, "pe": 10, "roe": 0.2, "market_cap": None,
    })
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"market_cap": [0, None]}, limit=20,
    )
    coverage = env["data"]["coverage"]
    assert coverage["fundamentals"] == {
        "limit": 30, "attempted": 30, "metric_available": {"market_cap": 0},
        "unsupported_metrics": ["market_cap"],
    }
    assert coverage["eligible"] == 35
    assert coverage["attempted"] == 30
    assert coverage["evaluated"] == 0
    assert env["availability"] == "partial"
    assert not env["data"]["candidates"]
    assert any("market_cap unavailable" in w for w in env["warnings"])
    assert any("enrichment cap 30" in w for w in env["warnings"])


async def test_market_cap_legacy_value_is_not_evaluated_without_basis(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def fake_run(fn, tool, **kwargs):
        return fn()

    async def fake_lookup(*args):
        return None

    async def fake_store(tool, fingerprint, ttl, data, **kwargs):
        from opentrading_mcp.schemas import make_envelope

        return make_envelope(data, **kwargs)

    monkeypatch.setattr(scan, "run_blocking", fake_run)
    monkeypatch.setattr(scan, "cache_lookup", fake_lookup)
    monkeypatch.setattr(scan, "cache_store", fake_store)
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "AAA"}])
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {
        "symbol": symbol, "market_cap": 1000,
    })
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"market_cap": [500, 1500]}, limit=1,
    )
    assert env["data"]["coverage"]["evaluated"] == 0
    assert env["data"]["coverage"]["fundamentals"]["metric_available"] == {
        "market_cap": 0,
    }
    assert env["data"]["coverage"]["fundamentals"]["unsupported_metrics"] == [
        "market_cap"
    ]
    assert env["availability"] == "partial"
    assert not env["data"]["candidates"]
    assert any("unit/as-of/shares basis unverified" in w for w in env["warnings"])


async def test_nonfilterable_invalid_price_condition_does_not_block_tool(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def fake_run(fn, tool, **kwargs):
        return fn()

    async def fake_lookup(*args):
        return None

    async def fake_store(tool, fingerprint, ttl, data, **kwargs):
        from opentrading_mcp.schemas import make_envelope

        return make_envelope(data, **kwargs)

    monkeypatch.setattr(scan, "run_blocking", fake_run)
    monkeypatch.setattr(scan, "cache_lookup", fake_lookup)
    monkeypatch.setattr(scan, "cache_store", fake_store)
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [{"symbol": "AAA"}])
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {"symbol": symbol})
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"close": [2, 1], "change_pct": [float("nan"), float("inf")]},
    )
    assert env["data"]["filters"] == {}
    assert env["data"]["coverage"]["evaluated"] == 1
    assert [row["symbol"] for row in env["data"]["candidates"]] == ["AAA"]


async def test_enrichment_cap_marks_partial_even_when_first_30_valid(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import scan

    async def fake_run(fn, tool, **kwargs):
        return fn()

    async def fake_lookup(*args):
        return None

    async def fake_store(tool, fingerprint, ttl, data, **kwargs):
        from opentrading_mcp.schemas import make_envelope

        return make_envelope(data, **kwargs)

    monkeypatch.setattr(scan, "run_blocking", fake_run)
    monkeypatch.setattr(scan, "cache_lookup", fake_lookup)
    monkeypatch.setattr(scan, "cache_store", fake_store)
    monkeypatch.setattr(vn_p, "listing_symbols", lambda: [
        {"symbol": f"S{i:03d}"} for i in range(35)
    ])
    monkeypatch.setattr(vn_p, "equity_fundamentals", lambda symbol: {
        "symbol": symbol, "pe": 10,
    })
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_screener").fn(
        filters={"pe": [None, 20]}, limit=20,
    )
    assert env["availability"] == "partial"
    assert env["data"]["coverage"]["evaluated"] == 30
    assert env["data"]["coverage"]["eligible"] == 35
    assert any("enrichment cap 30" in w for w in env["warnings"])


@pytest.mark.parametrize(
    "eps,bvps,reason",
    [(0, 0, "nonpositive"), (-1, -2, "nonpositive"), (None, None, "missing from both sources")],
)
async def test_valuation_warning_distinguishes_missing_from_nonpositive(
    monkeypatch, eps, bvps, reason
):
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool, fn, *args, **kwargs):
        if fn is comp_fin.vn_p.equity_quote_batch:
            return [{"close_price": 10000}]
        return {"eps": eps, "bvps": bvps}

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("valuation_run").fn(symbol="AAA")
    assert any(f"EPS {reason}" in warning for warning in env["warnings"])
    assert any(f"BVPS {reason}" in warning for warning in env["warnings"])
    assert "per" not in env["data"] and "pb" not in env["data"]
    if eps is not None:
        assert env["data"]["eps"] == eps and env["data"]["bvps"] == bvps


@pytest.mark.parametrize("value", [True, False])
def test_dataframe_boolean_metrics_are_not_financial_numbers(monkeypatch, value):
    import sys
    import types

    import pandas as pd

    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.screener import apply_filters

    # Boolean dtype yields a NumPy scalar from .iloc, not Python bool.
    frame = pd.DataFrame({"pe": [value]})
    assert vn_p._pick_ratio_number(frame, "pe") is None
    assert apply_filters([{"roe": frame["pe"].iloc[0]}], {"roe": [0, 2]}) == []
    long = pd.DataFrame([{"item_id": "roe", "2025": value, "2024": value}])
    assert vn_p._long_ratio_table(long)[1][0]["values"] == {"2025": None, "2024": None}
    equity = types.SimpleNamespace(ratio=lambda **kwargs: {"pe": value})
    fake = types.SimpleNamespace(Fundamental=lambda: types.SimpleNamespace(equity=lambda _: equity))
    monkeypatch.setitem(sys.modules, "vnstock", fake)
    assert vn_p.equity_fundamentals("AAA")["pe"] is None
