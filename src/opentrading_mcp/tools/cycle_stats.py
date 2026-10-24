"""Cycle-stats tables: read + incremental refresh, PG-backed (P14 dbinit).

Replaces markdown-stored stats + ~/.opentrading JSON cache (deleted 2026-10-10):
single writer (these tools), normalized tables, version in cycle_meta.
Benchmark 2026-10: ~0.6s/symbol VCI delta -> batch 12/call (~10-15s).
"""

from __future__ import annotations

import functools
import json
import math
import time
import unicodedata
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp import dbinit
from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools import cycle_db as db
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    READ_WRITE_STATE,
    AnyContext,
)
from opentrading_mcp.tools.shared import (
    run_blocking as _run_blocking,
)


async def run_blocking(fn, tool, timeout_secs=60.0):
    """Compute-module alias: all blocking work here rides the heavy pool."""
    return await _run_blocking(fn, tool, timeout_secs, heavy=True)

TOOL = "cycle_stats"
MEMBERS_VERSION = "v2"
TROUGH_RULE_VERSION = "1"
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
    "insurance": ["BVH", "PVI", "BIC", "MIG", "BMI", "VNR"],
    # v2: VIC/VHM/VRE moved to `vin`; ITA dropped (suspended 2024-09-25).
    "realestate": ["NVL", "DXG", "NLG", "KDH", "KBC", "PDR", "SJS", "DIG", "TCH", "HDC", "CEO", "CRE"],
    # v2: Vin ecosystem as its own basket (VPL listed 2025-05-13; VIC/VHM/VRE carry history).
    "vin": ["VIC", "VHM", "VRE", "VPL"],
    "construction": ["CTD", "VCG", "CII", "HBC", "HHV", "FCN", "LCG", "DPG"],
    # v2: POM dropped (trading gaps); SMC/TLH added.
    "steel": ["HPG", "HSG", "NKG", "VGS", "SMC", "TLH"],
    "chemical": ["DGC", "DCM", "DPM", "DDV", "LAS", "BFC", "CSV"],
    "oilgas": ["GAS", "BSR", "PVS", "PVD", "PVB", "PLX", "OIL", "PJT"],
    "utility": ["POW", "PC1", "NT2", "GEG", "REE", "DHP", "QTP", "VSH", "SJD", "CHP"],
    # v2: telecom merged into tech (VGI/FOX/ICT join FPT/CMG/ELC/SGT).
    "tech": ["FPT", "CMG", "ELC", "SGT", "VGI", "FOX", "ICT"],
    "retail": ["MWG", "FRT", "DGW", "PNJ", "PET"],
    "consumer": ["VNM", "MSN", "SAB", "KDC", "MCM"],
    # v2: SFN dropped (stale since 2026-09-24); 7 names added.
    "food": ["HAG", "VCF", "PAN", "SBT", "QNS", "LSS", "DBC", "MML", "ANV"],
    "transport": ["GMD", "HAH", "VSC", "PVT", "VOS", "SGP", "MVN", "VTO"],
}

# Relative-strength chains (A strong -> B vs VNINDEX next month), 1M and 3M horizons.
CHAIN_PAIRS: list[tuple[str, str]] = [
    ("bank", "securities"), ("bank", "realestate"), ("bank", "oilgas"),
    ("bank", "steel"), ("securities", "bank"), ("securities", "realestate"),
    ("securities", "tech"), ("realestate", "securities"), ("realestate", "oilgas"),
    ("oilgas", "bank"), ("steel", "securities"), ("chemical", "bank"),
    ("tech", "securities"), ("bank", "consumer"),
    # v2: Vin ecosystem chains (split out of realestate).
    ("bank", "vin"), ("vin", "realestate"), ("realestate", "vin"),
]

# Baskets tracked after major market troughs (cycle_trough_events columns).
TROUGH_BASKETS = ["bank", "securities", "realestate", "oilgas", "steel", "utility", "tech", "vin"]


def _fold(s: str) -> str:
    """Lowercase, strip diacritics, collapse to words (for basket names)."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("đ", "d").replace("Đ", "D").lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


BASKET_ALIASES: dict[str, str] = {
    **{key: key for key in BASKETS},
    "ngan hang": "bank",
    "chung khoan": "securities", "ck": "securities",
    "bao hiem": "insurance",
    "bat dong san": "realestate", "bds": "realestate", "dia oc": "realestate",
    "ho vin": "vin", "vingroup": "vin", "vin group": "vin",
    "xay dung": "construction", "dau tu cong": "construction",
    "thep": "steel", "gang thep": "steel",
    "hoa chat": "chemical", "phan bon": "chemical",
    "dau khi": "oilgas", "nang luong": "oilgas",
    "dien": "utility", "tien ich": "utility", "dien nuoc": "utility",
    "cntt": "tech", "cong nghe": "tech", "cong nghe thong tin": "tech",
    "vien thong": "tech", "tmt": "tech", "cntt vien thong": "tech",
    "ban le": "retail",
    "tieu dung": "consumer", "hang tieu dung": "consumer",
    "thuc pham": "food", "nong nghiep": "food",
    "van tai": "transport", "logistics": "transport",
}


def _canon_basket(name: str | None) -> str | None:
    """Accept English keys and folded Vietnamese names; unknown names pass through."""
    if name is None or not str(name).strip():
        return None
    raw = str(name).strip()
    return BASKET_ALIASES.get(_fold(raw), raw)

TETS = [
    "2012-01-23", "2013-02-10", "2014-01-31", "2015-02-19", "2016-02-08",
    "2017-01-28", "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12",
    "2022-02-01", "2023-01-22", "2024-02-10", "2025-01-29", "2026-02-17",
    "2027-02-06",
]

ALL_SYMBOLS = INDICES + sorted({s for v in BASKETS.values() for s in v})


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
            for ts, row in zip(times, recs, strict=False):
                t = str(ts)[:10]
                if len(t) != 10 or t[4] != "-":
                    raise ValueError(f"bad time {t!r}")
                out.append({"t": t, "o": float(row.get("open", 0) or 0),
                            "h": float(row.get("high", 0) or 0),
                            "l": float(row.get("low", 0) or 0),
                            "c": float(row.get("close", 0) or 0),
                            "v": float(row.get("volume", 0) or 0)})
            return sorted(out, key=lambda r: r["t"])
        except Exception as exc:
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
    if isinstance(obj, dict):
        return {k: _jsafe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsafe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _filters(base: str, conds: list[tuple[str, Any]], order: str) -> tuple[str, list[Any]]:
    used = [(c, v) for c, v in conds if v not in (None, "")]
    sql = base + (" WHERE " + " AND ".join(f"{c}=%s" for c, _ in used) if used else "") + f" ORDER BY {order}"
    return sql, [v for _, v in used]


def _remaining() -> tuple[int, list[str]]:
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM cycle_watermark")
            have = {r[0] for r in cur.fetchall()}
        return len(have), [s for s in ALL_SYMBOLS if s not in have]
    finally:
        conn.close()


def register_cycle_stats_tools(server: FastMCP) -> list[dict[str, Any]]:
    src = "cycle_stats"

    @server.tool(annotations=READ_ONLY)
    async def cycle_stats_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Staleness of cycle-stats tables. No fetch. Use first when locating market phase."""
        return await db.check_freshness(
            "cycle_stats_check", src, "cycle_meta", "SELECT COUNT(*) FROM cycle_watermark",
            {"members_version": MEMBERS_VERSION},
            expect_meta={"members_version": MEMBERS_VERSION},
        )

    @server.tool(annotations=READ_ONLY)
    async def cycle_seasonality(basket: str | None = None,
                                month: int | None = None,
                                ctx: AnyContext | None = None) -> dict[str, Any]:
        """Month seasonality per basket from the stored table (mean/hit/relative vs VNINDEX). Omit args for full table.

        Baskets: bank, securities, insurance, realestate, vin, construction, steel,
        chemical, oilgas, utility, tech, retail, consumer, food, transport; Vietnamese
        names without diacritics work too ("bất động sản", "dầu khí", "CNTT"...).

        Differs from `seasonality` (one symbol, computed live from candles): this is the
        long-run basket table; quote which one a number came from.
        """
        sql, args = _filters("SELECT basket, month, mean_ret, hit_rate, rel_ret, n FROM cycle_month_stats",
                             [("basket", _canon_basket(basket)), ("month", month)], "basket, month")
        return await db.read_rows("cycle_seasonality", src, sql, args,
                                  ["basket", "month", "mean_ret", "hit_rate", "rel_ret", "n"], bool(args))

    @server.tool(annotations=READ_ONLY)
    async def cycle_chains(pair: str | None = None,
                           ctx: AnyContext | None = None) -> dict[str, Any]:
        """Relative rotation chains (A strong -> B vs VNINDEX next month). Omit pair for full table."""
        sql, args = _filters("SELECT pair, n_up, rel_mean, rel_hit FROM cycle_chains",
                             [("pair", pair)], "rel_mean DESC")
        return await db.read_rows("cycle_chains", src, sql, args, ["pair", "n_up", "rel_mean", "rel_hit"], bool(args))

    @server.tool(annotations=READ_ONLY)
    async def cycle_turning(year: int | None = None,
                            ctx: AnyContext | None = None) -> dict[str, Any]:
        """Each calendar year's highest/lowest close date per index (year to date for the current year)."""
        sql, args = _filters("SELECT year, idx, peak_date, trough_date FROM cycle_turning",
                             [("year", year)], "year, idx")
        return await db.read_rows("cycle_turning", src, sql, args, ["year", "idx", "peak", "trough"], bool(args))

    @server.tool(annotations=READ_ONLY)
    async def cycle_tet(basket: str | None = None,
                        ctx: AnyContext | None = None) -> dict[str, Any]:
        """Tet (Lunar New Year) effect per basket: compounded return over the 6 sessions before / 5 after.

        Basket names as in cycle_seasonality (Vietnamese names without diacritics accepted).
        """
        sql, args = _filters("SELECT basket, pre5_mean, pre5_hit, post5_mean, post5_hit, n FROM cycle_tet",
                             [("basket", _canon_basket(basket))], "pre5_mean DESC")
        return await db.read_rows("cycle_tet", src, sql, args,
                                  ["basket", "pre5_mean", "pre5_hit", "post5_mean", "post5_hit", "n"], bool(args))

    @server.tool(annotations=READ_ONLY)
    async def cycle_yearly(basket: str | None = None,
                           year: int | None = None,
                           ctx: AnyContext | None = None) -> dict[str, Any]:
        """Yearly return % per VN sector basket (bank, securities, realestate, vin, steel, tech...); ranks sectors by year (current year = year to date). Omit args for full table.

        Basket names as in cycle_seasonality (Vietnamese names without diacritics accepted).
        is_partial_year: the running year, or a basket whose data ends before the
        market's last session of that year — its return is not a full-year figure.
        data_through is the basket's own last session in that year.
        """
        cols = ["basket", "year", "ret", "is_partial_year", "data_through", "period_basis"]
        sql, args = _filters(f"SELECT {', '.join(cols)} FROM cycle_yearly",
                             [("basket", _canon_basket(basket)), ("year", year)], "basket, year")
        return await db.read_rows("cycle_yearly", src, sql, args, cols, bool(args))

    @server.tool(annotations=READ_ONLY)
    async def cycle_trough_events(ctx: AnyContext | None = None) -> dict[str, Any]:
        """3M forward returns per VN sector basket after major market troughs (which sectors lead recoveries).

        Each row names the day the event became knowable (confirmation, after the
        trough) and how much of the 95-day window actually existed when the table
        was built: window_complete=false rows are provisional, not finished 3M
        studies. rule carries the thresholds and requires_future_data=true — a
        trough event is never a signal known at the trough itself.
        """
        cols = ["trough", "confirmation", "window_start", "window_end", "window_days",
                "window_observations", "window_complete", "basket_observations",
                "vnindex_3m", *TROUGH_BASKETS]
        out = await db.read_rows("cycle_trough_events", src,
                                 f"SELECT {', '.join(cols)} FROM cycle_trough_events ORDER BY trough",
                                 [], cols)
        rule: dict[str, Any] = {}
        try:
            meta = await db.in_thread(
                functools.partial(db._select, "SELECT key, value FROM cycle_meta", []))
            rule = {k: v for k, v in meta if k.startswith("trough_")}
        except Exception:
            rule = {}
        for row in out.get("data", {}).get("rows", []):
            raw = row.get("basket_observations")
            if isinstance(raw, str) and raw:
                try:
                    row["basket_observations"] = json.loads(raw)
                except ValueError:
                    pass
        if rule and out.get("data") is not None:
            out["data"]["rule"] = rule
        return out

    tools = [
        {"name": "cycle_stats_check"},
        {"name": "cycle_seasonality"},
        {"name": "cycle_chains"},
        {"name": "cycle_turning"},
        {"name": "cycle_tet"},
        {"name": "cycle_yearly"},
        {"name": "cycle_trough_events"},
    ]
    if not db.writes_enabled():
        return tools

    @server.tool(annotations=READ_WRITE_STATE)
    async def cycle_stats_refresh(symbols: list[str],
                                  ctx: AnyContext | None = None) -> dict[str, Any]:
        """Incremental refresh a batch (max 15/call, recommend 12) of the tracked symbols.

        Fetch [watermark+1, today] + 10-session overlap via VCI; overlap close
        deviation >0.5% triggers full re-fetch of that symbol. Each symbol is written in
        its own transaction. One refresh at a time.
        """
        asked = [s.strip().upper() for s in (symbols or []) if s.strip()]
        unknown = [s for s in asked if s not in ALL_SYMBOLS]
        syms = [s for s in asked if s in ALL_SYMBOLS][:MAX_BATCH]
        if not syms:
            return db.na("cycle_stats_refresh", f"no tracked symbols (unknown: {', '.join(unknown) or 'none'})")

        async def work() -> dict[str, Any]:
            today = date.today().isoformat()
            updated: list[dict[str, Any]] = []
            full: list[dict[str, Any]] = []
            failed: list[dict[str, Any]] = []
            for s in syms:
                try:
                    r = await run_blocking(functools.partial(db.transactional, _refresh_one, s, today),
                                           TOOL, timeout_secs=60.0)
                    (full if r.get("mode") == "full_refetch" else updated).append(r)
                except Exception as exc:
                    failed.append({"symbol": s, "error": str(exc)[:150]})
            try:
                done, remaining = await db.in_thread(_remaining)
            except db.DbUnavailable as exc:
                return db.na("cycle_stats_refresh", str(exc))
            return make_envelope({
                "updated": updated, "full_refetched": full, "failed": failed,
                "unknown_symbols": unknown,
                "progress": f"{done}/{len(ALL_SYMBOLS)}",
                "remaining": remaining,
            }, source="cycle_stats")

        return await db.guarded_write("cycle_stats_refresh", work)

    @server.tool(annotations=READ_WRITE_STATE)
    async def cycle_stats_finalize(extra_tet: list[str] | None = None,
                                   ctx: AnyContext | None = None) -> dict[str, Any]:
        """Recompute derived tables from cache in one transaction; bump meta. Run after all batches."""

        async def work() -> dict[str, Any]:
            try:
                data = await run_blocking(
                    functools.partial(db.transactional, _finalize_compute, extra_tet or []),
                    TOOL, timeout_secs=180.0)
            except db.DbUnavailable as exc:
                return db.na("cycle_stats_finalize", str(exc))
            return make_envelope(data, source="cycle_stats")

        return await db.guarded_write("cycle_stats_finalize", work)

    return [*tools, {"name": "cycle_stats_refresh"}, {"name": "cycle_stats_finalize"}]


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


def _complete_months(monthly: Any, today: date | None = None) -> Any:
    """Drop the trailing month while it is still running.

    A refresh on 23/10 made October a 3-week return that then sat in the October
    averages next to whole months. Only the current calendar month is dropped: a past
    month counts even if its last session fell before the month-end date.
    """
    import pandas as pd

    if len(monthly) == 0:
        return monthly
    if today is None:
        # VN calendar, not the server's (UTC on Render): at 01:00 VN on the 1st, UTC is
        # still the previous month and would drop a finished month.
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    current = pd.Timestamp(today).to_period("M")
    last = monthly.index[-1]
    last_period = last if isinstance(last, pd.Period) else pd.Timestamp(last).to_period("M")
    return monthly.iloc[:-1] if last_period >= current else monthly


def _major_troughs(closes: Any) -> list[Any]:
    """(trough date, confirmation date) pairs for major troughs: a fall of more
    than 15% from the running peak, followed by a recovery to a new peak at
    least 20% above the trough.

    The confirmation date is the day the recovery makes that new peak — the
    first day the event is knowable; it always lies after the trough (the rule
    reads future data, see cycle_meta.trough_requires_future_data).

    A new peak always closes the drawdown. Before, a new peak reached with less than a
    20% rebound kept the old trough, so a later, higher trough was never recorded and
    the event was dated at the stale one.
    """
    events: list[Any] = []
    if len(closes) == 0:
        return events
    peak = closes.iloc[0]
    state, t_px, t_date = "up", None, None
    for d, v in closes.items():
        if v > peak:
            peak = v
            if state == "down" and t_px is not None and v / t_px - 1 >= 0.20:
                events.append((t_date, d))
            t_px, t_date = None, None
            state = "up"
        elif v < peak * 0.85 and state == "up":
            state = "down"
        if state == "down" and (t_px is None or v < t_px):
            t_px, t_date = v, d
    return events


def _finalize_compute(conn: Any, extra_tet: list[str]) -> dict[str, Any]:
    import pandas as pd

    # The rebuild stamps members_version: never stamp a version whose schema
    # (e.g. the cycle_trough_events.vin migration) could not be ensured.
    if not dbinit.ensure_tables():
        raise ProviderUnavailable("cycle schema ensure failed — refusing to rebuild/stamp tables")

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
    mb = (1 + bdf).resample("ME").prod(min_count=1) - 1
    mb = mb[mb["VNINDEX"].notna()]
    mb.index = mb.index.to_period("M")
    mb = _complete_months(mb)
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
    chains = []
    for a, b in CHAIN_PAIRS:
        for h in (1, 3):
            sig = rel_m[a].rolling(h).sum().shift(1)
            df = pd.concat([sig, rel_m[b]], axis=1, keys=["sig", "nxt"]).dropna()
            up = df[df.sig > 0.02]
            if len(up) >= 10:
                chains.append({"pair": f"{a}RS{h}m->{b}", "n_up": len(up),
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
    current_year = date.today().year
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_yearly")
        for c in yr.columns:
            s = bdf[c].dropna()
            for y, v in yr[c].items():
                if v == v:
                    through = s[s.index.year == int(y)].index.max()
                    market_end = px.index[px.index.year == int(y)].max()
                    partial = (
                        int(y) == current_year
                        or pd.isna(through)
                        or (not pd.isna(market_end) and through < market_end)
                    )
                    basis = (
                        "year_to_date" if int(y) == current_year
                        else ("calendar_year" if not partial else "calendar_year_partial")
                    )
                    cur.execute(
                        "INSERT INTO cycle_yearly(basket,year,ret,is_partial_year,"
                        " data_through,period_basis) VALUES(%s,%s,%s,%s,%s,%s)"
                        " ON CONFLICT DO NOTHING",
                        (c, int(y), round(float(v) * 100, 1), partial,
                         str(through.date()) if not pd.isna(through) else None, basis))
    # trough events: drawdown >15% then recovery >=20% to a new peak -> 3M forward per basket.
    # "3M" is pinned as 95 calendar days. A window whose end is beyond the stored data
    # is provisional: it keeps its row, flagged window_complete=false.
    vi_full = px["VNINDEX"].dropna()
    events = _major_troughs(vi_full)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cycle_trough_events")
        for t, confirmed in events:
            if t < pd.Timestamp("2018-10-01"):
                continue
            base = vi_full.loc[:t].iloc[-1]
            fwd = bdf.loc[t + pd.Timedelta(days=1): t + pd.Timedelta(days=95)]
            complete = bool(len(fwd)) and vi_full.index.max() >= t + pd.Timedelta(days=95)
            basket_obs = {c: int(fwd[c].notna().sum()) for c in TROUGH_BASKETS}
            if len(fwd):
                vals = {"trough": str(t.date()),
                        "confirmation": str(confirmed.date()),
                        "vnindex_3m": round(float(vi_full.loc[fwd.index[-1]] / base - 1) * 100, 1)}
                for c in TROUGH_BASKETS:
                    vals[c] = round(float((1 + fwd[c].dropna()).prod() - 1) * 100, 1)
            else:
                vals = {"trough": str(t.date()), "confirmation": str(confirmed.date()),
                        "vnindex_3m": None, **{c: None for c in TROUGH_BASKETS}}
            cols = ["trough", "confirmation", "window_start", "window_end", "window_days",
                    "window_observations", "window_complete", "basket_observations",
                    "vnindex_3m", *TROUGH_BASKETS]
            vals.update({
                "window_start": str((t + pd.Timedelta(days=1)).date()) if len(fwd) else None,
                "window_end": str(fwd.index.max().date()) if len(fwd) else None,
                "window_days": 95,
                "window_observations": len(fwd),
                "window_complete": complete,
                "basket_observations": json.dumps(basket_obs),
            })
            cur.execute(
                f"INSERT INTO cycle_trough_events({', '.join(cols)})"
                f" VALUES({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING",
                [vals[c] for c in cols])
    # meta
    today = date.today().isoformat()
    with conn.cursor() as cur:
        for k, v in [("as_of", today), ("members_version", MEMBERS_VERSION),
                     ("trough_rule_version", TROUGH_RULE_VERSION),
                     ("trough_rule_thresholds",
                      '{"drawdown_from_peak": 0.15, "rebound_to_new_peak": 0.20}'),
                     ("trough_window_days", "95"),
                     ("trough_requires_future_data", "true")]:
            cur.execute(
                "INSERT INTO cycle_meta(key,value) VALUES(%s,%s)"
                " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (k, v))
        cur.execute("SELECT COUNT(*) FROM cycle_watermark")
        out["cached_symbols"] = cur.fetchone()[0]
    out["as_of"] = today
    return _jsafe(out)
