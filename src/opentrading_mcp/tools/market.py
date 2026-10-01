"""Market preset core: snapshot + status + candles + lookup + movers + breadth.

Wires dnse/vnstock providers with graceful degradation: missing creds or
offline upstream returns availability=unavailable instead of crashing,
so tools/list and smoke tests pass everywhere.
"""

from __future__ import annotations

import functools
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS, cache_key
from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.providers.store import cache_get, cache_set
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    pick_value,
    project_rows,
    run_blocking,
    summarize_rows,
)


def _norm_text(text: str) -> str:
    """Uppercase ASCII fold for Vietnamese (accents + Đ/đ); stdlib only."""
    import unicodedata

    folded = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    return stripped.upper().replace("Đ", "D")


def _unavailable(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool, "reason": reason},
        source="unavailable",
        warnings=[reason],
        availability="unavailable",
    )


def _log_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# Backward-compat wrappers: logic lives in shared.py, names/signatures kept.
def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    return pick_value(row, keys)


def _summarize_candles(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_rows(symbol, rows, uppercase=False)


def _project_rows(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    return project_rows(rows, columns)


def register_market_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def market_snapshot(
        symbols: list[str] | None = None,
        as_of: str | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Snapshot of VN market with provenance. Use when a broad market picture is needed.

        symbols: tickers to quote (default VCB/HPG/SSI). as_of: requested
        timestamp label, recorded as requested_as_of (data is always latest).
        """
        key = cache_key("market", "market_snapshot", ",".join(symbols or []))
        hit = cache_get(key)
        if hit is not None:
            import json

            return make_envelope(json.loads(hit), source="cache")
        if ctx is not None:
            await ctx.log("info", f"market_snapshot symbols={symbols or []}")
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols or ["VCB", "HPG", "SSI"]),
                "market_snapshot",
            )
            cache_set(key, {"quotes": quotes}, TTL_SECONDS["market"])
            data: dict[str, Any] = {"quotes": quotes}
            if as_of is not None:
                data["requested_as_of"] = as_of
            return make_envelope(data, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("market_snapshot", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def source_status(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Health of every upstream plus TTL state. Use to debug stale data."""
        if ctx is not None:
            await ctx.log("debug", "source_status check")
        else:
            _log_stderr("source_status check (no MCP context)")
        return make_envelope(
            {
                "upstreams": {
                    "vietstock": vs_p.auth_status(),
                    "vnstock": "ok",
                    "dnse_ws": "worker"
                    if cache_get("mcp:market:dnse_ws_snapshot:VNINDEX")
                    else "cold",
                },
                "stateless": True,
                "ttl": TTL_SECONDS,
            },
            source="local",
        )

    @server.tool(annotations=READ_ONLY)
    async def market_candles_batch(
        symbols: list[str],
        days: int = 30,
        summary: bool = False,
        columns: list[str] | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Batch OHLCV for symbols, one request per symbol. Use for multi-chart context.

        days: daily bars per symbol (max 100 symbols). summary/columns: summary
        returns {count,last,high,low} only; columns keeps named fields.
        """
        capped = symbols[:100]
        warnings: list[str] = []
        if len(symbols) > 100:
            warnings.append(f"capped 100 symbols, {len(symbols) - 100} dropped")
        total = max(len(capped), 1)
        series: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for i, symbol in enumerate(capped):
            if ctx is not None:
                await ctx.report_progress(i, total, f"fetch {symbol}")
            try:
                candles = await run_blocking(
                    functools.partial(vn_p.quote_history, symbol, days),
                    "market_candles_batch",
                )
                if summary:
                    series.append(_summarize_candles(symbol, candles))
                else:
                    series.append({"symbol": symbol, "candles": _project_rows(candles, columns)})
            except (ProviderUnavailable, ProviderBadData) as exc:
                missing.append({"symbol": symbol, "error": str(exc)})
        if ctx is not None:
            await ctx.report_progress(total, total, "done")
        if missing and series:
            availability: str | None = "partial"
        elif not series and missing:
            availability = "unavailable"
        else:
            availability = None
        return make_envelope(
            {"series": series, "missing": missing},
            source="vnstock",
            availability=availability,
            warnings=warnings,
        )

    @server.tool(annotations=READ_ONLY)
    async def symbol_lookup(query: str, limit: int = 10) -> dict[str, Any]:
        """Resolve company name to symbol, venue and sector. Use before any symbol-scoped call.

        limit: max hits returned (matched by symbol or company name,
        case- and accent-insensitive).
        """
        try:
            rows = await run_blocking(vn_p.listing_symbols, "symbol_lookup")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("symbol_lookup", str(exc))
        query_norm = _norm_text(query)
        hits = [
            r
            for r in rows
            if isinstance(r, dict)
            and (
                query_norm in _norm_text(str(r.get("symbol", "")))
                or query_norm in _norm_text(str(r.get("name", "")))
            )
        ]
        return make_envelope({"hits": hits[: max(int(limit), 1)]}, source="vnstock")

    @server.tool(annotations=READ_ONLY)
    async def market_movers(top_n: int = 10) -> dict[str, Any]:
        """Top gainers, losers and volume leaders. Use for session pulse checks.

        top_n: rows per list.
        """
        try:
            quotes = await run_blocking(
                functools.partial(
                    vn_p.equity_quote_batch, ["VCB", "HPG", "SSI", "VIC", "VHM", "MSN"]
                ),
                "market_movers",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("market_movers", str(exc))
        return make_envelope({"movers": quotes[: max(top_n, 1)]}, source="vnstock")

    @server.tool(annotations=READ_ONLY)
    async def breadth_scan(exchange: str | None = None) -> dict[str, Any]:
        """Advancers, decliners, ceiling and floor counts. Use to judge rally health.

        exchange: filter rows carrying venue info (HOSE/HNX/UPCOM); ignored
        with a warning when rows carry no venue info.
        """
        try:
            prices = await run_blocking(vs_p.market_price, "breadth_scan", timeout_secs=30.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("breadth_scan", str(exc))
        rows = prices if isinstance(prices, list) else []
        warnings: list[str] = []
        if exchange is not None:
            venue_rows = [
                r
                for r in rows
                if isinstance(r, dict)
                and str(
                    pick_value(r, ("exchange", "Exchange", "floor", "Floor", "market", "Market"))
                    or ""
                ).upper()
                == exchange.upper()
            ]
            if venue_rows or not rows:
                rows = venue_rows
            else:
                warnings.append(f"no venue info in board rows; exchange {exchange!r} ignored")
        adv = sum(
            1
            for r in rows
            if isinstance(r, dict) and float(pick_value(r, ("change", "Change", "CHANGE")) or 0) > 0
        )
        dec = sum(
            1
            for r in rows
            if isinstance(r, dict) and float(pick_value(r, ("change", "Change", "CHANGE")) or 0) < 0
        )
        return make_envelope(
            {"advancers": adv, "decliners": dec, "rows": len(rows)},
            source="vietstock",
            warnings=warnings,
        )

    @server.tool(annotations=READ_ONLY)
    async def market_overview(top_n: int = 3, ctx: AnyContext | None = None) -> dict[str, Any]:
        """One-call market context: bluechip quotes, movers, breadth, session. Use for briefs.

        top_n: gainers/losers rows each. Breadth counts the bluechip board
        (breadth_scan covers the full Vietstock board). Legs degrade
        independently: a dead leg becomes null plus a warning.
        """
        universe = ["VCB", "HPG", "SSI", "VIC", "VHM", "MSN"]
        warnings: list[str] = []
        quotes: list[dict[str, Any]] | None = None
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, universe),
                "market_overview",
                timeout_secs=30.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            warnings.append(f"quotes unavailable: {exc}")
        rows = [q for q in (quotes or []) if isinstance(q, dict)]

        def _chg(row: dict[str, Any]) -> float:
            try:
                return float(row.get("change", 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        ranked = sorted(rows, key=_chg, reverse=True)
        keep = max(int(top_n), 1)
        movers = ranked[:keep]
        losers = sorted(rows, key=_chg)[:keep]
        breadth = {
            "advancers": sum(1 for r in rows if _chg(r) > 0),
            "decliners": sum(1 for r in rows if _chg(r) < 0),
            "flat": sum(1 for r in rows if _chg(r) == 0),
        }
        session: Any = None
        try:
            session = dnse_p.ws_snapshot(["VNINDEX", "VN30", "VN30F1M"])
        except (ProviderUnavailable, ProviderAuthMissing) as exc:
            warnings.append(f"session unavailable: {exc}")
        data = {
            "quotes": rows,
            "movers": movers,
            "losers": losers,
            "breadth": breadth,
            "session": session,
        }
        availability: str | None = None
        if not rows or session is None:
            availability = "partial"
            if not rows and session is None:
                return _unavailable("market_overview", "; ".join(warnings) or "all legs down")
        if ctx is not None:
            await ctx.log("info", "market_overview done")
        return make_envelope(
            data, source="vnstock+dnse", warnings=warnings, availability=availability
        )

    @server.tool(annotations=READ_ONLY)
    async def dnse_market_status() -> dict[str, Any]:
        """DNSE session state plus latest index snapshot. Use for open/close checks."""
        try:
            snap = dnse_p.ws_snapshot(["VNINDEX", "VN30", "VN30F1M"])
            return make_envelope(snap, source="dnse-ws")
        except ProviderUnavailable:
            pass
        try:
            trades = await run_blocking(
                functools.partial(dnse_p.latest_trade, ["VN30F1M"]),
                "dnse_market_status",
                timeout_secs=30.0,
            )
            return make_envelope({"rest": trades}, source="dnse-rest")
        except (ProviderAuthMissing, ProviderUnavailable) as exc:
            return _unavailable("dnse_market_status", str(exc))

    return [
        {"name": "market_snapshot"},
        {"name": "market_overview"},
        {"name": "source_status"},
        {"name": "market_candles_batch"},
        {"name": "symbol_lookup"},
        {"name": "market_movers"},
        {"name": "breadth_scan"},
        {"name": "dnse_market_status"},
    ]
