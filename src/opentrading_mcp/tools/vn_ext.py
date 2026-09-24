"""VN extended tools: index/equity/futures/forex/crypto/global OHLCV, reference, company, MSN."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking
from opentrading_mcp.tools.vn import _na


async def _call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    return await run_blocking(functools.partial(fn, *args, **kwargs), tool, timeout_secs=60.0)


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


def register_vn_ext_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_index_ohlcv(
        symbol: str = "VNINDEX",
        count: int = 100,
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Index bars for VN tickers. Use for index history and breadth."""
        try:
            rows = await _call("i", vn_p.index_ohlcv, symbol, count)
            if summary:
                return make_envelope(_summarize(symbol, rows), source="vnstock")
            return make_envelope(
                {"symbol": symbol.upper(), "bars": _project(rows, columns)}, source="vnstock"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_index_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_equity_ohlcv(
        symbol: str,
        count: int = 100,
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Equity bars via Market API. Use as OHLCV alternative to quotes."""
        try:
            rows = await _call("e", vn_p.equity_ohlcv, symbol, count)
            if summary:
                return make_envelope(_summarize(symbol, rows), source="vnstock")
            return make_envelope(
                {"symbol": symbol.upper(), "bars": _project(rows, columns)}, source="vnstock"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_equity_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_futures_ohlcv(
        symbol: str = "VN30F1M",
        count: int = 100,
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Futures bars. Use for derivatives backtest input."""
        try:
            rows = await _call("f", vn_p.futures_ohlcv, symbol, count)
            if summary:
                return make_envelope(_summarize(symbol, rows), source="vnstock")
            return make_envelope(
                {"symbol": symbol.upper(), "bars": _project(rows, columns)}, source="vnstock"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_futures_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_forex_ohlcv(pair: str = "USDVND", count: int = 30) -> dict[str, Any]:
        """FX bars. Use for currency context."""
        try:
            rows = await _call("f", vn_p.forex_ohlcv, pair, count)
            return make_envelope({"pair": pair.upper(), "bars": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_forex_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_crypto_ohlv(symbol: str = "BTCUSDT", count: int = 30) -> dict[str, Any]:
        """Crypto bars. Use for digital-asset regime reads."""
        try:
            rows = await _call("c", vn_p.crypto_ohlv, symbol, count)
            return make_envelope({"symbol": symbol.upper(), "bars": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_crypto_ohlv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_global_index(symbol: str = "USA30", count: int = 30) -> dict[str, Any]:
        """Global index bars. Use as yfinance fallback."""
        try:
            rows = await _call("g", vn_p.global_index, symbol, count)
            return make_envelope({"symbol": symbol.upper(), "bars": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_global_index", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_reference(exchange: str = "HOSE") -> dict[str, Any]:
        """ICB reference by exchange. Use for universe construction."""
        try:
            rows = await _call("r", vn_p.reference_equity, exchange)
            return make_envelope({"exchange": exchange.upper(), "rows": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_reference", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_company(symbol: str) -> dict[str, Any]:
        """Profile, holders and officers. Use for company research."""
        try:
            return make_envelope(await _call("c", vn_p.company_info, symbol), source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_company", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_msn_fx_gold() -> dict[str, Any]:
        """USDVND and XAUUSD via MSN. Use for gold-basis math."""
        try:
            return make_envelope({"series": await _call("m", vn_p.msn_fx_gold)}, source="msn")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_msn_fx_gold", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_trades(symbol: str, limit: int = 20) -> dict[str, Any]:
        """Tick-level matched trades. Use for microstructure reads."""
        try:
            rows = await _call("t", vn_p.equity_trades, symbol, limit)
            return make_envelope({"symbol": symbol.upper(), "trades": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_trades", str(exc))

    return [
        {"name": "vn_index_ohlcv"},
        {"name": "vn_equity_ohlcv"},
        {"name": "vn_futures_ohlcv"},
        {"name": "vn_forex_ohlcv"},
        {"name": "vn_crypto_ohlv"},
        {"name": "vn_global_index"},
        {"name": "vn_reference"},
        {"name": "vn_company"},
        {"name": "vn_msn_fx_gold"},
        {"name": "vn_trades"},
    ]
