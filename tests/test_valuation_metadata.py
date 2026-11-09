"""Valuation provenance and safe denominator boundaries."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.server import create_server, register_preset
from opentrading_mcp.tools import compute_financial as cf


async def _valuation(monkeypatch, overview: dict[str, Any], fund: dict[str, Any]):
    async def fake_call(tool, fn, *args, **kwargs):
        if fn is cf.vs_p.overview_trading:
            return overview
        if fn is cf.vn_p.equity_quote_batch:
            return [{"symbol": "FPT", "close_price": 57400}]
        if fn is cf.vs_ratios.equity_fundamentals:
            return fund
        raise AssertionError(fn)

    async def cache_miss(*args):
        return None

    async def cache_write(tool, fingerprint, ttl, data, **kwargs):
        return make_envelope(data, source="test", warnings=kwargs.get("warnings"))

    monkeypatch.setattr(cf, "_call", fake_call)
    monkeypatch.setattr(cf, "cache_lookup", cache_miss)
    monkeypatch.setattr(cf, "cache_store", cache_write)
    server = create_server("scan")
    register_preset(server, "scan")
    return await server._tool_manager.get_tool("valuation_run").fn(symbol="FPT")


@pytest.mark.parametrize(
    "invalid", [float("nan"), float("inf"), -float("inf"), True, False, np.bool_(True)]
)
async def test_invalid_overview_denominators_never_create_multiples(monkeypatch, invalid):
    env = await _valuation(monkeypatch, {"EPS": invalid, "BVPS": invalid}, {})
    assert "per" not in env["data"] and "pb" not in env["data"]
    assert "eps" not in env["data"] and "bvps" not in env["data"]
    assert any("EPS invalid" in warning for warning in env["warnings"])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True, False, np.bool_(False)])
async def test_invalid_fallback_denominators_never_create_multiples(monkeypatch, invalid):
    env = await _valuation(monkeypatch, {}, {"eps": invalid, "bvps": invalid})
    assert "per" not in env["data"] and "pb" not in env["data"]
    assert "eps" not in env["data"] and "bvps" not in env["data"]
    assert any("vnstock fundamentals" in warning for warning in env["warnings"])


async def test_missing_provider_basis_is_explicitly_unverified(monkeypatch):
    env = await _valuation(
        monkeypatch, {}, {"eps": 6021.21, "bvps": 25679.55, "period_label": "2025"}
    )
    data = env["data"]
    assert data["eps_period"] == "2025"
    assert data["eps_frequency"] == "unverified"
    assert data["eps_basis"] == "unverified"
    assert data["bvps_frequency"] == "unverified"
    assert data["per"] == round(57400 / 6021.21, 2)


async def test_finite_subnormal_denominator_cannot_emit_infinite_multiple(monkeypatch):
    env = await _valuation(monkeypatch, {"EPS": 1e-320, "BVPS": 1e-320}, {})
    assert env["data"]["eps"] == 1e-320
    assert "per" not in env["data"] and "pb" not in env["data"]
    assert "EPS positive but quotient is not finite — PER not computed" in env["warnings"]
    assert "BVPS positive but quotient is not finite — PB not computed" in env["warnings"]


@pytest.mark.parametrize("value", [0, -1])
async def test_reported_nonpositive_values_remain_visible_without_multiple(monkeypatch, value):
    env = await _valuation(monkeypatch, {"EPS": value, "BVPS": value}, {})
    data = env["data"]
    assert data["eps"] == value and data["bvps"] == value
    assert "per" not in data and "pb" not in data


async def _valuation_by_period(monkeypatch, by_period: dict[str, Any]):
    seen: list[str] = []

    async def fake_call(tool, fn, *args, **kwargs):
        if fn is cf.vs_p.overview_trading:
            return {}
        if fn is cf.vn_p.equity_quote_batch:
            return [{"symbol": "FPT", "close_price": 50900}]
        if fn is cf.vs_ratios.equity_fundamentals:
            period = args[1]
            seen.append(period)
            got = by_period[period]
            if isinstance(got, Exception):
                raise got
            return got
        raise AssertionError(fn)

    async def cache_miss(*args):
        return None

    async def cache_write(tool, fingerprint, ttl, data, **kwargs):
        return make_envelope(data, source="test", warnings=kwargs.get("warnings"))

    monkeypatch.setattr(cf, "_call", fake_call)
    monkeypatch.setattr(cf, "cache_lookup", cache_miss)
    monkeypatch.setattr(cf, "cache_store", cache_write)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("valuation_run").fn(symbol="FPT")
    return env, seen


QUARTER = {"eps": 6030.0, "bvps": 26100.0, "period_label": "Q3/2026", "frequency": "quarterly",
           "eps_basis": "trailing_four_quarters"}
YEAR = {"eps": 6021.21, "bvps": 25679.55, "period_label": "2025", "frequency": "annual",
        "eps_basis": "trailing_four_quarters"}


async def test_q3_valuation_uses_the_newest_quarter_ttm_eps(monkeypatch):
    env, seen = await _valuation_by_period(monkeypatch, {"quarter": QUARTER, "year": YEAR})
    data = env["data"]
    assert seen == ["quarter"]  # the annual table is not read when the quarter answers
    assert data["eps"] == 6030.0 and data["eps_period"] == "Q3/2026"
    assert data["eps_frequency"] == "quarterly"
    assert data["eps_basis"] == "trailing_four_quarters"
    assert data["per"] == round(50900 / 6030.0, 2)
    assert data["bvps_period"] == "Q3/2026"
    assert "not restated" in data["eps_note"]


async def test_q3_falls_back_to_the_annual_table(monkeypatch):
    from opentrading_mcp.providers.errors import ProviderUnavailable

    empty_quarter = {"eps": None, "bvps": None, "period_label": None}
    env, seen = await _valuation_by_period(monkeypatch, {"quarter": empty_quarter, "year": YEAR})
    assert seen == ["quarter", "year"] and env["data"]["eps_period"] == "2025"

    env, seen = await _valuation_by_period(
        monkeypatch, {"quarter": ProviderUnavailable("vietstock timeout"), "year": YEAR})
    assert seen == ["quarter", "year"] and env["data"]["eps_period"] == "2025"
    assert not any("(quarter) unavailable" in w for w in env["warnings"] or [])
