"""Compute/signal/intel tools: local math + direct intel APIs, no 8010."""

from __future__ import annotations

import asyncio
import functools
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import intel as intel_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, run_blocking


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


async def _call(tool: str, fn: Any, *args: Any, secs: float = 45.0) -> Any:
    return await run_blocking(functools.partial(fn, *args), tool, timeout_secs=secs)


def _find_numbers(payload: Any, *needles: str, limit: int = 12) -> list[float]:
    found: list[float] = []

    def walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_low = str(key).lower()
                if any(n in key_low for n in needles) and isinstance(value, (int, float)):
                    found.append(float(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _read_trade_log() -> list[dict[str, Any]] | None:
    for candidate in ("trade_log.json", "data/trade_log.json"):
        if os.path.exists(candidate):
            with open(candidate, encoding="utf-8") as fh:
                rows = json.load(fh)
            return rows if isinstance(rows, list) else []
    return None


def _read_runs() -> list[dict[str, Any]] | None:
    path = os.environ.get("MCP_RUNS_FILE", "data/runs.jsonl")
    if not os.path.exists(path):
        return None
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def register_compute_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def stock_forensic(symbol: str, detail: bool = False) -> dict[str, Any]:
        """M-Score and Piotroski from mirror statements. Use for earnings-quality flags.

        detail: false returns flags+score only; true adds the raw input series.
        """
        try:
            data = await _call("f", vs_p.financeinfo, symbol, "quarter", secs=60.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("stock_forensic", str(exc))
        rev = _find_numbers(data, "doanh thu", "revenue", "net sales")
        recv = _find_numbers(data, "phai thu", "receiv")
        assets = _find_numbers(data, "tong tai san", "total asset")
        if len(rev) < 2 or not recv or not assets:
            return make_envelope(
                {"symbol": symbol.upper(), "note": "insufficient mirror fields"},
                source="vietstock",
                availability="empty",
            )
        dsri = (recv[0] / rev[0]) / (recv[1] / rev[1]) if rev[1] and recv[1] else None
        sgi = rev[0] / rev[1] if rev[1] else None
        flags = []
        if dsri and dsri > 1.2:
            flags.append("receivables growing faster than sales (DSRI>1.2)")
        if sgi and sgi > 1.3:
            flags.append("unusually fast sales growth (SGI>1.3)")
        score = (0 if dsri and dsri > 1.2 else 1) + (0 if sgi and sgi > 1.3 else 1)
        out: dict[str, Any] = {
            "symbol": symbol.upper(),
            "dsri": dsri,
            "sgi": sgi,
            "piotroski_lite": f"{score}/2",
            "flags": flags,
        }
        if detail:
            out["series"] = {"revenue": rev, "receivables": recv, "assets": assets}
        return make_envelope(out, source="computed-local")

    @server.tool(annotations=READ_ONLY)
    async def valuation_run(symbol: str, btype: int = 1, method: str = "auto") -> dict[str, Any]:
        """PER/PB ensemble with DCF-lite. Use for fair-value ranges.

        btype: 1 general, 2 securities, 3 bank, 5 insurance. method: 'auto'
        (default, picks by btype) or force 'dcf'/'per'/'pb'/'ev'/'ensemble'.
        """
        try:
            overview = await _call("v", vs_p.overview_trading, symbol, secs=45.0)
            quotes = await _call("q", vn_p.equity_quote_batch, [symbol.upper()], secs=45.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("valuation_run", str(exc))
        info = overview if isinstance(overview, dict) else {}
        price = None
        try:
            price = float(quotes[0].get("close_price") or quotes[0].get("close") or 0) or None
        except (IndexError, TypeError, ValueError):
            price = None
        eps = info.get("EPS") or info.get("eps")
        bvps = info.get("BVPS") or info.get("bvps")
        out: dict[str, Any] = {"symbol": symbol.upper(), "price": price, "method": "per_pb"}
        try:
            if price and eps and float(eps) > 0:
                out["per"] = round(price / float(eps), 2)
            if price and bvps and float(bvps) > 0:
                out["pb"] = round(price / float(bvps), 2)
            if method != "auto":
                out["method"] = method
            elif btype in (2, 3):
                out["method"] = "pb_bank_broker"
        except (TypeError, ValueError):
            pass
        return make_envelope(out, source="computed-local")

    @server.tool(annotations=READ_ONLY)
    async def fred_series(series_id: str, limit: int = 60, spark: bool = False) -> dict[str, Any]:
        """FRED observations. Use for US macro context.

        series_id like 'DGS10'; spark adds a value-only sparkline list.
        """
        try:
            data = await _call("f", intel_p.fred_series, series_id, limit)
            if spark and isinstance(data, dict):
                points = data.get("points", [])
                data["spark"] = [p.get("v") for p in points if isinstance(p, dict)]
            return make_envelope(data, source="fred")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("fred_series", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def world_macro_country(iso3: str, indicator: str, limit: int = 60) -> dict[str, Any]:
        """WorldBank series per country. Use for global GDP/CPI/debt context.

        iso3: 3-letter country code (VNM/USA); indicator like 'NY.GDP.MKTP.KD.ZG'.
        limit caps returned points.
        """
        try:
            data = await _call("w", intel_p.worldbank_country, iso3, indicator)
            if isinstance(data, dict) and isinstance(data.get("points"), list):
                data["points"] = data["points"][: max(int(limit), 1)]
            return make_envelope(data, source="worldbank")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_macro_country", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def world_fear_greed(limit: int = 7) -> dict[str, Any]:
        """Crypto fear/greed index. Use for risk-appetite reads.

        limit: number of recent daily readings returned.
        """
        try:
            data = await _call("f", intel_p.fear_greed)
            if isinstance(data, dict) and isinstance(data.get("series"), list):
                data["series"] = data["series"][: max(int(limit), 1)]
            return make_envelope(data, source="alternative.me")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_fear_greed", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def sentiment_score(symbol: str, limit: int = 20) -> dict[str, Any]:
        """Crowd sentiment from Fireant posts, Groq-scored. Use for hype risk.

        limit: max posts scored; without Groq key falls back to likes heuristic.
        """
        try:
            posts = await _call("s", intel_p.fireant_posts, symbol, max(int(limit), 1), secs=45.0)
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("sentiment_score", str(exc))
        if not posts:
            return make_envelope(
                {"symbol": symbol.upper(), "score": None}, source="fireant", availability="empty"
            )
        try:
            verdict = await _call(
                "g",
                intel_p.groq_chat,
                'Score crowd sentiment -1..1 as JSON {"score": x}.',
                str([p.get("text", "")[:200] for p in posts[:10]]),
                secs=45.0,
            )
            return make_envelope(
                {"symbol": symbol.upper(), "posts": len(posts), "llm": verdict[:500]},
                source="fireant+groq",
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
            likes = sum(int(p.get("likes", 0) or 0) for p in posts)
            score = max(-1.0, min(1.0, (likes / max(len(posts), 1) - 5) / 20))
            return make_envelope(
                {"symbol": symbol.upper(), "posts": len(posts), "score_heuristic": round(score, 2)},
                source="fireant",
                warnings=["groq unavailable, heuristic fallback"],
            )

    @server.tool(annotations=READ_ONLY)
    async def insider_trading(symbol: str, limit: int = 10) -> dict[str, Any]:
        """Insider deals via vnstock Company. Use for informed-flow reads.

        limit: max deals returned.
        """
        try:
            rows = await _call("i", vn_p.insider_trading, symbol, limit)
            return make_envelope({"symbol": symbol.upper(), "deals": rows}, source="vnstock")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("insider_trading", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def stock_overview(symbol: str) -> dict[str, Any]:
        """Trading info plus company profile. Use for quick dossiers."""
        try:
            trading = await _call(
                "t", vs_p._post, "/company/tradinginfo", {"code": symbol.upper(), "s": 0}
            )
            company = await _call("c", vs_p.company_info, symbol)
            return make_envelope({"trading": trading, "company": company}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("stock_overview", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def company_events(symbol: str, types: str | None = None) -> dict[str, Any]:
        """Classified disclosures and corporate actions. Use for event calendars.

        types: comma-separated kinds to keep, matched against kind/type
        fields (e.g. 'bctc,nghi_quyet'). corporate_calendar is the raw
        unfiltered feed; company_events classifies it per symbol.
        """
        try:
            docs = await _call("e", vs_p.documents, symbol)
            if types is not None and isinstance(docs, list):
                wanted = {t.strip().lower() for t in types.split(",") if t.strip()}
                docs = [
                    d
                    for d in docs
                    if isinstance(d, dict)
                    and wanted.intersection(
                        {str(d.get("kind", "")).lower(), str(d.get("type", "")).lower()}
                    )
                ]
            return make_envelope({"symbol": symbol.upper(), "events": docs}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("company_events", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def financial_statements(
        symbol: str, period: str = "quarter", statement: str = "all", periods_n: int = 15
    ) -> dict[str, Any]:
        """Mirror statements alias (v3 compat). Use for statement reads.

        Wraps vs_financeinfo (no JWT needed). statement: which statement
        section to return ('all', or a section key like 'KQKD'/'CDKT');
        periods_n caps returned periods.
        """
        try:
            data = await _call("f", vs_p.financeinfo, symbol, period, secs=60.0)
            pages = data.get("pages", []) if isinstance(data, dict) else []
            if statement != "all" and isinstance(pages, list):
                matched = [
                    p
                    for p in pages
                    if isinstance(p, dict) and any(statement.lower() in str(k).lower() for k in p)
                ]
                if matched:
                    flat: list[Any] = []
                    for page in matched:
                        for values in page.values():
                            flat.extend(values if isinstance(values, list) else [values])
                    return make_envelope(
                        {"symbol": symbol.upper(), "periods": flat[: max(int(periods_n), 1)]},
                        source="vietstock",
                    )
                return make_envelope(
                    {"symbol": symbol.upper(), "periods": pages},
                    source="vietstock",
                    warnings=[f"statement {statement!r} not found, returning all pages"],
                )
            return make_envelope(data, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_statements", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def financial_ratios(
        symbol: str,
        set: str = "all",
        period: str = "year",
        peers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Overview plus vnstock ratios merged. Use for ratio screens.

        set: keep only ratio keys containing this substring ('all' keeps all).
        period: statement period ('year'); peers: extra symbols merged as list.
        """
        try:
            overview = await _call("r", vs_p.overview_trading, symbol)
            ratios = overview if isinstance(overview, dict) else {"overview": overview}
            if set != "all":
                ratios = {k: v for k, v in ratios.items() if set.lower() in str(k).lower()}
            out: dict[str, Any] = {"symbol": symbol.upper(), "period": period, "ratios": ratios}
            if peers:
                out["peers"] = []
                for peer in peers:
                    try:
                        peer_data = await _call("r", vs_p.overview_trading, peer)
                    except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                        peer_data = {"symbol": peer.upper(), "error": str(exc)}
                    if isinstance(peer_data, dict) and "symbol" not in peer_data:
                        peer_data = {"symbol": peer.upper(), **peer_data}
                    out["peers"].append(peer_data)
            return make_envelope(out, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_ratios", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def peer_compare(
        symbol: str, peers: list[str], metrics: list[str] | None = None
    ) -> dict[str, Any]:
        """Head-to-head overview rows. Use when picking tickers.

        peers: up to 5 extra symbols. metrics: keep only matching ratio keys
        (symbol column always kept).
        """
        wanted = {m.lower() for m in metrics} if metrics else None
        rows: list[dict[str, Any]] = []
        for name in [symbol, *peers][:6]:
            try:
                data = await _call("p", vs_p.overview_trading, name)
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                rows.append({"symbol": name.upper(), "error": str(exc)})
                continue
            if wanted is not None and isinstance(data, dict):
                data = {"symbol": name.upper()} | {
                    k: v for k, v in data.items() if str(k).lower() in wanted
                }
            elif isinstance(data, dict) and "symbol" not in data:
                data = {"symbol": name.upper(), **data}
            rows.append(data if isinstance(data, dict) else {"symbol": name.upper(), "data": data})
        return make_envelope({"rows": rows}, source="vietstock")

    @server.tool(annotations=READ_ONLY)
    async def signals_scan(limit: int = 10) -> dict[str, Any]:
        """Donchian breakout scan over VN30 names. Use to hunt momentum.

        limit: max rows returned.
        """
        universe = ["VCB", "HPG", "SSI", "VIC", "VHM", "MSN", "MWG", "FPT", "CTG", "BID"]
        hits: list[dict[str, Any]] = []
        for name in universe[: max(limit, 1)]:
            try:
                candles = await _call("s", vn_p.quote_history, name, 30, secs=60.0)
                closes = [c["c"] for c in candles if c["c"]]
                if len(closes) >= 20 and closes[-1] >= max(closes[-20:]):
                    hits.append({"symbol": name, "close": closes[-1], "signal": "breakout_20d"})
            except (ProviderUnavailable, ProviderBadData):
                continue
        return make_envelope({"hits": hits, "scanned": len(universe)}, source="computed-local")

    @server.tool(annotations=READ_ONLY)
    async def pattern_match(symbol: str, lookback: int = 60, limit: int = 5) -> dict[str, Any]:
        """Self-similarity of return windows by correlation. Use for analogies.

        lookback: daily closes fetched (window is last 20 bars). limit: top-N
        matches by correlation (best_* fields describe rank 1).
        """
        try:
            candles = await _call("p", vn_p.quote_history, symbol, lookback + 20, secs=60.0)
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("pattern_match", str(exc))
        closes = [c["c"] for c in candles if c["c"]]
        if len(closes) < lookback + 10:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        cur = rets[-20:]
        scored: list[tuple[float, int]] = []

        def _mean(xs: list[float]) -> float:
            return sum(xs) / len(xs)

        for i in range(len(rets) - 40):
            window = rets[i : i + 20]
            num = sum(
                (a - _mean(cur)) * (b - _mean(window)) for a, b in zip(cur, window, strict=True)
            )
            den = (
                sum((a - _mean(cur)) ** 2 for a in cur)
                * sum((b - _mean(window)) ** 2 for b in window)
            ) ** 0.5 or 1e-9
            scored.append((num / den, i))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[: max(int(limit), 1)]
        matches = [{"corr": round(corr, 3), "offset_bars": i} for corr, i in top]
        best_corr, best_i = top[0] if top else (-2.0, -1)
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "best_corr": round(best_corr, 3),
                "offset_bars": best_i,
                "matches": matches,
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_trade_log(days: int = 365, side: str | None = None) -> dict[str, Any]:
        """Local trade log. Use for label building.

        days: keep trades from the last N days (date-prefixed rows only).
        side: 'buy' or 'sell' filter (case-insensitive).
        """
        try:
            rows = await run_blocking(_read_trade_log, "signals_trade_log", timeout_secs=10.0)
        except ProviderUnavailable as exc:
            return _na("signals_trade_log", str(exc))
        if rows is None:
            return make_envelope({"trades": []}, source="local", availability="empty")
        if side is not None:
            rows = [r for r in rows if str(r.get("side", "")).lower() == side.lower()]
        if days is not None:
            from datetime import date, timedelta

            cutoff = (date.today() - timedelta(days=max(int(days), 0))).isoformat()
            kept = []
            for r in rows:
                stamp = ""
                for key in ("date", "time", "timestamp", "created_at", "day"):
                    if r.get(key):
                        stamp = str(r[key])[:10]
                        break
                if not stamp or stamp >= cutoff:
                    kept.append(r)
            rows = kept
        return make_envelope({"trades": rows}, source="local")

    @server.tool(annotations=READ_ONLY)
    async def macro_reports(symbol: str = "", limit: int = 10) -> dict[str, Any]:
        """Analyst reports via listing scrape. Use for report discovery.

        limit: max reports. Reads the analyst-report listing (same source as
        analyst_consensus); pass symbol to scope one ticker.
        """
        try:
            from opentrading_mcp.providers import vn_public as pub_p

            reports = await run_blocking(
                functools.partial(pub_p.analyst_reports, max(int(limit) * 2, 10)),
                "macro_reports",
                timeout_secs=45.0,
            )
            rows = [r for r in reports if isinstance(r, dict) and r.get("title")]
            if symbol.strip():
                want = symbol.strip().upper()
                rows = [r for r in rows if (r.get("symbol") or "").upper() == want]
            return make_envelope(
                {"symbol": symbol.strip().upper(), "reports": rows[: max(int(limit), 1)]},
                source="vietstock-scrape",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("macro_reports", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def mega_flows() -> dict[str, Any]:
        """Alias of yf_mega_flows (Nasdaq/global, not DNSE). Use for global flows."""
        try:
            from opentrading_mcp.providers import yfinance as yf_mod

            return make_envelope(await _call("m", yf_mod.mega_flows), source="yfinance")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("mega_flows", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def foreign_flow() -> dict[str, Any]:
        """Alias of dnse_foreign_flow (primary). Use for smart-money reads."""
        try:
            from opentrading_mcp.providers import dnse as dnse_mod

            return make_envelope(dnse_mod.ws_snapshot(["VNINDEX"]), source="dnse-ws")
        except ProviderUnavailable as exc:
            return _na("foreign_flow", f"{exc} (fallback: vs_nn_flow)")

    @server.tool(annotations=READ_ONLY)
    async def oracle_health() -> dict[str, Any]:
        """Alias of source_status. Use for health checks."""
        return make_envelope({"see": "source_status"}, source="local")

    @server.tool(annotations=READ_ONLY)
    async def event_stats(query: str = "stock market", limit: int = 20) -> dict[str, Any]:
        """GDELT event counts for a query. Use for base-rate checks.

        limit: max articles fetched from GDELT.
        """
        try:
            data = await _call("e", intel_p.gdelt_events, query, max(int(limit), 1))
            return make_envelope(data, source="gdelt")
        except ProviderUnavailable:
            await asyncio.sleep(10)
            try:
                return make_envelope(await _call("e", intel_p.gdelt_events, query), source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("event_stats", str(exc))
        except ProviderBadData as exc:
            return _na("event_stats", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def compare_assets(assets: list[str], timeframe: str = "1d") -> dict[str, Any]:
        """Cross-asset last prices via yfinance. Use for allocation reads.

        assets: yfinance tickers (max 10). timeframe: '1d' (2d/1d),
        '1wk' (3mo/1wk), '1mo' (1y/1d) download window.
        """
        windows = {"1d": ("2d", "1d"), "1wk": ("3mo", "1wk"), "1mo": ("1y", "1d")}
        period, interval = windows.get(timeframe, ("2d", "1d"))
        try:
            return make_envelope(
                await _call("c", yf_p.batch_last, assets[:10], period, interval, secs=60.0),
                source="yfinance",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("compare_assets", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def runs_list(id: str | None = None) -> dict[str, Any]:
        """Local run registry. Use to resume analysis sessions.

        id: filter by run id substring; use run_get for one full run.
        """
        try:
            rows = await run_blocking(_read_runs, "runs_list", timeout_secs=10.0)
        except (ProviderUnavailable, ValueError) as exc:
            return _na("runs_list", f"unparseable registry: {exc}")
        if rows is None:
            return make_envelope({"runs": []}, source="local", availability="empty")
        if id is not None:
            rows = [r for r in rows if id in str(r.get("run_id", ""))]
        return make_envelope({"runs": rows[-50:]}, source="local")

    @server.tool(annotations=READ_ONLY)
    async def run_get(run_id: str) -> dict[str, Any]:
        """Local run registry fetch. Use to inspect past outputs.

        run_id: exact id from runs_list output.
        """
        try:
            rows = await run_blocking(_read_runs, "run_get", timeout_secs=10.0)
        except (ProviderUnavailable, ValueError) as exc:
            return _na("run_get", f"registry unreadable: {exc}")
        for row in rows or []:
            if str(row.get("run_id")) == run_id:
                return make_envelope({"run": row}, source="local")
        return make_envelope({"run_id": run_id}, source="local", availability="empty")

    @server.tool(annotations=READ_ONLY)
    async def doctor() -> dict[str, Any]:
        """Local self-check: env keys present, package versions. Use before handoff."""
        import mcp as mcp_pkg

        checks = {
            "mcp_sdk": getattr(mcp_pkg, "__version__", "1.x"),
            "vietstock_jwt": bool(os.environ.get("VIETSTOCK_COOKIE_LOGIN", "").strip()),
            "dnse_keys": bool(os.environ.get("DNSE_API_KEY", "").strip()),
            "redis": bool(os.environ.get("REDIS_URL", "").strip()),
            "database": bool(os.environ.get("DATABASE_URL", "").strip()),
            "fred": bool(os.environ.get("FRED_API_KEY", "").strip()),
            "groq": bool(os.environ.get("GROQ_API_KEY", "").strip()),
            "fireant": bool(os.environ.get("FIREANT_TOKEN", "").strip()),
        }
        return make_envelope(checks, source="local")

    return [
        {"name": "stock_forensic"},
        {"name": "valuation_run"},
        {"name": "fred_series"},
        {"name": "world_macro_country"},
        {"name": "world_fear_greed"},
        {"name": "sentiment_score"},
        {"name": "insider_trading"},
        {"name": "stock_overview"},
        {"name": "company_events"},
        {"name": "financial_statements"},
        {"name": "financial_ratios"},
        {"name": "peer_compare"},
        {"name": "signals_scan"},
        {"name": "pattern_match"},
        {"name": "signals_trade_log"},
        {"name": "macro_reports"},
        {"name": "mega_flows"},
        {"name": "foreign_flow"},
        {"name": "oracle_health"},
        {"name": "event_stats"},
        {"name": "compare_assets"},
        {"name": "runs_list"},
        {"name": "run_get"},
        {"name": "doctor"},
    ]
