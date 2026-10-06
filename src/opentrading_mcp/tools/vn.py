"""VN-direct tools: quotes, OHLCV, reference, fundamentals, retail gold/FX."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    CLOSE_KEYS,
    HIGH_KEYS,
    LOW_KEYS,
    READ_ONLY,
    AnyContext,
    pick_value,
    project_rows,
    run_blocking,
    summarize_rows,
)


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


# Backward-compat aliases: logic lives in shared.py, names kept for imports.
_CLOSE_KEYS = CLOSE_KEYS
_HIGH_KEYS = HIGH_KEYS
_LOW_KEYS = LOW_KEYS


def _project(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    return project_rows(rows, columns)


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    return pick_value(row, keys)


def _summarize(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_rows(symbol, rows, uppercase=True)


def register_vn_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_quote_history(
        symbol: str,
        days: int = 365,
        summary: bool = False,
        columns: list[str] | None = None,
        interval: str = "1D",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Candles for a VN symbol (1D/1W/1M), VCI then KBS fallback. Use for any price history.

        days: bars requested (max 365 nến; weekly/monthly span nhân hệ số).
        interval: '1D' (mặc định), '1W', '1M'. summary/columns: summary returns
        {count,last,high,low} only; columns keeps named fields.
        """
        if ctx is not None:
            await ctx.log("info", f"vn_quote_history {symbol} {days}d {interval}")
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, days, interval),
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
        """One-request price board for many symbols. Use for snapshots and movers.

        summary/columns: summary returns {count,symbols} only; columns keeps
        named fields per quote.
        """
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols),
                "vn_equity_quote_batch",
            )
            if summary:
                names = [
                    q.get("symbol", s) if isinstance(q, dict) else s
                    for q, s in zip(quotes, symbols, strict=False)
                ]
                return make_envelope({"count": len(quotes), "symbols": names}, source="vnstock")
            return make_envelope({"quotes": _project(quotes, columns)}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_equity_quote_batch", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_listing(limit: int = 500) -> dict[str, Any]:
        """Full symbol list with company names. Use for universe and lookup.

        limit: max symbols returned (universe ~1500).
        """
        try:
            rows = await run_blocking(vn_p.listing_symbols, "vn_listing")
            return make_envelope(
                {"count": len(rows), "symbols": rows[: max(int(limit), 1)]},
                source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_listing", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_fundamentals(
        symbol: str, period: str = "year", report_type: str = "ttm"
    ) -> dict[str, Any]:
        """Ratios and statements via vnstock Fundamental and Finance. Use for quick valuation.

        period: 'year' or 'quarter'. report_type: 'ttm' (trailing twelve months) or 'latest'.
        """
        try:
            from vnstock import Fundamental
        except ImportError:
            return _na("vn_fundamentals", "vnstock not installed")
        try:
            data = await run_blocking(
                functools.partial(
                    Fundamental().equity(symbol.upper()).ratio,
                    period=period,
                    report_type=report_type,
                ),
                "vn_fundamentals",
            )
            to_records = getattr(data, "to_dict", None)
            if callable(to_records):
                try:
                    ratios = to_records(orient="records")
                except Exception:
                    try:
                        ratios = to_records()
                    except Exception:
                        ratios = str(data)
            else:
                ratios = data
            return make_envelope({"symbol": symbol.upper(), "ratios": ratios}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_fundamentals", str(exc))
        except Exception as exc:
            return _na("vn_fundamentals", f"upstream failed: {exc}")

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_gold(source: str = "btmc") -> dict[str, Any]:
        """SJC and ring gold buy/sell from BTMC retail. Use for local gold premium.

        source: retail source id (default 'btmc'). Direct BTMC https fetch
        first (15s); vnstock lib fallback (its http URL hangs without timeout).
        """
        if source.strip().lower() == "btmc":
            try:
                from opentrading_mcp.providers import vn_public as pub_p

                rows = await run_blocking(pub_p.btmc_gold, "vn_retail_gold", timeout_secs=20.0)
                keep = [r for r in rows if "SJC" in str(r) or "NHẪN" in str(r)]
                return make_envelope({"rows": keep or rows}, source="btmc-direct")
            except (ProviderUnavailable, ProviderBadData):
                pass
        try:
            from vnstock import Retail
        except ImportError:
            return _na("vn_retail_gold", "vnstock not installed")
        try:
            frame = await run_blocking(
                functools.partial(Retail().gold, source=source), "vn_retail_gold"
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
