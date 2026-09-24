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


_CLOSE_KEYS = ("c", "close", "Close", "CLOSE")
_HIGH_KEYS = ("h", "high", "High", "HIGH")
_LOW_KEYS = ("l", "low", "Low", "LOW")


def _project(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    if not columns:
        return rows
    return [{k: r[k] for k in columns if k in r} for r in rows]


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in row:
            return row[k]
    return None


def _summarize(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"symbol": symbol.upper(), "count": 0, "last": None, "high": None, "low": None}
    closes = [_pick(r, _CLOSE_KEYS) for r in rows]
    highs = [_pick(r, _HIGH_KEYS) for r in rows]
    lows = [_pick(r, _LOW_KEYS) for r in rows]
    last_close = closes[-1] if closes[-1] is not None else rows[-1]
    try:
        high = max(h for h in highs if isinstance(h, (int, float)))
    except ValueError:
        high = None
    try:
        low = min(lo for lo in lows if isinstance(lo, (int, float)))
    except ValueError:
        low = None
    return {
        "symbol": symbol.upper(),
        "count": len(rows),
        "last": last_close,
        "high": high,
        "low": low,
    }


def register_vn_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_quote_history(
        symbol: str,
        days: int = 365,
        summary: bool = False,
        columns: list[str] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Daily candles for a VN symbol, VCI then KBS fallback. Use for any price history."""
        if ctx is not None:
            await ctx.log("info", f"vn_quote_history {symbol} {days}d")
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, days),
                "vn_quote_history",
            )
            if summary:
                return make_envelope(_summarize(symbol, candles), source="vnstock")
            return make_envelope(
                {"symbol": symbol.upper(), "candles": _project(candles, columns)},
                source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_quote_history", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_equity_quote_batch(
        symbols: list[str],
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """One-request price board for many symbols. Use for snapshots and movers."""
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols),
                "vn_equity_quote_batch",
            )
            if summary:
                names = [q.get("symbol", s) if isinstance(q, dict) else s for q, s in zip(quotes, symbols)]
                return make_envelope(
                    {"count": len(quotes), "symbols": names}, source="vnstock"
                )
            return make_envelope({"quotes": _project(quotes, columns)}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_equity_quote_batch", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_listing() -> dict[str, Any]:
        """Full symbol list with company names. Use for universe and lookup."""
        try:
            rows = await run_blocking(vn_p.listing_symbols, "vn_listing")
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
