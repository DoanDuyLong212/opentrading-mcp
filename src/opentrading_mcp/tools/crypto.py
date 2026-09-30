"""Crypto tools: Binance spot + derivatives, public REST, no key (P6)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import binance as bn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def register_crypto_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def crypto_spot(symbols: list[str], ctx: AnyContext | None = None) -> dict[str, Any]:
        """Binance spot 24h tickers. Use for crypto price and volume reads.

        symbols: up to 10, any of BTCUSDT / BTC/USDT / btc-usdt spellings.
        """
        if ctx is not None:
            await ctx.log("info", f"crypto_spot {symbols}")
        try:
            tickers = await run_blocking(
                functools.partial(bn_p.spot_board, symbols),
                "crypto_spot",
                timeout_secs=30.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "crypto_spot"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope({"tickers": tickers}, source="binance-spot")

    @server.tool(annotations=READ_ONLY)
    async def crypto_derivs(symbols: list[str], ctx: AnyContext | None = None) -> dict[str, Any]:
        """Binance futures funding, OI and long/short ratios. Use for leverage reads.

        symbols: up to 5 perpetual symbols (BTCUSDT ...). Rows carry per-symbol
        error instead of failing the batch when one symbol is delisted.
        """
        if ctx is not None:
            await ctx.log("info", f"crypto_derivs {symbols}")
        try:
            derivs = await run_blocking(
                functools.partial(bn_p.derivs_board, symbols),
                "crypto_derivs",
                timeout_secs=60.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "crypto_derivs"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope({"derivs": derivs}, source="binance-futures")

    return [
        {"name": "crypto_spot"},
        {"name": "crypto_derivs"},
    ]
