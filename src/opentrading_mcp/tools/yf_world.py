"""yfinance world tools: breadth, oracle markets, regime, mega flows, alloc."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.tools.shared import (
    READ_ONLY_OPEN,
    cache_lookup,
    cache_store,
    run_blocking,
)
from opentrading_mcp.tools.yf import _na


async def _call(tool: str, fn: Any, *args: Any, secs: float = 90.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_yf_world_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_world_indices(tickers: list[str] | None = None) -> dict[str, Any]:
        """24 world benchmarks. Use for global breadth.

        tickers: subset override (default WORLD 24).
        """
        fp = f"{tickers}"
        hit = await cache_lookup("yf_world_indices", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("w", yf_p.world_indices, tickers)
            return await cache_store(
                "yf_world_indices", fp, TTL_SECONDS["world"],
                {"indices": data}, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_world_indices", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_oracle_markets(groups: list[str] | None = None) -> dict[str, Any]:
        """40 markets in 6 groups with 30d stats. Use for cross-asset state.

        groups: keep only named groups (crypto/metals/energy/agri/bonds_fx/index).
        """
        fp = f"{groups}"
        hit = await cache_lookup("yf_oracle_markets", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("o", yf_p.oracle_markets, groups, secs=120.0)
            return await cache_store(
                "yf_oracle_markets", fp, TTL_SECONDS["world"],
                data, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_oracle_markets", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_regime_assets() -> dict[str, Any]:
        """7 regime drivers with 2y history. Use for RISK-ON/OFF calls."""
        hit = await cache_lookup("yf_regime_assets", "-")
        if hit is not None:
            return hit
        try:
            data = await _call("r", yf_p.regime_assets, secs=120.0)
            return await cache_store(
                "yf_regime_assets", "-", TTL_SECONDS["documents"],
                data, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_regime_assets", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_mega_flows(top_n: int = 15) -> dict[str, Any]:
        """Mega-cap leader flows. Use to follow global smart money.

        top_n: leaders evaluated (default 15 of the ~20-name universe).
        """
        fp = f"{top_n}"
        hit = await cache_lookup("yf_mega_flows", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("m", yf_p.mega_flows, max(int(top_n), 1))
            return await cache_store(
                "yf_mega_flows", fp, TTL_SECONDS["world"],
                data, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_mega_flows", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_alloc_history(asset: str = "GC", timeframe: str = "1d") -> dict[str, Any]:
        """Long allocation history per asset. Use for regime backtests.

        asset: GC/VND/BTC/OIL/SILVER/COFFEE (unknown falls back to GC).
        timeframe: '1d' or '1wk'; returns last 60 closes over 5y.
        """
        fp = f"{asset}|{timeframe}"
        hit = await cache_lookup("yf_alloc_history", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("a", yf_p.alloc_history, asset, timeframe, secs=120.0)
            return await cache_store(
                "yf_alloc_history", fp, TTL_SECONDS["documents"],
                data, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_alloc_history", str(exc))

    @server.tool(annotations=READ_ONLY_OPEN)
    async def yf_market_pins() -> dict[str, Any]:
        """5-day pins for world majors plus VN watchlist. Use for brief headers."""
        hit = await cache_lookup("yf_market_pins", "-")
        if hit is not None:
            return hit
        try:
            data = await _call("p", yf_p.market_pins)
            return await cache_store(
                "yf_market_pins", "-", TTL_SECONDS["world"],
                data, source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_market_pins", str(exc))

    return [
        {"name": "yf_world_indices"},
        {"name": "yf_oracle_markets"},
        {"name": "yf_regime_assets"},
        {"name": "yf_mega_flows"},
        {"name": "yf_alloc_history"},
        {"name": "yf_market_pins"},
    ]
