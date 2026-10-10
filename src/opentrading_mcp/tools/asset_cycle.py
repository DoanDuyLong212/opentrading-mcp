"""Multi-asset cycle tables: VN assets + global assets, PG-backed.

VN scope (9 assets, no physical RE): VNINDEX/GOLD_W/USDVND/RON95/BTC/BRENT
  monthly + anchors (TPCP/deposit/TPDN/SJC-spread/foreign, provenance-kept)
  + Granger-verified chains.
Global scope (14 groups): monthly + NBER-phase + corr regimes + outlook snapshot.
Refresh: yfinance/VCI/petrol-API (no auth); FRED optional (USREC w/ hardcoded
fallback 2020-03/04). Batch ~12 symbols/call like cycle_stats.
"""

from __future__ import annotations

import functools
import json
import math
import time
import urllib.request
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

TOOL = "asset_cycle"
MAX_BATCH = 15

VN_FETCH = {  # asset -> (provider, symbol)
    "VNINDEX": ("vci", "VNINDEX"),
    "GOLD_W": ("yf", "GLD"),
    "USDVND": ("yf", "VND=X"),
    "RON95": ("petrol", None),
    "BTC": ("yf", "BTC-USD"),
    "BRENT": ("yf", "BZ=F"),
}
VN_ASSETS = list(VN_FETCH.keys())

G_ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "SHY", "TIP",
          "LQD", "HYG", "DBC", "GLD", "VNQ", "IGF", "UUP", "BTC-USD"]
NBER_KNOWN = ["2020-03", "2020-04"]  # fallback when FRED key absent


def _pg() -> Any:
    url = dbinit.db_url().strip()
    if not url:
        return None
    dbinit.ensure_tables()
    try:
        import psycopg

        return psycopg.connect(url, autocommit=True, connect_timeout=5)
    except Exception:
        return None


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope({"tool": tool}, source="unavailable",
                         warnings=[reason], availability="unavailable")


def _yf_close(symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    import yfinance as yf

    last: Exception | None = None
    for _ in range(2):
        try:
            df = yf.download(symbol, start=start, end=end, auto_adjust=True,
                             progress=False)["Close"]
            if df is None or len(df) == 0:
                raise ValueError("empty")
            s = df.iloc[:, 0].dropna() if hasattr(df, "iloc") else df.dropna()
            return [{"t": str(t)[:10], "c": float(v)} for t, v in s.items()]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2)
    raise ProviderUnavailable(f"yfinance failed for {symbol}: {last}")


def _vci_close(symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    try:
        from vnstock.api.quote import Quote
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    last: Exception | None = None
    for attempt in range(3):
        try:
            q = Quote(symbol=symbol.upper(), source="VCI")
            df = q.history(start=start, end=end, interval="1D")
            if df is None or len(df) == 0:
                raise ValueError("empty frame")
            import pandas as _pd
            if isinstance(df.index, _pd.DatetimeIndex):
                times = df.index
            else:
                tcol = "time" if "time" in df.columns else df.columns[0]
                times = _pd.to_datetime(df[tcol])
            return [{"t": str(ts)[:10], "c": float(row.get("close", 0) or 0)}
                    for ts, (_, row) in zip(times, df.iterrows())]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise ProviderUnavailable(f"VCI fetch failed for {symbol}: {last}")


def _petrol_ron95(start: str, end: str) -> list[dict[str, Any]]:
    import pandas as _pd

    with urllib.request.urlopen(
            "https://giaxanghomnay.com/api/chart?range=all", timeout=30) as r:
        data = json.load(r)
    df = _pd.DataFrame(data)
    df["date"] = _pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    s = df["a"].combine_first(df["e"] / 0.9815) * 1000  # RON95-III -> E10 splice
    s = s.loc[start:end].dropna()
    return [{"t": str(t)[:10], "c": float(v)} for t, v in s.items()]


def _fetch_vn_asset(asset: str, start: str, end: str) -> list[dict[str, Any]]:
    prov, sym = VN_FETCH[asset]
    if prov == "vci":
        return _vci_close(sym, start, end)
    if prov == "yf":
        return _yf_close(sym, start, end)
    if prov == "petrol":
        return _petrol_ron95(start, end)
    raise ProviderUnavailable(f"unknown provider for {asset}")


def _usrec_months() -> list[str]:
    """NBER recession months: FRED USREC when key present, else hardcoded known."""
    import os

    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id=USREC&api_key={key}&file_type=json&observation_start=2010-01-01")
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.load(r)
            return [o["date"][:7] for o in d["observations"] if o["value"] == "1"]
        except Exception:
            pass
    return [d + "-03" for d in ["2020"]] + [d + "-04" for d in ["2020"]]


def register_asset_cycle_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_asset_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Staleness of VN multi-asset tables. No fetch."""
        conn = _pg()
        if conn is None:
            return _na("vn_asset_check", "DATABASE_URL not configured")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM vn_asset_meta")
                meta = dict(cur.fetchall())
            as_of = meta.get("as_of", "")
            try:
                stale = (date.today() - date.fromisoformat(as_of)).days if as_of else None
            except ValueError:
                stale = None
            return make_envelope({
                "as_of": as_of or None, "stats_version": meta.get("stats_version"),
                "days_stale": stale,
                "needs_refresh": bool(stale is not None and stale > 90),
            }, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def vn_asset_seasonality(asset: str | None = None,
                                  month: int | None = None,
                                  ctx: AnyContext | None = None) -> dict[str, Any]:
        """Monthly mean/hit per VN asset class. Omit args for full table."""
        conn = _pg()
        if conn is None:
            return _na("vn_asset_seasonality", "DATABASE_URL not configured")
        try:
            q = "SELECT asset, month, mean_ret, hit_rate, n FROM vn_asset_monthly"
            cond: list[str] = []
            args: list[Any] = []
            if asset:
                cond.append("asset=%s")
                args.append(asset)
            if month:
                cond.append("month=%s")
                args.append(month)
            if cond:
                q += " WHERE " + " AND ".join(cond)
            q += " ORDER BY asset, month"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"asset": r[0], "month": r[1], "mean_ret": r[2],
                         "hit_rate": r[3], "n": r[4]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def vn_asset_anchors(asset: str | None = None,
                               ctx: AnyContext | None = None) -> dict[str, Any]:
        """Anchor-grade data (yields/spreads/walls/flows) with provenance. For TPCP/deposit/TPDN/SJC/foreign."""
        conn = _pg()
        if conn is None:
            return _na("vn_asset_anchors", "DATABASE_URL not configured")
        try:
            q = "SELECT asset, metric, period, value, unit, source FROM vn_asset_anchors"
            args: list[Any] = []
            if asset:
                q += " WHERE asset=%s"
                args.append(asset)
            q += " ORDER BY asset, period"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"asset": r[0], "metric": r[1], "period": r[2],
                         "value": r[3], "unit": r[4], "source": r[5]}
                        for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def vn_asset_chains(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Cross-asset lead-lag incl. Granger-verified links (BTC->VNI, Brent->RON95)."""
        conn = _pg()
        if conn is None:
            return _na("vn_asset_chains", "DATABASE_URL not configured")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pair, n_up, rel_mean, rel_hit, note FROM vn_asset_chains"
                            " ORDER BY rel_mean DESC")
                rows = [{"pair": r[0], "n_up": r[1], "rel_mean": r[2], "rel_hit": r[3],
                         "note": r[4]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_WRITE_STATE)
    async def vn_asset_refresh(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Refresh all 6 VN assets (incremental) + recompute monthly. Own tables only."""
        conn = _pg()
        if conn is None:
            return _na("vn_asset_refresh", "DATABASE_URL not configured")
        try:
            today = date.today().isoformat()
            status = []
            for asset in VN_ASSETS:
                try:
                    rows = await run_blocking(
                        functools.partial(_refresh_vn_asset, conn, asset, today),
                        TOOL, timeout_secs=60.0)
                    status.append(rows)
                except Exception as exc:  # noqa: BLE001
                    status.append({"asset": asset, "error": str(exc)[:150]})
            summ = await run_blocking(
                functools.partial(_vn_finalize, conn), TOOL, timeout_secs=120.0)
            summ["assets"] = status
            return make_envelope(summ, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def g_asset_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Staleness of global asset tables. No fetch."""
        conn = _pg()
        if conn is None:
            return _na("g_asset_check", "DATABASE_URL not configured")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM g_asset_meta")
                meta = dict(cur.fetchall())
            as_of = meta.get("as_of", "")
            try:
                stale = (date.today() - date.fromisoformat(as_of)).days if as_of else None
            except ValueError:
                stale = None
            return make_envelope({
                "as_of": as_of or None, "stats_version": meta.get("stats_version"),
                "days_stale": stale,
                "needs_refresh": bool(stale is not None and stale > 90),
            }, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def g_asset_seasonality(asset: str | None = None,
                                 month: int | None = None,
                                 ctx: AnyContext | None = None) -> dict[str, Any]:
        """Monthly mean/hit per global asset (17 ETFs). Omit args for full table."""
        conn = _pg()
        if conn is None:
            return _na("g_asset_seasonality", "DATABASE_URL not configured")
        try:
            q = "SELECT asset, month, mean_ret, hit_rate, n FROM g_asset_monthly"
            cond: list[str] = []
            args: list[Any] = []
            if asset:
                cond.append("asset=%s")
                args.append(asset)
            if month:
                cond.append("month=%s")
                args.append(month)
            if cond:
                q += " WHERE " + " AND ".join(cond)
            q += " ORDER BY asset, month"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"asset": r[0], "month": r[1], "mean_ret": r[2],
                         "hit_rate": r[3], "n": r[4]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def g_asset_phase(asset: str | None = None,
                            ctx: AnyContext | None = None) -> dict[str, Any]:
        """NBER-phase returns (Early/Late/Mid/Recession). Small-n warning on Early/Late/Recession."""
        conn = _pg()
        if conn is None:
            return _na("g_asset_phase", "DATABASE_URL not configured")
        try:
            q = "SELECT asset, phase, mean_m, ann_ret, n FROM g_asset_phase"
            args: list[Any] = []
            if asset:
                q += " WHERE asset=%s"
                args.append(asset)
            q += " ORDER BY asset, phase"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"asset": r[0], "phase": r[1], "mean_m": r[2],
                         "ann_ret": r[3], "n": r[4]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def g_asset_corr(regime: str | None = None,
                           ctx: AnyContext | None = None) -> dict[str, Any]:
        """Cross-asset monthly correlations. regime: full|pre22|post22."""
        conn = _pg()
        if conn is None:
            return _na("g_asset_corr", "DATABASE_URL not configured")
        try:
            q = "SELECT a, b, corr, regime FROM g_asset_corr"
            args: list[Any] = []
            if regime:
                q += " WHERE regime=%s"
                args.append(regime)
            q += " ORDER BY regime, a, b"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"a": r[0], "b": r[1], "corr": r[2], "regime": r[3]}
                        for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_ONLY)
    async def g_asset_outlook(house: str | None = None,
                              ctx: AnyContext | None = None) -> dict[str, Any]:
        """Curated bank/fund allocation calls per quarter (with sources). Manually refreshed."""
        conn = _pg()
        if conn is None:
            return _na("g_asset_outlook", "DATABASE_URL not configured")
        try:
            q = "SELECT house, quarter, asset, stance, detail FROM g_asset_outlook"
            args: list[Any] = []
            if house:
                q += " WHERE house=%s"
                args.append(house)
            q += " ORDER BY quarter DESC, house, asset"
            with conn.cursor() as cur:
                cur.execute(q, args)
                rows = [{"house": r[0], "quarter": r[1], "asset": r[2],
                         "stance": r[3], "detail": r[4]} for r in cur.fetchall()]
            return make_envelope({"rows": rows}, source="asset_cycle")
        finally:
            conn.close()

    @server.tool(annotations=READ_WRITE_STATE)
    async def g_asset_refresh(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Refresh 17 ETFs + USREC (incremental) + recompute monthly/phase/corr. Own tables only."""
        conn = _pg()
        if conn is None:
            return _na("g_asset_refresh", "DATABASE_URL not configured")
        try:
            today = date.today().isoformat()
            status = []
            for sym in G_ETFS:
                try:
                    rows = await run_blocking(
                        functools.partial(_refresh_g_symbol, conn, sym, today),
                        TOOL, timeout_secs=60.0)
                    status.append(rows)
                except Exception as exc:  # noqa: BLE001
                    status.append({"symbol": sym, "error": str(exc)[:150]})
            summ = await run_blocking(
                functools.partial(_g_finalize, conn), TOOL, timeout_secs=120.0)
            summ["symbols"] = status
            return make_envelope(summ, source="asset_cycle")
        finally:
            conn.close()

    return [
        {"name": "vn_asset_check"},
        {"name": "vn_asset_seasonality"},
        {"name": "vn_asset_anchors"},
        {"name": "vn_asset_chains"},
        {"name": "vn_asset_refresh"},
        {"name": "g_asset_check"},
        {"name": "g_asset_seasonality"},
        {"name": "g_asset_phase"},
        {"name": "g_asset_corr"},
        {"name": "g_asset_outlook"},
        {"name": "g_asset_refresh"},
    ]


def _refresh_vn_asset(conn: Any, asset: str, today: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(t) FROM vn_asset_ohlcv WHERE asset=%s", (asset,))
        mx = cur.fetchone()[0]
    start = (mx - timedelta(days=20)).isoformat() if mx else "2015-01-01"
    if asset == "RON95":
        start = max(start, "2018-01-01")
    fresh = _fetch_vn_asset(asset, start, today)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO vn_asset_ohlcv(asset,t,c) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            [(asset, r["t"], r["c"]) for r in fresh])
        cur.execute("SELECT COUNT(*), MAX(t) FROM vn_asset_ohlcv WHERE asset=%s", (asset,))
        n, last = cur.fetchone()
    # NOTE: vn_asset_ohlcv table must exist (added in dbinit asset-rotation: fix uses cycle_ohlcv-like DDL)
    return {"asset": asset, "rows": n, "last": str(last) if last else None}


def _refresh_g_symbol(conn: Any, sym: str, today: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(t) FROM g_ohlcv WHERE symbol=%s", (sym,))
        mx = cur.fetchone()[0]
    start = (mx - timedelta(days=20)).isoformat() if mx else "2010-01-01"
    rows = _yf_close(sym, start, today)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO g_ohlcv(symbol,t,c) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            [(sym, r["t"], r["c"]) for r in rows])
        cur.execute("SELECT COUNT(*), MAX(t) FROM g_ohlcv WHERE symbol=%s", (sym,))
        n, last = cur.fetchone()
    return {"symbol": sym, "rows": n, "last": str(last) if last else None}


def _vn_finalize(conn: Any) -> dict[str, Any]:
    import pandas as pd

    with conn.cursor() as cur:
        cur.execute("SELECT asset, t, c FROM vn_asset_ohlcv ORDER BY asset, t")
        by_asset: dict[str, Any] = {}
        for a, t, c in cur.fetchall():
            by_asset.setdefault(a, {})[str(t)] = float(c)
    px = pd.DataFrame({a: pd.Series(v, dtype=float) for a, v in by_asset.items()})
    px.index = pd.to_datetime(px.index)
    px = px.sort_index().ffill()
    mb = (1 + px.pct_change(fill_method=None)).resample("ME").prod(min_count=1) - 1
    with conn.cursor() as cur:
        cur.execute("DELETE FROM vn_asset_monthly")
        for a in mb.columns:
            s = mb[a].dropna()
            for m in range(1, 13):
                seg = s[s.index.month == m]
                if len(seg) == 0:
                    continue
                cur.execute(
                    "INSERT INTO vn_asset_monthly(asset,month,mean_ret,hit_rate,n)"
                    " VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (a, m, round(float(seg.mean()) * 100, 2),
                     round(float((seg > 0).mean()) * 100, 1), len(seg)))
        cur.execute("INSERT INTO vn_asset_meta(key,value) VALUES('as_of',%s)"
                    " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                    (date.today().isoformat(),))
    return {"range": [str(px.index.min().date()), str(px.index.max().date())],
            "as_of": date.today().isoformat()}


def _g_finalize(conn: Any) -> dict[str, Any]:
    import pandas as pd

    with conn.cursor() as cur:
        cur.execute("SELECT symbol, t, c FROM g_ohlcv ORDER BY symbol, t")
        by_sym: dict[str, Any] = {}
        for s, t, c in cur.fetchall():
            by_sym.setdefault(s, {})[str(t)] = float(c)
    px = pd.DataFrame({s: pd.Series(v, dtype=float) for s, v in by_sym.items()})
    px.index = pd.to_datetime(px.index)
    px = px.sort_index().ffill()
    gm = (1 + px.pct_change(fill_method=None)).resample("ME").prod(min_count=1) - 1
    with conn.cursor() as cur:
        cur.execute("DELETE FROM g_asset_monthly")
        for a in gm.columns:
            s = gm[a].dropna()
            for m in range(1, 13):
                seg = s[s.index.month == m]
                if len(seg) == 0:
                    continue
                cur.execute(
                    "INSERT INTO g_asset_monthly(asset,month,mean_ret,hit_rate,n)"
                    " VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (a, m, round(float(seg.mean()) * 100, 2),
                     round(float((seg > 0).mean()) * 100, 1), len(seg)))
        # phases via USREC months: Recession + Early(12M post-trough) +
        # Late(12M pre-peak) + Mid(rest). Trough = first expansion month after
        # a recession block; peak = last expansion month before one.
        try:
            rec = set(_usrec_months())
        except Exception:
            rec = set()
        months = sorted({f"{p.year}-{p.month:02d}" for p in gm.index.to_period("M")})
        is_rec = {m: (m in rec) for m in months}
        troughs, peaks = [], []
        for i, m in enumerate(months):
            prev = months[i - 1] if i else None
            nxt = months[i + 1] if i + 1 < len(months) else None
            if not is_rec[m] and prev and is_rec[prev]:
                troughs.append(m)
            if not is_rec[m] and nxt and is_rec[nxt]:
                peaks.append(m)

        def phase_of(key: str) -> str:
            # Early = trough month + 11 following (12M); Late = 11 before + peak (12M)
            if is_rec.get(key):
                return "Recession"
            y, m = int(key[:4]), int(key[5:7])
            for t in troughs:
                ty, tm = int(t[:4]), int(t[5:7])
                d = (y - ty) * 12 + (m - tm)
                if 0 <= d <= 11:
                    return "Early"
            for p in peaks:
                py, pm = int(p[:4]), int(p[5:7])
                d = (py - y) * 12 + (pm - m)
                if 0 <= d <= 11:
                    return "Late"
            return "Mid"

        mmap = {str(p): phase_of(f"{p.year}-{p.month:02d}")
                for p in gm.index.to_period("M").unique()}
        ph = gm.copy()
        ph["__ph"] = [mmap[str(p)] for p in gm.index.to_period("M")]
        cur.execute("DELETE FROM g_asset_phase")
        for a in gm.columns:
            for phase, seg in ph.groupby("__ph")[a]:
                seg = seg.dropna()
                if len(seg) == 0:
                    continue
                cur.execute(
                    "INSERT INTO g_asset_phase(asset,phase,mean_m,ann_ret,n)"
                    " VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (a, phase, round(float(seg.mean()) * 100, 2),
                     round(float(((1 + seg.mean()) ** 12 - 1) * 100), 1), len(seg)))
        # corr full + regimes
        for regime, frame in [("full", gm), ("pre22", gm.loc[:"2021-12"]),
                              ("post22", gm.loc["2022-01":])]:
            c = frame.corr()
            cur.execute("DELETE FROM g_asset_corr WHERE regime=%s", (regime,))
            for i in c.columns:
                for j in c.columns:
                    v = c.loc[i, j]
                    if v == v:
                        cur.execute(
                            "INSERT INTO g_asset_corr(a,b,corr,regime) VALUES(%s,%s,%s,%s)"
                            " ON CONFLICT DO NOTHING", (i, j, round(float(v) * 100, 1), regime))
        cur.execute("INSERT INTO g_asset_meta(key,value) VALUES('as_of',%s)"
                    " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                    (date.today().isoformat(),))
    return {"range": [str(px.index.min().date()), str(px.index.max().date())],
            "as_of": date.today().isoformat()}
