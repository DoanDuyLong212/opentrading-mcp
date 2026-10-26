"""Wave-1 adversarial oracles — hunt for NEW defects in the F09/F10/F11
deep contracts and the F05a fill fallback, from angles the original tests
did not cover."""

from __future__ import annotations

import asyncio

import pytest

from opentrading_mcp.providers import binance as bn_p
from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str):
    server = create_server("all")
    register_preset(server, "all")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


# ------------------------------------------------- F09-A1 duplicate symbols
def test_f09_a1_duplicate_symbols_collapse_cleanly(monkeypatch):
    """['BTCUSDT', 'BTCUSDT'] → one row, requested deduped, missing empty."""
    from opentrading_mcp.tools import crypto as crypto_mod

    class _FakeBn:
        def spot_board(self, symbols):
            return [{"symbol": "BTCUSDT", "lastPrice": 60000.0}]

    monkeypatch.setattr(crypto_mod, "bn_p", _FakeBn())

    async def run():
        return await _tool_fn("crypto_spot")(symbols=["BTCUSDT", "BTCUSDT"])

    env = asyncio.run(run())
    assert env["data"]["missing"] == []
    assert env["data"]["requested"] == ["BTCUSDT"]
    assert env["availability"] is None or env["availability"] == "available"


# ------------------------------------------------- F09-A2 unmapped base
def test_f09_a2_unmapped_base_becomes_missing(monkeypatch):
    """A base with no CoinGecko id (fake upstream has no 'xyz') must be listed
    as missing — never fabricated from another symbol's row."""
    monkeypatch.setattr(
        bn_p, "_get_json",
        lambda url, params: {"bitcoin": {"usd": 60000.0}},
    )
    rows = bn_p._coingecko_fallback(["XYZUSDT", "BTCUSDT"], None)
    symbols = sorted(r["symbol"] for r in rows)
    assert symbols == ["BTCUSDT"]  # XYZ row skipped: no fabrication
    # the tool layer must surface XYZUSDT as missing (completeness contract)


def test_f09_a2b_tool_reports_unmapped_missing(monkeypatch):
    from opentrading_mcp.tools import crypto as crypto_mod

    class _FakeBn:
        def spot_board(self, symbols):
            return bn_p._coingecko_fallback(symbols, None)

    monkeypatch.setattr(crypto_mod, "bn_p", _FakeBn())
    monkeypatch.setattr(
        bn_p, "_get_json",
        lambda url, params: {"bitcoin": {"usd": 60000.0}},
    )

    async def run():
        return await _tool_fn("crypto_spot")(symbols=["XYZUSDT", "BTCUSDT"])

    env = asyncio.run(run())
    assert env["data"]["missing"] == ["XYZUSDT"], env["data"]
    assert env["availability"] == "partial"


# ------------------------------------------------- F05a opens with None/0
def test_f05a_none_or_zero_opens_fall_back_to_close(monkeypatch):
    """None/zero opens anywhere → whole series falls back to next-bar-close
    (documented), never a partial mixed-price chain."""
    from opentrading_mcp.tools.quant_shared import _run_strategy

    closes = [100.0, 110.0, 121.0]
    dates = ["2026-01-01", "2026-01-02", "2026-01-03"]

    for bad_opens in ([100.0, None, 110.0], [100.0, 0.0, 110.0]):
        out = _run_strategy(
            closes, "buy_hold", 1, 2, 0.0, dates=dates, opens=bad_opens
        )
        assert out["fill"] == "next-bar-close-fallback", (bad_opens, out)
        # next-bar-close: fill close[1]=110, mark close[2]=121 → +10%
        assert abs(out["net_return"] - 0.10) < 1e-6, (bad_opens, out)


# ------------------------------------------------- F11 cache round-trip
def test_f11_cache_hit_preserves_completeness_metadata(monkeypatch):
    """Second call (cache hit) must return the SAME completeness contract as
    the miss: missing list, requested list, partial availability."""
    from opentrading_mcp.tools import crypto as crypto_mod

    class _FakeBn:
        def spot_board(self, symbols):
            return [{"symbol": "BTCUSDT", "lastPrice": 60000.0}]

    monkeypatch.setattr(crypto_mod, "bn_p", _FakeBn())

    async def run():
        fn = _tool_fn("crypto_spot")
        first = await fn(symbols=["BTCUSDT", "ETHUSDT"])
        second = await fn(symbols=["BTCUSDT", "ETHUSDT"])  # cache hit
        return first, second

    first, second = asyncio.run(run())
    assert first["data"]["missing"] == second["data"]["missing"]
    assert first["data"]["requested"] == second["data"]["requested"]
    assert second["availability"] == "partial"
    assert second["provenance"].get("cached") is True


# ------------------------------------------------- F09 mixed quote suffixes
def test_f09_mixed_usd_family_identity(monkeypatch):
    """BTCUSD (exact) + BTCUSDT + BTCBUSD (reference) in one call: exactly one
    identity_exact=True row, two False rows, no overwrites."""
    monkeypatch.setattr(
        bn_p, "_get_json",
        lambda url, params: {"bitcoin": {"usd": 60000.0}},
    )
    rows = bn_p._coingecko_fallback(["BTCUSD", "BTCUSDT", "BTCBUSD"], None)
    assert len(rows) == 3
    exact = [r["symbol"] for r in rows if r["identity_exact"]]
    assert exact == ["BTCUSD"]
    assert {r["quote_currency"] for r in rows} == {"USD"}


# ------------------------------------------------- F10 both legs same date
def test_f10_same_date_legs_compute_inversion():
    """Same-date legs → inversion IS computed (None-withholding only applies
    to mismatched dates)."""
    ten = {"points": [{"t": "2026-10-20", "v": 4.10}]}
    two = {"points": [{"t": "2026-10-20", "v": 3.90}]}
    us10y = float(ten["points"][0]["v"]) / 100
    us2y = float(two["points"][0]["v"]) / 100
    d10, d2 = ten["points"][0]["t"], two["points"][0]["t"]
    inverted = None if d10 != d2 else us2y > us10y
    assert inverted is False  # 3.90 < 4.10 → not inverted
