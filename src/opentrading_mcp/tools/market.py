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

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.providers.store import acache_get
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
    last_bar_time,
    no_exit,
    pick_value,
    price_ttl,
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


def _num(row: dict[str, Any], keys: tuple[str, ...]) -> float:
    """First finite numeric value among keys, else 0.0."""
    import math

    for k in keys:
        try:
            v = row.get(k)
            if v is not None:
                f = float(v)
                if not math.isnan(f) and not math.isinf(f):
                    return f
        except (TypeError, ValueError):
            continue
    return 0.0


# vnstock board rows carry percent_change/price_change (there is no `change` key);
# the trailing spellings keep older upstream shapes working.
_CHG_KEYS = ("percent_change", "pct_change", "price_change", "change", "Change", "CHANGE")


def _chg(row: dict[str, Any]) -> float:
    return _num(row, _CHG_KEYS)


# Vietstock /data/marketinfo row fields (one row per exchange index).
_BREADTH_FIELDS = {
    "advancers": "up",
    "decliners": "dn",
    "unchanged": "st",
    "ceiling": "upc",
    "floor": "dnf",
}


def _board_breadth(exchange: str, raw: Any) -> dict[str, Any] | None:
    """Advance/decline counts from a marketinfo board; None when it carries none."""
    rows = (raw.get("rows") or raw.get("data")) if isinstance(raw, dict) else raw
    for row in rows if isinstance(rows, list) else []:
        if not (isinstance(row, dict) and "up" in row and "dn" in row):
            continue
        out: dict[str, Any] = {"exchange": exchange.upper()}
        for name, key in _BREADTH_FIELDS.items():
            # A missing count stays null: 0 would read as "no stock at ceiling".
            try:
                out[name] = int(row[key]) if row.get(key) is not None else None
            except (TypeError, ValueError):
                out[name] = None
        return out
    return None


def _breadth_totals(boards: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        name: sum(b.get(name) or 0 for b in boards) for name in _BREADTH_FIELDS
    }
    counted = totals["advancers"] + totals["decliners"] + totals["unchanged"]
    totals["advancers_pct"] = round(totals["advancers"] / counted * 100, 1) if counted else None
    return totals


async def _vnstock_quota() -> Any:
    """Quota info for source_status; a quota hit (vnai sys.exit) is reported, not raised."""
    try:
        return await asyncio.to_thread(no_exit, vn_p.quota_info)
    except ProviderUnavailable as exc:
        return {"error": str(exc)[:160]}


def register_market_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def market_snapshot(
        symbols: list[str] | None = None,
        as_of: str | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Toàn cảnh thị trường VN: bảng giá VN30 kèm nguồn gốc dữ liệu. Dùng khi cần bức tranh thị
            trường rộng trong một lần gọi.

        Dùng khi: hỏi "thị trường hôm nay sao", cần giá nhiều mã cùng lúc.
        Không dùng khi: chỉ cần 1 mã (dùng vn_equity_quote_batch với đúng mã đó); cần top tăng/giảm
            (dùng market_movers); cần bản tin soạn sẵn (dùng brief_build).

        symbols: các mã cần báo giá — mặc định cả rổ VN30. as_of: nhãn thời điểm yêu cầu, ghi vào
            requested_as_of (dữ liệu luôn là mới nhất).
        """
        fp = f"{','.join(symbols or [])}|{as_of}"
        hit = await cache_lookup("market_snapshot", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"market_snapshot symbols={symbols or []}")
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols or vn_p.VN30),
                "market_snapshot",
            )
            quotes, missing = vn_p.split_batch(quotes)
            data: dict[str, Any] = {"quotes": quotes}
            if as_of is not None:
                data["requested_as_of"] = as_of
            if missing:
                data["missing"] = missing
            return await cache_store(
                "market_snapshot",
                fp,
                price_ttl(),
                data,
                source="vnstock",
                warnings=[f"batch partial: {len(missing)} symbols missing"] if missing else None,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _unavailable("market_snapshot", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def source_status(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Sức khỏe từng nguồn dữ liệu + trạng thái TTL. Dùng khi nghi ngờ dữ liệu cũ hoặc tool báo
            lỗi nguồn.

        Không dùng khi: cần dữ liệu thị trường (gọi tool dữ liệu tương ứng); đây là tool chẩn đoán,
            không trả giá.
        """
        if ctx is not None:
            await ctx.log("debug", "source_status check")
        else:
            _log_stderr("source_status check (no MCP context)")
        hit = await cache_lookup("source_status", "-")
        if hit is not None:
            return hit
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
        return await cache_store(
            "source_status",
            "-",
            TTL_SECONDS["market"],  # 60s: diagnostic, never a trading input
            {
                "upstreams": {
                    "vietstock": vs_p.auth_status(),
                    "vnstock": vnstock_state,
                    # First use imports vnstock (seconds of CPU): never on the event loop.
                    "vnstock_quota": await _vnstock_quota(),
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
        """Nến OHLCV theo ngày cho NHIỀU mã, mỗi mã một request. Dùng khi cần dữ liệu vẽ nhiều đồ
            thị cùng lúc.

        Dùng khi: so sánh nhiều mã, chuẩn bị context nhiều chart.
        Không dùng khi: chỉ 1 mã (dùng vn_quote_history — sâu hơn, tới 365 nến, có 1W/1M); cần nến
            phút/intraday (dùng vn_equity_ohlcv).

        days: số nến ngày mỗi mã (tối đa 100 mã). summary/columns: summary chỉ trả
            {count,last,high,low}; columns giữ lại trường nêu tên.
        """
        fp = f"{','.join(symbols or [])}|{days}|{summary}|{columns}"
        hit = await cache_lookup("market_candles_batch", fp)
        if hit is not None:
            return hit
        capped = symbols[:100]
        warnings: list[str] = []
        if len(symbols) > 100:
            warnings.append(f"capped 100 symbols, {len(symbols) - 100} dropped")
        total = max(len(capped), 1)
        series: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        last_t: str | None = None
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
                t = last_bar_time(candles)
                if t is not None and (last_t is None or t > last_t):
                    last_t = t
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
        return await cache_store(
            "market_candles_batch",
            f"{','.join(capped)}|{days}|{summary}|{columns}",
            price_ttl(),
            {"series": series, "missing": missing},
            source="vnstock",
            availability=availability,
            warnings=warnings,
            data_time=last_t,
        )

    @server.tool(annotations=READ_ONLY)
    async def symbol_lookup(
        query: str, limit: int = 10, offset: int = 0
    ) -> dict[str, Any]:
        """Tra tên công ty ra mã, sàn và ngành. Dùng TRƯỚC mọi lệnh theo mã khi chưa chắc mã chính
            xác.

        Dùng khi: user nêu tên công ty ("Hòa Phát") mà chưa rõ mã.
        Không dùng khi: đã biết mã (gọi thẳng tool cần); mã không phải cổ phiếu VN như vàng, USD,
            BTC hay chỉ số thế giới (dùng symbol_resolve).

        limit/offset: phân trang kết quả (khớp theo mã hoặc tên công ty, không phân biệt hoa
            thường/dấu).
        """
        fp = f"{query}|{limit}|{offset}"
        hit = await cache_lookup("symbol_lookup", fp)
        if hit is not None:
            return hit
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
        return await cache_store(
            "symbol_lookup", fp, TTL_SECONDS["categories"],
            {"hits": items}, source="vnstock", page=page,
        )

    # ---- symbol_resolve: multi-asset resolver (local tables + VN listing) ----
    @server.tool(annotations=READ_ONLY)
    async def symbol_resolve(query: str, limit: int = 5) -> dict[str, Any]:
        """Giải mã BẤT KỲ mã tài sản nào ra symbol + loại tài sản + tool tiếp theo. Dùng ĐẦU TIÊN
            khi không chắc mã thuộc loại nào.

        Dùng khi: mã lạ ("BTC", "USD", "VNI", "vàng SJC") — gồm cổ phiếu VN, crypto, forex, chỉ số,
            phái sinh, vàng/dầu. Trả ứng viên xếp hạng kèm thứ tự fallback; ambiguous=true nghĩa là
            hỏi user hoặc thử #1 rồi #2.
        Không dùng khi: đã rõ là cổ phiếu VN (dùng symbol_lookup nhanh hơn).
        """
        fp = f"{query}|{limit}"
        hit = await cache_lookup("symbol_resolve", fp)
        if hit is not None:
            return hit
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
        return await cache_store(
            "symbol_resolve",
            f"{query}|{limit}",
            TTL_SECONDS["categories"],
            {"query": q_raw, "resolved": resolved, "ambiguous": ambiguous, "candidates": cands},
            source="vnstock+local" if rows else "local",
            warnings=warnings,
            availability="available" if cands else "empty",
        )

    @server.tool(annotations=READ_ONLY)
    async def market_movers(top_n: int = 10, universe: str = "vn30") -> dict[str, Any]:
        """Top tăng/giảm mạnh và dẫn đầu thanh khoản. Dùng khi kiểm tra nhịp phiên (mã nào đang
            chạy, dòng tiền ở đâu).

        Dùng khi: hỏi "mã nào tăng mạnh hôm nay", "dòng tiền đang ở đâu".
        Không dùng khi: cần đếm mã tăng/giảm toàn sàn (dùng breadth_scan); cần context gộp nhiều
            chân cho bản tin (dùng market_overview).

        top_n: số dòng mỗi bảng. universe: 'vn30' (mặc định, 30 bluechip — nhanh, ổn định) hoặc
            'hose' (cả sàn ≤60 mã, chậm; mã kém thanh khoản có thể treo → trả partial kèm missing).
        """
        fp = f"{top_n}|{universe}"
        hit = await cache_lookup("market_movers", fp)
        if hit is not None:
            return hit
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

        return await cache_store(
            "market_movers",
            fp,
            price_ttl(),
            {"gainers": [_clean(g) for g in gainers],
             "losers": [_clean(g) for g in losers],
             "volume_leaders": [_clean(g) for g in volume],
             "universe": len(rows), **({"missing": missing} if missing else {})},
            source="vnstock",
            warnings=[f"batch partial: {len(missing)} symbols missing"] if missing else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def breadth_scan(exchange: str | None = None) -> dict[str, Any]:
        """Đếm mã tăng/giảm/đứng/trần/sàn theo từng sàn. Dùng khi đánh giá sức khỏe đợt tăng (tăng
            có lan tỏa hay chỉ vài trụ kéo).

        Dùng khi: hỏi "độ rộng thị trường", "đợt tăng này có chắc không".
        Không dùng khi: chỉ cần top 3-5 mã tăng/giảm (dùng market_movers — nhẹ hơn); cần context gộp
            cho bản tin (dùng market_overview).

        exchange: HOSE/HNX/UPCOM; bỏ trống để lấy cả 3 sàn và tổng. Số đếm lấy từ bảng thông tin
            sàn của Vietstock: advancers/decliners/unchanged là số mã tăng/giảm/đứng giá,
            ceiling/floor là số mã trần/sàn; advancers_pct = advancers / (tăng + giảm + đứng).
        """
        venues = list(vs_p.EXCHANGE_TYPE_IDS)
        if exchange is not None and exchange.strip():
            venue = exchange.strip().upper()
            if venue not in vs_p.EXCHANGE_TYPE_IDS:
                return _unavailable(
                    "breadth_scan", f"unknown exchange {exchange!r} (HOSE|HNX|UPCOM)"
                )
            venues = [venue]
        fp = "v2|" + ",".join(venues)  # v2: per-exchange marketinfo counts
        hit = await cache_lookup("breadth_scan", fp)
        if hit is not None:
            return hit
        boards: list[dict[str, Any]] = []
        failed: list[str] = []
        for venue in venues:
            try:
                raw = await run_blocking(
                    functools.partial(vs_p.market_info_board, venue),
                    "breadth_scan",
                    timeout_secs=30.0,
                )
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                failed.append(f"{venue}: {exc}")
                continue
            board = _board_breadth(venue, raw)
            if board is None:
                failed.append(f"{venue}: board carries no advance/decline counts")
                continue
            boards.append(board)
        if not boards:
            from opentrading_mcp import snapshots

            try:
                stale_rows = await run_blocking(
                    functools.partial(snapshots.load, "breadth_3ex", 1),
                    "breadth_scan",
                    timeout_secs=10.0,
                )
            except ProviderUnavailable:
                stale_rows = []
            payload = stale_rows[0].get("payload") if stale_rows else None
            # The worker saves [HOSE, HNX, UPCOM] boards in this order.
            stale = [
                b
                for b in (
                    _board_breadth(v, raw)
                    for v, raw in zip(
                        vs_p.EXCHANGE_TYPE_IDS,
                        payload if isinstance(payload, list) else [],
                        strict=False,
                    )
                )
                if b is not None and b["exchange"] in venues
            ]
            if stale:
                return make_envelope(
                    {
                        **_breadth_totals(stale),
                        "exchanges": stale,
                        "from_snapshot": True,
                        "snapshot_date": stale_rows[0].get("date"),
                    },
                    source="cache-stale",
                    warnings=[f"live unavailable, snapshot fallback: {'; '.join(failed)}"],
                    availability="stale",
                )
            return _unavailable("breadth_scan", "; ".join(failed) or "no breadth data")
        return await cache_store(
            "breadth_scan",
            fp,
            price_ttl(),
            {**_breadth_totals(boards), "exchanges": boards},
            source="vietstock",
            warnings=[f"exchange unavailable: {f}" for f in failed] or None,
            availability="partial" if failed else None,
        )

    @server.tool(annotations=READ_ONLY)
    async def market_overview(top_n: int = 3, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Context thị trường một lần gọi: giá bluechip, movers, độ rộng, phiên. Dùng cho bản tin và
            câu hỏi tổng quan.

        Dùng khi: hỏi "thị trường hôm nay sao", cần mọi thứ trong một gọi.
        Không dùng khi: cần độ rộng TOÀN sàn Vietstock (dùng breadth_scan — overview chỉ đếm rổ
            bluechip); cần rổ VN30 đầy đủ (dùng market_snapshot); cần nến lịch sử (dùng
            market_candles_batch).

        top_n: số dòng tăng/giảm mỗi bảng. Các chân suy yếu độc lập: chân chết trả null kèm cảnh
            báo.
        """
        fp = f"{top_n}"
        hit = await cache_lookup("market_overview", fp)
        if hit is not None:
            return hit
        universe = ["VCB", "HPG", "SSI", "VIC", "VHM", "MSN"]
        warnings: list[str] = []
        quotes: list[dict[str, Any]] | None = None
        # Single attempt: slow-timeout legs fail fast via the negative cache
        # instead of paying the 30s leg twice (1s apart) on every miss.
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, universe),
                "market_overview",
                timeout_secs=30.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            warnings.append(f"quotes unavailable: {exc}")
        rows, missing = vn_p.split_batch([q for q in (quotes or []) if isinstance(q, dict)])
        if missing:
            warnings.append(f"batch partial: {len(missing)} symbols missing")
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
        return await cache_store(
            "market_overview",
            fp,
            price_ttl(),
            data, source="vnstock+dnse", warnings=warnings, availability=availability
        )

    @server.tool(annotations=READ_ONLY)
    async def dnse_market_status() -> dict[str, Any]:
        """Trạng thái phiên DNSE kèm snapshot chỉ số mới nhất. Dùng khi kiểm tra phiên đang mở hay
            đóng.

        Không dùng khi: cần giá VN30 đầy đủ (dùng market_snapshot); cần context gộp cho bản tin
            (dùng market_overview).
        """
        hit = await cache_lookup("dnse_market_status", "-")
        if hit is not None:
            return hit
        try:
            snap = dnse_p.ws_snapshot(["VNINDEX", "VN30", "VN30F1M"])
            return await cache_store(
                "dnse_market_status", "-", price_ttl(), snap, source="dnse-ws"
            )
        except ProviderUnavailable:
            pass
        try:
            trades = await run_blocking(
                functools.partial(dnse_p.latest_trade, ["VN30F1M"]),
                "dnse_market_status",
                timeout_secs=30.0,
            )
            return await cache_store(
                "dnse_market_status", "-", price_ttl(),
                {"rest": trades}, source="dnse-rest",
            )
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
