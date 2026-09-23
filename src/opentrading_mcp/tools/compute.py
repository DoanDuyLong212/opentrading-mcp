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
    async def stock_forensic(symbol: str) -> dict[str, Any]:
        """M-Score and Piotroski from mirror statements. Use for earnings-quality flags."""
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
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "dsri": dsri,
                "sgi": sgi,
                "piotroski_lite": f"{score}/2",
                "flags": flags,
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def valuation_run(symbol: str, btype: int = 1) -> dict[str, Any]:
        """PER/PB ensemble with DCF-lite. Use for fair-value ranges."""
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
            if btype in (2, 3):
                out["method"] = "pb_bank_broker"
        except (TypeError, ValueError):
            pass
        return make_envelope(out, source="computed-local")

    @server.tool(annotations=READ_ONLY)
    async def fred_series(series_id: str, limit: int = 60) -> dict[str, Any]:
        """FRED observations. Use for US macro context."""
        try:
            return make_envelope(
                await _call("f", intel_p.fred_series, series_id, limit), source="fred"
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("fred_series", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def world_macro_country(iso3: str, indicator: str) -> dict[str, Any]:
        """WorldBank series per country. Use for global GDP/CPI/debt context."""
        try:
            return make_envelope(
                await _call("w", intel_p.worldbank_country, iso3, indicator), source="worldbank"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_macro_country", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def world_fear_greed() -> dict[str, Any]:
        """Crypto fear/greed index. Use for risk-appetite reads."""
        try:
            return make_envelope(await _call("f", intel_p.fear_greed), source="alternative.me")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("world_fear_greed", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def sentiment_score(symbol: str) -> dict[str, Any]:
        """Crowd sentiment from Fireant posts, Groq-scored. Use for hype risk."""
        try:
            posts = await _call("s", intel_p.fireant_posts, symbol, 20, secs=45.0)
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
        """Insider deals via vnstock Company. Use for informed-flow reads."""
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
    async def company_events(symbol: str) -> dict[str, Any]:
        """Disclosures and corporate actions. Use for event calendars."""
        try:
            docs = await _call("e", vs_p.documents, symbol)
            return make_envelope({"symbol": symbol.upper(), "events": docs}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("company_events", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def financial_statements(symbol: str, period: str = "quarter") -> dict[str, Any]:
        """Mirror statements alias (v3 compat). Use for statement reads."""
        try:
            data = await _call("f", vs_p.financeinfo, symbol, period, secs=60.0)
            return make_envelope(data, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_statements", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def financial_ratios(symbol: str) -> dict[str, Any]:
        """Overview plus vnstock ratios merged. Use for ratio screens."""
        try:
            overview = await _call("r", vs_p.overview_trading, symbol)
            return make_envelope({"symbol": symbol.upper(), "ratios": overview}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return _na("financial_ratios", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def peer_compare(symbol: str, peers: list[str]) -> dict[str, Any]:
        """Head-to-head overview rows. Use when picking tickers."""
        rows: list[dict[str, Any]] = []
        for name in [symbol, *peers][:6]:
            try:
                rows.append(await _call("p", vs_p.overview_trading, name))
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
                rows.append({"symbol": name.upper(), "error": str(exc)})
        return make_envelope({"rows": rows}, source="vietstock")

    @server.tool(annotations=READ_ONLY)
    async def signals_scan(limit: int = 10) -> dict[str, Any]:
        """Donchian breakout scan over VN30 names. Use to hunt momentum."""
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
    async def pattern_match(symbol: str, lookback: int = 60) -> dict[str, Any]:
        """Self-similarity of return windows by correlation. Use for analogies."""
        try:
            candles = await _call("p", vn_p.quote_history, symbol, lookback + 20, secs=60.0)
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("pattern_match", str(exc))
        closes = [c["c"] for c in candles if c["c"]]
        if len(closes) < lookback + 10:
            return make_envelope({"symbol": symbol.upper()}, source="vnstock", availability="empty")
        rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        cur, best, best_i = rets[-20:], -2.0, -1

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
            corr = num / den
            if corr > best:
                best, best_i = corr, i
        return make_envelope(
            {"symbol": symbol.upper(), "best_corr": round(best, 3), "offset_bars": best_i},
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def signals_trade_log() -> dict[str, Any]:
        """Local trade log. Use for label building."""
        try:
            rows = await run_blocking(_read_trade_log, "signals_trade_log", timeout_secs=10.0)
        except ProviderUnavailable as exc:
            return _na("signals_trade_log", str(exc))
        if rows is None:
            return make_envelope({"trades": []}, source="local", availability="empty")
        return make_envelope({"trades": rows}, source="local")

    @server.tool(annotations=READ_ONLY)
    async def macro_reports(symbol: str = "") -> dict[str, Any]:
        """Research PDFs metadata. Use for report discovery."""
        try:
            data = await _call("m", vs_p.reports_search, symbol)
            return make_envelope({"reports": data}, source="vietstock")
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
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
    async def event_stats(query: str = "stock market") -> dict[str, Any]:
        """GDELT event counts for a query. Use for base-rate checks."""
        try:
            return make_envelope(await _call("e", intel_p.gdelt_events, query), source="gdelt")
        except ProviderUnavailable:
            await asyncio.sleep(10)
            try:
                return make_envelope(await _call("e", intel_p.gdelt_events, query), source="gdelt")
            except (ProviderUnavailable, ProviderBadData) as exc:
                return _na("event_stats", str(exc))
        except ProviderBadData as exc:
            return _na("event_stats", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def compare_assets(assets: list[str]) -> dict[str, Any]:
        """Cross-asset last prices via yfinance. Use for allocation reads."""
        try:
            return make_envelope(
                await _call("c", yf_p.batch_last, assets[:10], secs=60.0), source="yfinance"
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("compare_assets", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def runs_list() -> dict[str, Any]:
        """Local run registry. Use to resume analysis sessions."""
        try:
            rows = await run_blocking(_read_runs, "runs_list", timeout_secs=10.0)
        except (ProviderUnavailable, ValueError) as exc:
            return _na("runs_list", f"unparseable registry: {exc}")
        if rows is None:
            return make_envelope({"runs": []}, source="local", availability="empty")
        return make_envelope({"runs": rows[-50:]}, source="local")

    @server.tool(annotations=READ_ONLY)
    async def run_get(run_id: str) -> dict[str, Any]:
        """Fetch one run by id. Use to inspect past outputs."""
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
