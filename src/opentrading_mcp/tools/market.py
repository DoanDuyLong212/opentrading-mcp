"""Market core: snapshot + status + candles + lookup + movers + breadth.

Wires dnse/vnstock providers with graceful degradation: missing creds or
offline upstream returns availability=unavailable instead of crashing,
so tools/list and smoke tests pass everywhere.
"""

from __future__ import annotations

import asyncio
import difflib
import functools
import re
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
from opentrading_mcp.providers.store import acache_get, acache_set
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


# symbol_resolve tables: stdlib-only, no network.
_CRYPTO_BASES = frozenset(
    "BTC ETH SOL BNB XRP DOGE ADA TON TRX AVAX LINK DOT NEAR ARB OP ATOM "
    "LTC BCH ETC FIL ICP APT SUI INJ SEI TIA JUP PEPE SHIB WLD RENDER FET "
    "ONDO LDO AAVE UNI MKR SNX SAND MANA AXS CHZ GAL GMT APE LRC ZEC DASH "
    "XMR XTZ EOS IOTA HBAR VET ALGO FLOW EGLD KAVA ROSE ONE CELO FTM MINA "
    "XLM QNT GRT STX IMX BLUR PYTH JASMY BONK FLOKI ORDI TAO STRK ZK ARB "
    "SFP PENDLE".split()
)
_CURRENCIES = frozenset(
    "USD VND EUR JPY GBP AUD CAD CHF CNY HKD SGD KRW TWD THB MYR IDR PHP "
    "INR NZD SEK NOK DKK PLN CZK HUF ILS AED SAR QAR KWD ZAR BRL MXN CLP "
    "COP PEN ARS TRY".split()
)
_GLOBAL_TICKERS = frozenset(
    "^GSPC ^IXIC ^DJI ^N225 ^FTSE ^STOXX ^GDAXI ^HSI ^KS11 ^TWII ^AXJO "
    "^GSPTSE ^FCHI GC=F SI=F CL=F BZ=F NG=F HG=F BTC-USD ETH-USD DX-Y.NYB "
    "^TNX ^FVX ^TYX ^IRX ZN=F USA30".split()
)
# normalized query -> (symbol, asset_class, venue, name, use_tool, use_args)
# normalized query -> (symbol, asset_class, venue, name, use_tool, use_args)
_ALIASES: dict[str, tuple[str, str, str, str, str, dict[str, Any]]] = {
    "SP500": (
        "^GSPC",
        "global_index",
        "US",
        "S&P 500",
        "yf_global_indices",
        {"tickers": ["^GSPC"]},
    ),
    "S&P 500": (
        "^GSPC",
        "global_index",
        "US",
        "S&P 500",
        "yf_global_indices",
        {"tickers": ["^GSPC"]},
    ),
    "NASDAQ": (
        "^IXIC",
        "global_index",
        "US",
        "Nasdaq Composite",
        "yf_global_indices",
        {"tickers": ["^IXIC"]},
    ),
    "DOW": ("^DJI", "global_index", "US", "Dow Jones", "yf_global_indices", {"tickers": ["^DJI"]}),
    "DOW JONES": (
        "^DJI",
        "global_index",
        "US",
        "Dow Jones",
        "yf_global_indices",
        {"tickers": ["^DJI"]},
    ),
    "NIKKEI": (
        "^N225",
        "global_index",
        "JP",
        "Nikkei 225",
        "yf_global_indices",
        {"tickers": ["^N225"]},
    ),
    "HANG SENG": (
        "^HSI",
        "global_index",
        "HK",
        "Hang Seng",
        "yf_global_indices",
        {"tickers": ["^HSI"]},
    ),
    "VANG": (
        "GC=F",
        "commodity",
        "global",
        "Gold futures",
        "yf_commodities",
        {"tickers": ["GC=F"]},
    ),
    "GOLD": (
        "GC=F",
        "commodity",
        "global",
        "Gold futures",
        "yf_commodities",
        {"tickers": ["GC=F"]},
    ),
    "VANG THE GIOI": (
        "GC=F",
        "commodity",
        "global",
        "Gold futures",
        "yf_commodities",
        {"tickers": ["GC=F"]},
    ),
    "BAC": (
        "SI=F",
        "commodity",
        "global",
        "Silver futures",
        "yf_commodities",
        {"tickers": ["SI=F"]},
    ),
    "SILVER": (
        "SI=F",
        "commodity",
        "global",
        "Silver futures",
        "yf_commodities",
        {"tickers": ["SI=F"]},
    ),
    "BRENT": (
        "BZ=F",
        "commodity",
        "global",
        "Brent crude",
        "yf_commodities",
        {"tickers": ["BZ=F"]},
    ),
    "DAU BRENT": (
        "BZ=F",
        "commodity",
        "global",
        "Brent crude",
        "yf_commodities",
        {"tickers": ["BZ=F"]},
    ),
    "WTI": ("CL=F", "commodity", "global", "WTI crude", "yf_commodities", {"tickers": ["CL=F"]}),
    "DAU WTI": (
        "CL=F",
        "commodity",
        "global",
        "WTI crude",
        "yf_commodities",
        {"tickers": ["CL=F"]},
    ),
    "DAU THO": (
        "CL=F",
        "commodity",
        "global",
        "WTI crude",
        "yf_commodities",
        {"tickers": ["CL=F"]},
    ),
    "BITCOIN": ("BTCUSDT", "crypto", "Binance", "Bitcoin", "crypto_spot", {"symbols": ["BTCUSDT"]}),
    "ETHEREUM": (
        "ETHUSDT",
        "crypto",
        "Binance",
        "Ethereum",
        "crypto_spot",
        {"symbols": ["ETHUSDT"]},
    ),
    "DOLLAR INDEX": (
        "DX-Y.NYB",
        "global_index",
        "US",
        "Dollar index",
        "yf_global_indices",
        {"tickers": ["DX-Y.NYB"]},
    ),
    "DXY": (
        "DX-Y.NYB",
        "global_index",
        "US",
        "Dollar index",
        "yf_global_indices",
        {"tickers": ["DX-Y.NYB"]},
    ),
}


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

        symbols: tickers to quote — default the full VN30 basket (P14).
        as_of: requested timestamp label, recorded as requested_as_of
        (data is always latest).
        """
        key = cache_key("market_snapshot", ",".join(symbols or []))
        hit = await acache_get(key)
        if hit is not None:
            import json

            return make_envelope(json.loads(hit), source="cache")
        if ctx is not None:
            await ctx.log("info", f"market_snapshot symbols={symbols or []}")
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols or vn_p.VN30),
                "market_snapshot",
            )
            await acache_set(key, {"quotes": quotes}, TTL_SECONDS["market"])
            quotes, missing = vn_p.split_batch(quotes)
            data: dict[str, Any] = {"quotes": quotes}
            if as_of is not None:
                data["requested_as_of"] = as_of
            if missing:
                data["missing"] = missing
            return make_envelope(
                data, source="vnstock",
                warnings=[f"batch partial: {len(missing)} symbols missing"] if missing else None,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("market_snapshot", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def source_status(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Health of every upstream plus TTL state. Use to debug stale data."""
        if ctx is not None:
            await ctx.log("debug", "source_status check")
        else:
            _log_stderr("source_status check (no MCP context)")
        try:
            await run_blocking(
                functools.partial(vn_p.quote_history, "VCB", 1),
                "source_status_probe",
                timeout_secs=5.0,
            )
            vnstock_state = "ok"
        except (ProviderUnavailable, ProviderBadData):
            vnstock_state = "unavailable"
        except Exception:
            vnstock_state = "unavailable"
        return make_envelope(
            {
                "upstreams": {
                    "vietstock": vs_p.auth_status(),
                    "vnstock": vnstock_state,
                    # First use imports vnstock (seconds of CPU): never on the event loop.
                    "vnstock_quota": await asyncio.to_thread(vn_p.quota_info),
                    "dnse_ws": "worker"
                    if await acache_get("mcp:market:dnse_ws_snapshot:VNINDEX")
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
    async def symbol_lookup(
        query: str, limit: int = 10, offset: int = 0
    ) -> dict[str, Any]:
        """Resolve company name to symbol, venue and sector. Use before any symbol-scoped call.

        limit/offset: paginate hits (matched by symbol or company name,
        case- and accent-insensitive).
        """
        try:
            rows = await run_blocking(vn_p.listing_symbols, "symbol_lookup")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("symbol_lookup", str(exc))
        from opentrading_mcp.schemas import paginate_list

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
        items, page = paginate_list(hits, limit, offset)
        return make_envelope({"hits": items}, source="vnstock", page=page)

    # ---- symbol_resolve: multi-asset resolver (local tables + VN listing) ----
    @server.tool(annotations=READ_ONLY)
    async def symbol_resolve(query: str, limit: int = 5) -> dict[str, Any]:
        """Resolve ANY asset code to symbol + class + next tool. Use FIRST when unsure.

        Covers VN stocks, crypto, forex, indices, futures, gold/oil. Returns ranked
        candidates with fallback order; ambiguous=true means ask the user or try #1 then #2.
        """
        cands: list[dict[str, Any]] = []
        warnings: list[str] = []
        q_raw = (query or "").strip()
        if not q_raw:
            return make_envelope(
                {"query": query, "resolved": None, "ambiguous": False, "candidates": []},
                source="local",
                availability="empty",
            )
        qn = _norm_text(q_raw)
        qc = re.sub(r"[\s\-/_.]", "", qn)

        def _add(
            symbol: str,
            asset_class: str,
            venue: str,
            name: str,
            score: int,
            reason: str,
            use_tool: str,
            use_args: dict[str, Any],
        ) -> None:
            if not any(c["symbol"] == symbol for c in cands):
                cands.append(
                    {
                        "symbol": symbol,
                        "asset_class": asset_class,
                        "venue": venue,
                        "name": name,
                        "score": score,
                        "reason": reason,
                        "use_tool": use_tool,
                        "use_args": use_args,
                    }
                )

        # 1) forex pair XXXYYY or XXX/YYY
        if re.fullmatch(r"[A-Z]{6}", qc or "") and qc[:3] in _CURRENCIES and qc[3:] in _CURRENCIES:
            _add(
                qc,
                "forex",
                "OTC",
                f"{qc[:3]}/{qc[3:]}",
                90,
                "6-letter currency pair",
                "vn_forex_ohlcv",
                {"pair": qc},
            )
        # 2) VN futures (VN30F1M style)
        if re.fullmatch(r"[A-Z0-9]{2,12}F[12]M", qc or ""):
            _add(
                qc,
                "vn_futures",
                "DNSE",
                qc,
                90,
                "futures code pattern",
                "dnse_ohlc_history",
                {"symbol": qc},
            )
        # 3) crypto: BASE[QUOTE]
        base, suffix = qc, ""
        for suf in ("USDT", "USDC", "FDUSD", "TUSD", "USD", "VND", "BTC", "ETH", "EUR", "GBP"):
            if len(qc) > len(suf) + 1 and qc.endswith(suf) and qc[: -len(suf)] in _CRYPTO_BASES:
                base, suffix = qc[: -len(suf)], suf
                break
        if base in _CRYPTO_BASES and (suffix or len(qc) <= 6):
            sym = base + (
                suffix if suffix in ("USDT", "USDC", "FDUSD", "TUSD", "USD", "VND") else "USDT"
            )
            if suffix in ("BTC", "ETH"):
                sym = base + suffix
            score = 90 if suffix else 85
            _add(
                sym,
                "crypto",
                "Binance",
                f"{base}/quote",
                score,
                "crypto base" + (f"+{suffix}" if suffix else " (default USDT)"),
                "crypto_spot",
                {"symbols": [sym]},
            )
        # 4) named aliases (indices, commodities, sponsors)
        if qn in _ALIASES or qc in _ALIASES:
            alias = _ALIASES.get(qn, _ALIASES.get(qc))
            assert alias is not None
            sym, aclass, venue, nm, tool, args = alias
            _add(sym, aclass, venue, nm, 95, "known alias", tool, dict(args))
        # 5) raw global tickers (^GSPC, GC=F, BTC-USD ...)
        if qc in _GLOBAL_TICKERS:
            aclass = (
                "commodity"
                if re.search(r"=[A-Z]$", qc) and qc not in ("BTC-USD", "ETH-USD")
                else "global_index"
            )
            if qc in ("BTC-USD", "ETH-USD"):
                aclass = "crypto"
            _add(
                qc,
                aclass,
                "global",
                qc,
                90,
                "known global ticker",
                "yf_commodities" if aclass == "commodity" else "yf_global_indices",
                {"tickers": [qc]},
            )
        # 6) VN listing: exact > prefix > substring > name > fuzzy
        try:
            rows = await run_blocking(vn_p.listing_symbols, "symbol_resolve")
        except (ProviderUnavailable, ProviderBadData) as exc:
            rows = []
            warnings.append(f"vn listing unavailable — pattern-only: {exc}")
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            sym = str(r.get("symbol", "")).upper()
            nm = str(r.get("name", ""))
            if not sym:
                continue
            sym_n = _norm_text(sym)
            if sym_n == qc:
                _add(
                    sym,
                    "vn_equity",
                    "VN",
                    nm,
                    100,
                    "exact VN symbol",
                    "stock_overview",
                    {"symbol": sym},
                )
            elif sym_n.startswith(qc) and qc:
                _add(
                    sym,
                    "vn_equity",
                    "VN",
                    nm,
                    75,
                    "VN symbol prefix",
                    "stock_overview",
                    {"symbol": sym},
                )
            elif qc and qc in sym_n:
                _add(
                    sym,
                    "vn_equity",
                    "VN",
                    nm,
                    60,
                    "VN symbol substring",
                    "stock_overview",
                    {"symbol": sym},
                )
            elif qn and qn in _norm_text(nm):
                _add(
                    sym,
                    "vn_equity",
                    "VN",
                    nm,
                    50,
                    "company name match",
                    "stock_overview",
                    {"symbol": sym},
                )
            else:
                ratio = max(
                    difflib.SequenceMatcher(None, qn, sym_n).ratio(),
                    difflib.SequenceMatcher(None, qn, _norm_text(nm)).ratio(),
                )
                if ratio >= 0.6:
                    _add(
                        sym,
                        "vn_equity",
                        "VN",
                        nm,
                        round(25 + 35 * ratio),
                        f"fuzzy {ratio:.2f}",
                        "stock_overview",
                        {"symbol": sym},
                    )
        cands.sort(key=lambda c: (-c["score"], c["symbol"]))
        cands = cands[: max(int(limit), 1)]
        resolved = cands[0] if cands else None
        ambiguous = bool(
            cands
            and (
                (len(cands) > 1 and cands[0]["score"] - cands[1]["score"] < 15)
                or cands[0]["score"] < 60
            )
        )
        return make_envelope(
            {"query": q_raw, "resolved": resolved, "ambiguous": ambiguous, "candidates": cands},
            source="vnstock+local" if rows else "local",
            warnings=warnings,
            availability="available" if cands else "empty",
        )

    @server.tool(annotations=READ_ONLY)
    async def market_movers(top_n: int = 10, universe: str = "vn30") -> dict[str, Any]:
        """Top gainers, losers and volume leaders. Use for session pulse checks.

        top_n: rows per list. universe: 'vn30' (default, 30 liquid bluechips —
        fast and stable) or 'hose' (full HOSE ref ≤60, slow; illiquid symbols
        may hang vnstock and trip the batch timeout → partial with missing).
        """
        try:
            syms: list[str] = []
            if universe.strip().lower() == "hose":
                try:
                    syms = [str(r.get("symbol")) for r in await run_blocking(
                        functools.partial(vn_p.reference_equity, "HOSE"),
                        "market_movers",
                        timeout_secs=30.0,
                    ) if isinstance(r, dict) and r.get("symbol")][:60]
                except (ProviderUnavailable, ProviderBadData):
                    syms = []
            if not syms:
                syms = list(vn_p.VN30)
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, syms),
                "market_movers",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("market_movers", str(exc))
        rows = [q for q in quotes if isinstance(q, dict)]

        def _num(r: dict[str, Any], keys: tuple[str, ...]) -> float:
            import math

            for k in keys:
                try:
                    v = r.get(k)
                    if v is not None:
                        f = float(v)
                        if not math.isnan(f) and not math.isinf(f):
                            return f
                except (TypeError, ValueError):
                    continue
            return 0.0

        _CHG_KEYS = ("percent_change", "pct_change", "price_change", "change", "Change", "CHANGE")

        def _chg(r: dict[str, Any]) -> float:
            return _num(r, _CHG_KEYS)

        def _vol(r: dict[str, Any]) -> float:
            return _num(r, ("volume_accumulated", "volume", "Volume", "VOLUME", "vol"))

        keep = max(int(top_n), 1)
        rows, missing = vn_p.split_batch(rows)
        gainers = sorted(rows, key=_chg, reverse=True)[:keep]
        losers = sorted(rows, key=_chg)[:keep]
        volume = sorted(rows, key=_vol, reverse=True)[:keep]
        import math

        def _clean(r: dict[str, Any]) -> dict[str, Any]:
            out2 = {}
            for k, v in r.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    out2[k] = None
                else:
                    out2[k] = v
            return out2

        return make_envelope(
            {"gainers": [_clean(g) for g in gainers],
             "losers": [_clean(g) for g in losers],
             "volume_leaders": [_clean(g) for g in volume],
             "universe": len(rows), **({"missing": missing} if missing else {})},
            source="vnstock",
            warnings=[f"batch partial: {len(missing)} symbols missing"] if missing else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def breadth_scan(exchange: str | None = None) -> dict[str, Any]:
        """Advancers, decliners, ceiling and floor counts. Use to judge rally health.

        exchange: filter rows carrying venue info (HOSE/HNX/UPCOM); ignored
        with a warning when rows carry no venue info.
        """
        try:
            prices = await run_blocking(vs_p.market_price, "breadth_scan", timeout_secs=30.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            from opentrading_mcp import snapshots

            stale_rows = await run_blocking(
                functools.partial(snapshots.load, "breadth_3ex", 1),
                "breadth_scan",
                timeout_secs=10.0,
            )
            if stale_rows:
                payload = stale_rows[0].get("payload") or {}
                boards = payload.get("rows", payload) if not isinstance(payload, list) else payload
                return make_envelope(
                    {"from_snapshot": True, "exchanges": boards},
                    source="cache-stale",
                    warnings=[f"live unavailable, snapshot fallback: {exc}"],
                    availability="stale",
                )
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
        def _bchg(row: dict[str, Any]) -> float:
            try:
                return float(pick_value(row, ("change", "Change", "CHANGE")) or 0)
            except (TypeError, ValueError):
                return 0.0

        adv = sum(1 for r in rows if isinstance(r, dict) and _bchg(r) > 0)
        dec = sum(
            1
            for r in rows
            if isinstance(r, dict) and _bchg(r) < 0
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
        # P14: retry the main leg twice (1s apart) before degrading.
        for attempt in (1, 2):
            try:
                quotes = await run_blocking(
                    functools.partial(vn_p.equity_quote_batch, universe),
                    "market_overview",
                    timeout_secs=30.0,
                )
                break
            except (ProviderUnavailable, ProviderBadData) as exc:
                if attempt == 2:
                    warnings.append(f"quotes unavailable: {exc}")
                else:
                    await asyncio.sleep(1.0)
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
        {"name": "symbol_resolve"},
        {"name": "market_movers"},
        {"name": "breadth_scan"},
        {"name": "dnse_market_status"},
    ]
