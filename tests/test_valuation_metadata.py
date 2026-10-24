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
        if fn is cf.vn_p.equity_fundamentals:
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
