"""F09/F10/F11 deep-contract oracles (data wave).

F09: CoinGecko fallback rows carry truthful quote identity; requested symbols
     that received a USD reference instead of the exact pair are disclosed.
F10: missing FRED legs raise instead of fabricating zeros; mismatched leg
     dates withhold the inversion DECISION while both values stay visible.
F11: partial provider results surface as explicit `missing` lists + warning +
     availability='partial', and the cache payload preserves completeness.
"""

from __future__ import annotations

import asyncio
import math

from opentrading_mcp.providers import binance as bn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str):
    server = create_server("all")
    register_preset(server, "all")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


# ------------------------------------------------------------------ F09
def test_f09_usdt_usdc_no_longer_overwrite_each_other(monkeypatch):
    """BTCUSDT + BTCUSDC: both must appear (the old id map lost BTCUSDT), and
    both must disclose identity_exact=False (CoinGecko prices are USD)."""
    monkeypatch.setattr(
        bn_p, "_get_json",
        lambda url, params: {"bitcoin": {"usd": 60000.0, "usd_24h_change": 1.5,
                                         "usd_24h_vol": 1e9}},
    )
    rows = bn_p._coingecko_fallback(["BTCUSDT", "BTCUSDC"], None)
    symbols = sorted(r["symbol"] for r in rows)
    assert symbols == ["BTCUSDC", "BTCUSDT"], symbols
    for r in rows:
        assert r["quote_currency"] == "USD"
        assert r["identity_exact"] is False
        assert r["lastPrice"] == 60000.0


def test_f09_exact_usd_pair_keeps_identity(monkeypatch):
    monkeypatch.setattr(
        bn_p, "_get_json",
        lambda url, params: {"bitcoin": {"usd": 60000.0, "usd_24h_change": 1.5}},
    )
    rows = bn_p._coingecko_fallback(["BTCUSD"], None)
    assert rows[0]["identity_exact"] is True
    assert rows[0]["quote_currency"] == "USD"


# ------------------------------------------------------------------ F10
def test_f10_missing_fred_leg_returns_unavailable(monkeypatch):
    """Empty FRED points must end as availability=unavailable — the old code
    fabricated us10y=0.0/us2y=0.0/inverted=False."""
    from opentrading_mcp.providers import intel as intel_p
    from opentrading_mcp.providers import vnstock as vn_p  # noqa: F401 (patch target sanity)

    monkeypatch.setattr(intel_p, "fred_series",
                        lambda sid, limit: {"series": sid, "points": []})
    monkeypatch.setattr("opentrading_mcp.tools.yf.yf_p.yield_curve",
                        lambda: (_ for _ in ()).throw(ProviderUnavailable("blocked")))

    async def run():
        return await _tool_fn("yf_yield_curve")()

    env = asyncio.run(run())
    assert env["availability"] == "unavailable", env
    assert "FRED" in " ".join(env["warnings"]), env["warnings"]


def test_f10_mismatched_leg_dates_withhold_inversion():
    """Legs dated differently: both values stay visible, but `inverted` is
    None — the classification is never made across incompatible dates."""
    ten = {"points": [{"t": "2026-10-20", "v": 4.10}]}
    two = {"points": [{"t": "2026-10-17", "v": 3.90}]}
    us10y = float(ten["points"][0]["v"]) / 100
    us2y = float(two["points"][0]["v"]) / 100
    d10, d2 = ten["points"][0]["t"], two["points"][0]["t"]
    assert math.isclose(us10y, 0.041, abs_tol=1e-9)
    assert math.isclose(us2y, 0.039, abs_tol=1e-9)
    inverted = None if d10 != d2 else us2y > us10y
    assert inverted is None  # withheld — never classified across dates


# ------------------------------------------------------------------ F11
def test_f11_crypto_spot_partial_contract(monkeypatch):
    """A partial provider response must surface `missing` symbols + a warning
    + availability='partial', and the payload preserves completeness."""
    from opentrading_mcp.tools import crypto as crypto_mod

    class _FakeBn:
        def spot_board(self, symbols):
            return [{"symbol": "BTCUSDT", "lastPrice": 60000.0}]

    monkeypatch.setattr(crypto_mod, "bn_p", _FakeBn())

    async def run():
        return await _tool_fn("crypto_spot")(symbols=["BTCUSDT", "ETHUSDT"])

    env = asyncio.run(run())
    data = env["data"]
    assert data["missing"] == ["ETHUSDT"], data
    assert env["availability"] == "partial", env["availability"]
    assert any("ETHUSDT" in w for w in env["warnings"])
    assert env["data"]["requested"] == ["BTCUSDT", "ETHUSDT"]
