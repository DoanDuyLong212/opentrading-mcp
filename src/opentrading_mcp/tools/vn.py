"""VN-direct tools: quotes, OHLCV, reference, fundamentals, retail gold/FX."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


def register_vn_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_quote_history(
        symbol: str, days: int = 365, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Daily candles for a VN symbol, VCI then KBS fallback. Use for any price history."""
        if ctx is not None:
            await ctx.log("info", f"vn_quote_history {symbol} {days}d")
        try:
            return make_envelope(
                {"symbol": symbol.upper(), "candles": vn_p.quote_history(symbol, days)},
                source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_quote_history", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_equity_quote_batch(symbols: list[str]) -> dict[str, Any]:
        """One-request price board for many symbols. Use for snapshots and movers."""
        try:
            return make_envelope({"quotes": vn_p.equity_quote_batch(symbols)}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_equity_quote_batch", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_listing() -> dict[str, Any]:
        """Full symbol list with company names. Use for universe and lookup."""
        try:
            rows = vn_p.listing_symbols()
            return make_envelope({"count": len(rows), "symbols": rows[:500]}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_listing", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_fundamentals(symbol: str, period: str = "year") -> dict[str, Any]:
        """Ratios and statements via vnstock Fundamental and Finance. Use for quick valuation."""
        try:
            from vnstock import Fundamental
        except ImportError:
            return _na("vn_fundamentals", "vnstock not installed")
        try:
            data = await run_blocking(
                functools.partial(Fundamental().equity(symbol.upper()).ratio, period=period),
                "vn_fundamentals",
            )
            return make_envelope({"symbol": symbol.upper(), "ratios": str(data)}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_fundamentals", str(exc))
        except Exception as exc:
            return _na("vn_fundamentals", f"upstream failed: {exc}")

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_gold() -> dict[str, Any]:
        """SJC and ring gold buy/sell from BTMC retail. Use for local gold premium."""
        try:
            from vnstock import Retail
        except ImportError:
            return _na("vn_retail_gold", "vnstock not installed")
        try:
            frame = await run_blocking(
                functools.partial(Retail().gold, source="btmc"), "vn_retail_gold"
            )
            rows = frame.to_dict(orient="records")
            keep = [r for r in rows if "SJC" in str(r) or "NHẪN" in str(r)]
            return make_envelope({"rows": keep or rows}, source="vnstock-retail")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_retail_gold", str(exc))
        except Exception as exc:
            return _na("vn_retail_gold", f"upstream failed: {exc}")

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_fx() -> dict[str, Any]:
        """VCB USD buy/sell rates. Use for currency conversion context."""
        try:
            from vnstock import Retail
        except ImportError:
            return _na("vn_retail_fx", "vnstock not installed")
        try:
            frame = await run_blocking(Retail().exchange_rate, "vn_retail_fx")
            return make_envelope({"rows": frame.to_dict(orient="records")}, source="vnstock-retail")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_retail_fx", str(exc))
        except Exception as exc:
            return _na("vn_retail_fx", f"upstream failed: {exc}")

    return [
        {"name": "vn_quote_history"},
        {"name": "vn_equity_quote_batch"},
        {"name": "vn_listing"},
        {"name": "vn_fundamentals"},
        {"name": "vn_retail_gold"},
        {"name": "vn_retail_fx"},
    ]
