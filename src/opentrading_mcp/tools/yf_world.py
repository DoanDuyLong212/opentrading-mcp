"""yfinance world tools: breadth, oracle markets, regime, mega flows, alloc."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking
from opentrading_mcp.tools.yf import _na


async def _call(tool: str, fn: Any, *args: Any, secs: float = 90.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def register_yf_world_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def yf_world_indices() -> dict[str, Any]:
        """24 world benchmarks. Use for global breadth."""
        try:
            return make_envelope(
                {"indices": await _call("w", yf_p.world_indices)}, source="yfinance"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_world_indices", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def yf_oracle_markets() -> dict[str, Any]:
        """40 markets in 6 groups with 30d stats. Use for cross-asset state."""
        try:
            return make_envelope(
                await _call("o", yf_p.oracle_markets, secs=120.0), source="yfinance"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_oracle_markets", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def yf_regime_assets() -> dict[str, Any]:
        """7 regime drivers with 2y history. Use for RISK-ON/OFF calls."""
        try:
            return make_envelope(
                await _call("r", yf_p.regime_assets, secs=120.0), source="yfinance"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_regime_assets", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def yf_mega_flows() -> dict[str, Any]:
        """Mega-cap leader flows. Use to follow global smart money."""
        try:
            return make_envelope(await _call("m", yf_p.mega_flows), source="yfinance")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_mega_flows", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def yf_alloc_history(asset: str = "GC", timeframe: str = "1d") -> dict[str, Any]:
        """Long allocation history per asset. Use for regime backtests."""
        try:
            return make_envelope(
                await _call("a", yf_p.alloc_history, asset, timeframe, secs=120.0),
                source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("yf_alloc_history", str(exc))

    return [
        {"name": "yf_world_indices"},
        {"name": "yf_oracle_markets"},
        {"name": "yf_regime_assets"},
        {"name": "yf_mega_flows"},
        {"name": "yf_alloc_history"},
    ]
