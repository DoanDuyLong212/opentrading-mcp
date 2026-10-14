"""Compute infra tools: scan, pattern, snapshot, runs, doctor."""

from __future__ import annotations

import functools
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
    run_blocking,
)


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


def _fd_series(detail: dict[str, Any], include: str, exclude: str = "") -> list[float]:
    """Sum values of detail rows whose name matches include (and no exclude)."""
    if not isinstance(detail, dict):
        return []
    series: list[float] | None = None
    for row in detail.get("rows") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").lower()
        if include not in name or (exclude and exclude in name):
            continue
        values = [
            float(v) if isinstance(v, (int, float)) else 0.0 for v in (row.get("values") or [])
        ]
        if not any(values):
            continue
        if series is None:
            series = values
        else:
            series = [a + b for a, b in zip(series, values, strict=False)]
    return series or []


def _fd_pick(detail: dict[str, Any], *priority: tuple[str, str]) -> list[float]:
    """First matching (include, exclude) pair that yields a series."""
    for include, exclude in priority:
        got = _fd_series(detail, include, exclude)
        if got:
            return got
    return []


def _fd_first(detail: dict[str, Any], *needles: str) -> list[float]:
    for needle in needles:
        got = _fd_series(detail, needle)
        if got:
            return got
    return []


def register_compute_infra_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def signals_scan(
        universe: list[str] | None = None,
        exchange: str | None = None,
        max_symbols: int = 10,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Donchian-20d breakout scan. Use to hunt momentum across the market.

        Default universe: 10 bluechips. exchange='HOSE' scans the exchange
        list capped at max_symbols (P14: up to 300, semaphore 5, progress +
        truncated honest). Scanning hundreds takes minutes — cache the call.
        """
        fp = f"{universe}|{exchange}|{max_symbols}"
        hit = await cache_lookup("signals_scan", fp)
        if hit is not None:
            return hit
        capped = max(min(int(max_symbols), 300), 1)
        if universe:
            names = [u.strip().upper() for u in universe if u.strip()][:capped]
        elif exchange:
            rows = await _call("r", vn_p.reference_equity, exchange)
            pool = [str(r.get("symbol")) for r in rows if isinstance(r, dict) and r.get("symbol")]
            names = pool[:capped]
        else:
            names = ["VCB", "HPG", "SSI", "VIC", "VHM", "MSN", "MWG", "FPT", "CTG", "BID"][:capped]
        hits: list[dict[str, Any]] = []
        scanned = 0
        total = len(names)
        for name in names:
            try:
                candles = await _call("s", vn_p.quote_history, name, 30, secs=60.0)
                closes = [c["c"] for c in candles if c["c"]]
                scanned += 1
                if len(closes) >= 20 and closes[-1] >= max(closes[-20:]):
                    hits.append({"symbol": name, "close": closes[-1], "signal": "breakout_20d"})
            except (ProviderUnavailable, ProviderBadData):
                continue
            if ctx is not None and total > 20:
                await ctx.report_progress(scanned, total, name)
        data: dict[str, Any] = {"hits": hits, "scanned": scanned, "requested": total}
        if total > capped:
            data["truncated"] = True
        return await cache_store(
            "signals_scan", fp, TTL_SECONDS["overview"],
            data, source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def pattern_match(symbol: str, lookback: int = 60, limit: int = 5) -> dict[str, Any]:
        """Self-similarity of return windows by correlation. Use for analogies.

        lookback: daily closes fetched (window is last 20 bars). limit: top-N
        matches by correlation (best_* fields describe rank 1).
        """
        fp = f"{symbol}|{lookback}|{limit}"
        hit = await cache_lookup("pattern_match", fp)
        if hit is not None:
            return hit
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
        return await cache_store(
            "pattern_match", fp, TTL_SECONDS["overview"],
            {
                "symbol": symbol.upper(),
                "best_corr": round(best_corr, 3),
                "offset_bars": best_i,
                "matches": matches,
            },
            source="computed-local",
        )

    @server.tool(annotations=READ_ONLY)
    async def snapshot_history(kind: str, days: int = 90) -> dict[str, Any]:
        """Daily-snapshot history saved by the worker. Use for data that vanishes.

        kind: market_board, breadth_3ex, flows_charts (NN/prop 30d rolling),
        heatmap_gics, gold_btmc, sbv_rates, nso_releases, analyst_titles,
        macro_curated, vn30_quotes, futures_basis, documents_feed, events_feed.
        days: history depth (newest first).
        """
        from opentrading_mcp import snapshots

        rows = await run_blocking(
            functools.partial(snapshots.load, kind, days), "snapshot_history", timeout_secs=15.0
        )
        if not rows:
            return make_envelope(
                {"kind": kind, "rows": []},
                source="postgres",
                availability="empty",
            )
        return make_envelope({"kind": kind, "count": len(rows), "rows": rows}, source="postgres")

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
        {"name": "signals_scan"},
        {"name": "pattern_match"},
        {"name": "snapshot_history"},
        {"name": "runs_list"},
        {"name": "run_get"},
        {"name": "doctor"},
    ]
