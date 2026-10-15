"""Crypto tools: Binance spot + derivatives, public REST, no key (P6)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import binance as bn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY_OPEN,
    AnyContext,
    cache_lookup,
    cache_store,
    run_blocking,
)


def register_crypto_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY_OPEN)
    async def crypto_spot(symbols: list[str], ctx: AnyContext | None = None) -> dict[str, Any]:
        """Binance spot 24h tickers. Use for crypto price and volume reads.

        symbols: up to 10, any of BTCUSDT / BTC/USDT / btc-usdt spellings.
        """
        fp = f"{symbols}"
        hit = await cache_lookup("crypto_spot", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"crypto_spot {symbols}")
        capped = symbols[:10]
        warnings = (
            [f"capped 10 symbols, {len(symbols) - 10} dropped"] if len(symbols) > 10 else []
        )
        try:
            tickers = await run_blocking(
                functools.partial(bn_p.spot_board, capped),
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
        return await cache_store(
            "crypto_spot", fp, TTL_SECONDS["market"],  # 24/7 asset: fixed 60s, not HOSE hours
            {"tickers": tickers}, source="binance", warnings=warnings or None,
        )

    @server.tool(annotations=READ_ONLY_OPEN)
    async def crypto_derivs(symbols: list[str], ctx: AnyContext | None = None) -> dict[str, Any]:
        """Binance futures funding, OI and long/short ratios. Use for leverage reads.

        symbols: up to 5 perpetual symbols (BTCUSDT ...). Rows carry per-symbol
        error instead of failing the batch when one symbol is delisted.
        """
        fp = f"{symbols}"
        hit = await cache_lookup("crypto_derivs", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"crypto_derivs {symbols}")
        capped = symbols[:5]
        warnings = (
            [f"capped 5 symbols, {len(symbols) - 5} dropped"] if len(symbols) > 5 else []
        )
        try:
            derivs = await run_blocking(
                functools.partial(bn_p.derivs_board, capped),
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
        return await cache_store(
            "crypto_derivs", fp, TTL_SECONDS["hour"],
            {"derivs": derivs}, source="binance-futures", warnings=warnings or None
        )

    return [
        {"name": "crypto_spot"},
        {"name": "crypto_derivs"},
    ]
