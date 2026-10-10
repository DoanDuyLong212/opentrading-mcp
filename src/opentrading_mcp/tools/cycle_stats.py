"""Cycle-stats tables: read + incremental refresh, PG-backed (P14 dbinit).

Replaces markdown-stored stats + ~/.opentrading JSON cache (deleted 2026-10-10):
single writer (these tools), normalized tables, version in cycle_meta.
Benchmark 2026-10: ~0.6s/symbol VCI delta -> batch 12/call (~10-15s).
"""

from __future__ import annotations

import functools
import math
import os
import time
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp import dbinit
from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    READ_WRITE_STATE,
    AnyContext,
    run_blocking,
)

TOOL = "cycle_stats"
MEMBERS_VERSION = "v1"
OVERLAP_N = 10
TOLERANCE = 0.005
MAX_BATCH = 15
FULL_START = "2018-01-01"
VNINDEX_START = "2011-01-01"

INDICES = [
    "VNINDEX", "VN30", "VNFIN", "VNFINLEAD", "VNMAT", "VNREAL", "VNUTI",
    "VNIT", "VNSI", "HNXINDEX", "HNX30",
]

BASKETS: dict[str, list[str]] = {
    "bank": ["VCB", "BID", "CTG", "TCB", "MBB", "ACB", "VPB", "STB", "HDB", "SHB", "OCB", "VIB", "TPB", "BVB"],
    "securities": ["SSI", "HCM", "VCI", "VND", "SHS", "BVS", "VDS", "MBS", "APG", "PSI"],
    "realestate": ["VHM", "VIC", "VRE", "NVL", "DXG", "NLG", "KDH", "KBC", "PDR", "SJS", "DIG", "ITA"],
    "oilgas": ["GAS", "BSR", "PVS", "PVD", "PVB", "PLX", "OIL", "PJT"],
    "steel": ["HPG", "HSG", "NKG", "VGS", "POM"],
    "utility": ["POW", "PC1", "NT2", "GEG", "REE", "DHP"],
    "tech": ["FPT", "CMG", "ELC"],
    "retail": ["MWG", "FRT", "DGW", "PNJ"],
    "consumer": ["VNM", "MSN", "SAB"],
    "transport": ["GMD", "HAH", "VSC"],
    "chemical": ["DGC", "DCM", "DPM"],
    "food": ["HAG", "VCF", "SFN"],
    "insurance": ["BVH"],
    "construction": ["CTD", "VCG", "CII"],
    "telecom": ["VGI"],
}

TETS = [
    "2012-01-23", "2013-02-10", "2014-01-31", "2015-02-19", "2016-02-08",
    "2017-01-28", "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12",
    "2022-02-01", "2023-01-22", "2024-02-10", "2025-01-29", "2026-02-17",
    "2027-02-06",
]

ALL_SYMBOLS = INDICES + sorted({s for v in BASKETS.values() for s in v})


def _pg() -> Any:
    from opentrading_mcp import dbinit as _d

    url = _d.db_url().strip()
    if not url:
        return None
    _d.ensure_tables()
    try:
        import psycopg

        return psycopg.connect(url, autocommit=True, connect_timeout=5)
    except Exception:
        return None


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope({"tool": tool}, source="unavailable",
                         warnings=[reason], availability="unavailable")


def _fetch_range(sym: str, start: str, end: str) -> list[dict[str, Any]]:
    try:
        from vnstock.api.quote import Quote
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    last: Exception | None = None
    for attempt in range(3):
        try:
            q = Quote(symbol=sym.upper(), source="VCI")
            df = q.history(start=start, end=end, interval="1D")
            if df is None or len(df) == 0:
                raise ValueError("empty frame")
            import pandas as _pd
            if isinstance(df.index, _pd.DatetimeIndex):
                times, recs = df.index, [r for _, r in df.iterrows()]
            else:
                tcol = "time" if "time" in df.columns else df.columns[0]
                times, recs = _pd.to_datetime(df[tcol]), [r for _, r in df.iterrows()]
            out = []
            for ts, row in zip(times, recs):
                t = str(ts)[:10]
                if len(t) != 10 or t[4] != "-":
                    raise ValueError(f"bad time {t!r}")
                out.append({"t": t, "o": float(row.get("open", 0) or 0),
                            "h": float(row.get("high", 0) or 0),
                            "l": float(row.get("low", 0) or 0),
                            "c": float(row.get("close", 0) or 0),
                            "v": float(row.get("volume", 0) or 0)})
            return sorted(out, key=lambda r: r["t"])
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise ProviderUnavailable(f"VCI fetch failed for {sym}: {last}")


def _refresh_one(conn: Any, sym: str, today: str) -> dict[str, Any]:
    sym = sym.upper()
    with conn.cursor() as cur:
        cur.execute("SELECT t, c FROM cycle_ohlcv WHERE symbol=%s ORDER BY t", (sym,))
        cached = [{"t": str(r[0]), "c": r[1]} for r in cur.fetchall()]
    if cached:
        wm_date = cached[-1]["t"]
        start = (date.fromisoformat(wm_date) - timedelta(days=20)).isoformat()
    else:
        wm_date = None
        start = VNINDEX_START if sym == "VNINDEX" else FULL_START
    fresh = _fetch_range(sym, start, today)
    fresh_by_t = {r["t"]: r for r in fresh}
    if cached:
        overlap = [r for r in cached[-OVERLAP_N:] if r["t"] in fresh_by_t]
        breached = any(
            r["c"] and abs(fresh_by_t[r["t"]]["c"] - r["c"]) / abs(r["c"]) > TOLERANCE
            for r in overlap)
        if breached or not overlap:
            full = _fetch_range(sym, VNINDEX_START if sym == "VNINDEX" else FULL_START, today)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cycle_ohlcv WHERE symbol=%s", (sym,))
                cur.executemany(
                    "INSERT INTO cycle_ohlcv(symbol,t,o,h,l,c,v) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    [(sym, r["t"], r["o"], r["h"], r["l"], r["c"], r["v"]) for r in full])
                cur.execute(
                    "INSERT INTO cycle_watermark(symbol,last_date,mode,members_version)"
                    " VALUES(%s,%s,'full_refetch',%s)"
                    " ON CONFLICT (symbol) DO UPDATE SET last_date=EXCLUDED.last_date,"
                    " mode='full_refetch', members_version=EXCLUDED.members_version",
                    (sym, full[-1]["t"], MEMBERS_VERSION))
            return {"symbol": sym, "mode": "full_refetch", "rows": len(full),
                    "reason": "overlap_breach" if breached else "no_overlap"}
    have = {r["t"] for r in cached}
    new = [r for r in fresh if r["t"] not in have and (wm_date is None or r["t"] > wm_date)]
    mode = "full_initial" if wm_date is None else "incremental"
    with conn.cursor() as cur:
        if new:
            cur.executemany(
                "INSERT INTO cycle_ohlcv(symbol,t,o,h,l,c,v) VALUES(%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT DO NOTHING",
                [(sym, r["t"], r["o"], r["h"], r["l"], r["c"], r["v"]) for r in new])
        cur.execute("SELECT MAX(t) FROM cycle_ohlcv WHERE symbol=%s", (sym,))
        last = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO cycle_watermark(symbol,last_date,mode,members_version)"
            " VALUES(%s,%s,%s,%s)"
            " ON CONFLICT (symbol) DO UPDATE SET last_date=EXCLUDED.last_date,"
            " mode=EXCLUDED.mode, members_version=EXCLUDED.members_version",
            (sym, str(last) if last else None, mode, MEMBERS_VERSION))
    return {"symbol": sym, "mode": mode, "added": len(new),
            "last": str(last) if last else None}


def _jsafe(obj: Any) -> Any:
    import math
    if isinstance(obj, dict):
        return {k: _jsafe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsafe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def register_cycle_stats_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def cycle_stats_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Staleness of cycle-stats tables. No fetch. Use first when locating market phase."""
        conn = _pg()
        if conn is None:
            return _na("cycle_stats_check", "DATABASE_URL not configured")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM cycle_meta")
                meta = dict(cur.fetchall())
                cur.execute("SELECT COUNT(*), MIN(last_date), MAX(last_date) FROM cycle_watermark")
                n, mn, mx = cur.fetchone()
            as_of = meta.get("as_of", "")
            try:
                stale = (date.today() - date.fromisoformat(as_of)).days if as_of else None
            except ValueError:
                stale = None
            return make_envelope({
                "as_of": as_of or None, "stats_version": meta.get("stats_version"),
                "members_version": meta.get("members_version", MEMBERS_VERSION),
                "days_stale": stale,
                "needs_refresh": bool(stale is not None and stale > 90),
                "cached_symbols": n,
                "cache_range": [str(mn) if mn else None, str(mx) if mx else None],
            }, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def cycle_seasonality(basket: str | None = None,
                                month: int | None = None,
                                ctx: AnyContext | None = None) -> dict[str, Any]:
        """Month seasonality per basket: mean/hit/relative-vs-VNINDEX. Omit args for full table."""
        conn = _pg()
        if conn is None:
            return _na("cycle_seasonality", "DATABASE_URL not configured")
        try:
            q = "SELECT basket, month, mean_ret, hit_rate, rel_ret, n FROM cycle_month_stats"
            cond: list[str] = []
            args: list[Any] = []
            if basket:
                cond.append("basket=%s")
                args.append(basket)
            if month:
                cond.append("month=%s")
                args.append(month)
            if cond:
                q += " WHERE " + " AND ".join(cond)
            q += " ORDER BY basket, month"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"basket": r[0], "month": r[1], "mean_ret": r[2],
                         "hit_rate": r[3], "rel_ret": r[4], "n": r[5]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def cycle_chains(pair: str | None = None,
                           ctx: AnyContext | None = None) -> dict[str, Any]:
        """Relative rotation chains (A strong -> B vs VNINDEX next month). Omit pair for full table."""
        conn = _pg()
        if conn is None:
            return _na("cycle_chains", "DATABASE_URL not configured")
        try:
            q = "SELECT pair, n_up, rel_mean, rel_hit FROM cycle_chains"
            args: list[Any] = []
            if pair:
                q += " WHERE pair=%s"
                args.append(pair)
            q += " ORDER BY rel_mean DESC"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"pair": r[0], "n_up": r[1], "rel_mean": r[2], "rel_hit": r[3]}
                        for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def cycle_turning(year: int | None = None,
                            ctx: AnyContext | None = None) -> dict[str, Any]:
        """Index peak/trough dates per year (VNINDEX/VNFIN/VNREAL/...). Omit year for full table."""
        conn = _pg()
        if conn is None:
            return _na("cycle_turning", "DATABASE_URL not configured")
        try:
            q = "SELECT year, idx, peak_date, trough_date FROM cycle_turning"
            args: list[Any] = []
            if year:
                q += " WHERE year=%s"
                args.append(year)
            q += " ORDER BY year, idx"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"year": r[0], "idx": r[1], "peak": str(r[2]) if r[2] else None,
                         "trough": str(r[3]) if r[3] else None} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def cycle_tet(basket: str | None = None,
                        ctx: AnyContext | None = None) -> dict[str, Any]:
        """Tet (Lunar New Year) effect: pre/post 5-session mean/hit per basket."""
        conn = _pg()
        if conn is None:
            return _na("cycle_tet", "DATABASE_URL not configured")
        try:
            q = ("SELECT basket, pre5_mean, pre5_hit, post5_mean, post5_hit, n"
                 " FROM cycle_tet")
            args: list[Any] = []
            if basket:
                q += " WHERE basket=%s"
                args.append(basket)
            q += " ORDER BY pre5_mean DESC"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"basket": r[0], "pre5_mean": r[1], "pre5_hit": r[2],
                         "post5_mean": r[3], "post5_hit": r[4], "n": r[5]}
                        for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_WRITE_STATE)
    async def cycle_stats_refresh(symbols: list[str],
                                  ctx: AnyContext | None = None) -> dict[str, Any]:
        """Incremental refresh a batch (max 15/call, recommend 12).

        Fetch [watermark+1, today] + 10-session overlap via VCI; overlap close
        deviation >0.5% triggers full re-fetch of that symbol. Own cache only.
        """
        from opentrading_mcp.tools.shared import run_blocking as _rb

        syms = [s.upper() for s in (symbols or [])][:MAX_BATCH]
        if not syms:
            return _na("cycle_stats_refresh", "empty symbols")
        conn = _pg()
        if conn is None:
            return _na("cycle_stats_refresh", "DATABASE_URL not configured")
        try:
            today = date.today().isoformat()
            updated, full, failed = [], [], []
            for s in syms:
                try:
                    r = await _rb(functools.partial(_refresh_one, conn, s, today),
                                  TOOL, timeout_secs=30.0)
                    (full if r.get("mode") == "full_refetch" else updated).append(r)
                except Exception as exc:  # noqa: BLE001
                    failed.append({"symbol": s, "error": str(exc)[:150]})
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM cycle_watermark")
                done = cur.fetchone()[0]
            remaining = [s for s in ALL_SYMBOLS
                         if s not in {r["symbol"] for r in updated + full}]
            # re-check watermark table for true remaining
            with conn.cursor() as cur:
                cur.execute("SELECT symbol FROM cycle_watermark")
                have = {r[0] for r in cur.fetchall()}
            return make_envelope({
                "updated": updated, "full_refetched": full, "failed": failed,
                "progress": f"{done}/{len(ALL_SYMBOLS)}",
                "remaining": [s for s in ALL_SYMBOLS if s not in have],
            }, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_WRITE_STATE)
    async def cycle_stats_finalize(extra_tet: list[str] | None = None,
                                   ctx: AnyContext | None = None) -> dict[str, Any]:
        """Recompute derived tables from cache; bump meta. Run after all batches."""
        conn = _pg()
        if conn is None:
            return _na("cycle_stats_finalize", "DATABASE_URL not configured")
        try:
            data = await run_blocking(
                functools.partial(_finalize_compute, conn, extra_tet or []),
                TOOL, timeout_secs=120.0)
            return make_envelope(data, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def cycle_yearly(basket: str | None = None,
                           year: int | None = None,
                           ctx: AnyContext | None = None) -> dict[str, Any]:
        """Yearly return % per basket. Omit args for full table."""
        conn = _pg()
        if conn is None:
            return _na("cycle_yearly", "DATABASE_URL not configured")
        try:
            q = "SELECT basket, year, ret FROM cycle_yearly"
            cond: list[str] = []
            args: list[Any] = []
            if basket:
                cond.append("basket=%s")
                args.append(basket)
            if year:
                cond.append("year=%s")
                args.append(year)
            if cond:
                q += " WHERE " + " AND ".join(cond)
            q += " ORDER BY basket, year"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"basket": r[0], "year": r[1], "ret": r[2]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="cycle_stats")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def cycle_trough_events(ctx: AnyContext | None = None) -> dict[str, Any]:
        """3M forward returns per basket after major troughs (who leads recoveries)."""
        conn = _pg()
        if conn is None:
            return _na("cycle_trough_events", "DATABASE_URL not configured")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT trough, vnindex_3m, bank, securities, realestate,"
                            " oilgas, steel, utility, tech FROM cycle_trough_events"
                            " ORDER BY trough")
                cols = ["trough", "vnindex_3m", "bank", "securities", "realestate",
                        "oilgas", "steel", "utility", "tech"]
                rows = [dict(zip(cols, [str(r[0])] + list(r[1:]))) for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="cycle_stats")
        finally:
            conn.close()

    return [
        {"name": "cycle_stats_check"},
        {"name": "cycle_seasonality"},
        {"name": "cycle_chains"},
        {"name": "cycle_turning"},
        {"name": "cycle_tet"},
        {"name": "cycle_stats_refresh"},
        {"name": "cycle_stats_finalize"},
        {"name": "cycle_yearly"},
        {"name": "cycle_trough_events"},
    ]


def _load_frame(conn: Any) -> Any:
    import pandas as pd

    with conn.cursor() as cur:
        cur.execute("SELECT symbol, t, c FROM cycle_ohlcv ORDER BY symbol, t")
        rows = cur.fetchall()
    if not rows:
        raise ProviderUnavailable("cycle_ohlcv empty — run cycle_stats_refresh first")
    closes: dict[str, Any] = {}
    for sym, t, c in rows:
        closes.setdefault(sym, {})[str(t)] = float(c)
    px = pd.DataFrame({s: pd.Series(v, dtype=float) for s, v in closes.items()})
    px.index = pd.to_datetime(px.index)
    return px.sort_index()


def _finalize_compute(conn: Any, extra_tet: list[str]) -> dict[str, Any]:
    import pandas as pd

    px = _load_frame(conn)
    if "VNINDEX" not in px.columns:
        raise ProviderUnavailable("cache missing VNINDEX")

    def basket(syms: list[str]) -> Any:
        use = [s for s in syms if s in px.columns]
        rets = px[use].pct_change(fill_method=None)
        n_ok = rets.notna().sum(axis=1)
        r = rets.mean(axis=1)
        r[n_ok < max(1, len(syms) // 3)] = float("nan")
        r.loc[r.index < pd.Timestamp("2018-10-01")] = float("nan")
        return r

    baskets = {k: basket(v) for k, v in BASKETS.items()}
    bdf = pd.DataFrame(baskets)
    bdf["VNINDEX"] = px["VNINDEX"].pct_change(fill_method=None)
    out: dict[str, Any] = {}
    mb = (1 + bdf).resample("ME").prod(min_count=1) - 1
    mb = mb[mb["VNINDEX"].notna()]
    mb.index = mb.index.to_period("M")
    mean_t = (mb.groupby(mb.index.month).mean() * 100).round(2)
    hit_t = (mb.groupby(mb.index.month).apply(
        lambda g: (g > 0).sum() / g.notna().sum() * 100).round(0))
    n_t = mb.groupby(mb.index.month).apply(lambda g: g.notna().sum())
    rel = mb.sub(mb["VNINDEX"], axis=0)
    rel_t = (rel.groupby(rel.index.month).mean() * 100).round(2)
    # rebuild tables explicitly (DELETE + INSERT keeps history clean per version)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_month_stats")
        cur.executemany(
            "INSERT INTO cycle_month_stats(basket,month,mean_ret,hit_rate,rel_ret,n)"
            " VALUES(%s,%s,%s,%s,%s,%s)",
            [(b, int(m), float(mean_t.loc[m, b]), float(hit_t.loc[m, b]),
              float(rel_t.loc[m, b]), int(n_t.loc[m, b]))
             for b in mean_t.columns for m in mean_t.index
             if mean_t.loc[m, b] == mean_t.loc[m, b]])
    return _finalize_rest(conn, bdf, mb, mean_t, hit_t, rel_t, rel, px, extra_tet)


def _finalize_rest(conn: Any, bdf: Any, mb: Any, mean_t: Any, hit_t: Any,
                   rel_t: Any, rel: Any, px: Any, extra_tet: list[str]) -> dict[str, Any]:
    import pandas as pd

    out: dict[str, Any] = {
        "range": [str(px.index.min().date()), str(px.index.max().date())]}
    rel_m = mb.sub(mb["VNINDEX"], axis=0)
    pairs = [("bank", "securities"), ("bank", "realestate"), ("bank", "oilgas"),
             ("bank", "steel"), ("securities", "bank"), ("securities", "realestate"),
             ("securities", "tech"), ("realestate", "securities"), ("realestate", "oilgas"),
             ("oilgas", "bank"), ("steel", "securities"), ("chemical", "bank"),
             ("tech", "securities"), ("bank", "consumer")]
    chains = []
    for a, b in pairs:
        for h in (1, 3):
            sig = rel_m[a].rolling(h).sum().shift(1)
            df = pd.concat([sig, rel_m[b]], axis=1, keys=["sig", "nxt"]).dropna()
            up = df[df.sig > 0.02]
            if len(up) >= 10:
                chains.append({"pair": f"{a}RS{h}m->{b}", "n_up": int(len(up)),
                               "rel_mean": round(float(up["nxt"].mean()) * 100, 2),
                               "rel_hit": round(float((up["nxt"] > 0).mean()) * 100, 1)})
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_chains")
        cur.executemany(
            "INSERT INTO cycle_chains(pair,n_up,rel_mean,rel_hit) VALUES(%s,%s,%s,%s)",
            [(c["pair"], c["n_up"], c["rel_mean"], c["rel_hit"]) for c in chains])
    out["chains_n"] = len(chains)
    # peaks / troughs per year
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_turning")
        n_turn = 0
        for c in INDICES:
            if c not in px.columns:
                continue
            s = px[c].dropna()
            for y, seg in s.groupby(s.index.year):
                cur.execute(
                    "INSERT INTO cycle_turning(year,idx,peak_date,trough_date)"
                    " VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (int(y), c, str(seg.idxmax().date()), str(seg.idxmin().date())))
                n_turn += 1
    out["turning_n"] = n_turn
    # tet
    tets = sorted(set(TETS + (extra_tet or [])))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_tet")
        n_tet = 0
        for c in bdf.columns:
            s = bdf[c].dropna()
            pre, post = [], []
            for tx in tets:
                tet = pd.Timestamp(tx)
                before = s.index[s.index < tet]
                after = s.index[s.index >= tet]
                if len(before) < 6 or len(after) < 5:
                    continue
                pre.append(float((1 + s.loc[:before[-1]].tail(6)).prod() - 1) * 100)
                post.append(float((1 + s.loc[after[0]:].head(5)).prod() - 1) * 100)
            if len(pre) >= 5:
                cur.execute(
                    "INSERT INTO cycle_tet(basket,pre5_mean,pre5_hit,post5_mean,post5_hit,n)"
                    " VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (c, round(sum(pre) / len(pre), 2),
                     round(sum(1 for x in pre if x > 0) / len(pre) * 100, 1),
                     round(sum(post) / len(post), 2),
                     round(sum(1 for x in post if x > 0) / len(post) * 100, 1),
                     len(pre)))
                n_tet += 1
    out["tet_n"] = n_tet
    # yearly
    yr = (1 + bdf).resample("YE").prod(min_count=1) - 1
    yr.index = yr.index.year
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_yearly")
        for c in yr.columns:
            for y, v in yr[c].items():
                if v == v:
                    cur.execute(
                        "INSERT INTO cycle_yearly(basket,year,ret) VALUES(%s,%s,%s)"
                        " ON CONFLICT DO NOTHING", (c, int(y), round(float(v) * 100, 1)))
    # trough events: drawdown >15% then recovery >20% -> 3M forward per basket
    vi_full = px["VNINDEX"].dropna()
    troughs_ev = []
    peak = vi_full.iloc[0]
    state, t_px, t_date = "up", None, None
    for d, v in vi_full.items():
        if v > peak:
            peak = v
            if state == "down" and t_px is not None and v / t_px - 1 >= 0.20:
                troughs_ev.append(t_date)
                t_px = None
            state = "up"
        elif v < peak * 0.85 and state == "up":
            state = "down"
        if state == "down" and (t_px is None or v < t_px):
            t_px, t_date = v, d
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_trough_events")
        for t in troughs_ev:
            if t < pd.Timestamp("2018-10-01"):
                continue
            try:
                base = vi_full.loc[:t].iloc[-1]
                fwd = bdf.loc[t + pd.Timedelta(days=1): t + pd.Timedelta(days=95)]
                if len(fwd) < 20:
                    continue
                vals = {"trough": str(t.date()),
                        "vnindex_3m": round(float(vi_full.loc[fwd.index[-1]] / base - 1) * 100, 1)}
                for c in ["bank", "securities", "realestate", "oilgas", "steel", "utility", "tech"]:
                    vals[c] = round(float((1 + fwd[c].dropna()).prod() - 1) * 100, 1)
                cur.execute(
                    "INSERT INTO cycle_trough_events(trough,vnindex_3m,bank,securities,"
                    "realestate,oilgas,steel,utility,tech)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (vals["trough"], vals["vnindex_3m"], vals["bank"], vals["securities"],
                     vals["realestate"], vals["oilgas"], vals["steel"], vals["utility"], vals["tech"]))
            except Exception:
                continue
    # meta
    today = date.today().isoformat()
    with conn.cursor() as cur:
        for k, v in [("as_of", today), ("members_version", MEMBERS_VERSION)]:
            cur.execute(
                "INSERT INTO cycle_meta(key,value) VALUES(%s,%s)"
                " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (k, v))
        cur.execute("SELECT COUNT(*) FROM cycle_watermark")
        out["cached_symbols"] = cur.fetchone()[0]
    out["as_of"] = today
    return _jsafe(out)
