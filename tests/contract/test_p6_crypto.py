"""P6 contract: crypto spot + derivs via Binance public REST (TDD RED)."""

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


def test_norm_symbol_variants():
    from opentrading_mcp.providers import binance as bn_p

    assert bn_p._norm("btc/usdt") == "BTCUSDT"
    assert bn_p._norm("ETH-USDT") == "ETHUSDT"
    assert bn_p._norm("SOLUSDT") == "SOLUSDT"


async def test_crypto_spot_returns_tickers(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "symbol": "BTCUSDT",
                "last": 67000.0,
                "change_pct": 1.5,
                "volume": 1000.0,
                "quote_volume": 67000000.0,
            }
        ]

    import opentrading_mcp.tools.crypto as crypto_mod

    monkeypatch.setattr(crypto_mod, "run_blocking", fake_block)
    fn = _tool_fn("crypto_spot")
    env = await fn(symbols=["BTC/USDT"])
    _check_envelope(env, "crypto_spot")
    row = env["data"]["tickers"][0]
    assert row["symbol"] == "BTCUSDT"
    assert row["last"] == 67000.0


async def test_crypto_derivs_returns_funding_oi(monkeypatch):
    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        return [
            {
                "symbol": "BTCUSDT",
                "funding_rate": 0.0001,
                "open_interest": 50000.0,
                "ls_ratio": 1.2,
                "taker_ls_ratio": 1.01,
            }
        ]

    import opentrading_mcp.tools.crypto as crypto_mod

    monkeypatch.setattr(crypto_mod, "run_blocking", fake_block)
    fn = _tool_fn("crypto_derivs")
    env = await fn(symbols=["BTCUSDT"])
    _check_envelope(env, "crypto_derivs")
    row = env["data"]["derivs"][0]
    assert row["funding_rate"] == 0.0001
    assert row["open_interest"] == 50000.0


async def test_crypto_bad_symbol_is_unavailable():
    fn = _tool_fn("crypto_spot")
    env = await fn(symbols=["!!!"])
    assert env["availability"] == "unavailable"


async def test_market_preset_includes_crypto():
    server = create_server("market")
    tools = register_preset(server, "market")
    names = {t["name"] for t in tools}
    assert {"crypto_spot", "crypto_derivs"} <= names


def test_spot_board_normalizes_raw(monkeypatch):
    from opentrading_mcp.providers import binance as bn_p

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> Any:
            return [
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "67000.0",
                    "priceChangePercent": "1.5",
                    "highPrice": "68000",
                    "lowPrice": "66000",
                    "volume": "1000",
                    "quoteVolume": "67000000",
                }
            ]

    class FakeClient:
        def get(self, *a: Any, **k: Any) -> Any:
            return FakeResp()

    monkeypatch.setattr(bn_p, "_shared", lambda: FakeClient())
    rows = bn_p.spot_board(["BTC/USDT"])
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["last"] == 67000.0
    assert rows[0]["change_pct"] == 1.5
