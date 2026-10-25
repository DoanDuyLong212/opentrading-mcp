"""P3 full technicals (pandas, local compute, TradingView-pattern port).

Computes RSI14 (Wilder), Stoch(14,3), CCI20, ADX14, MACD(12,26,9),
Momentum10, AO(5,34), EMA/SMA, VWMA20 (fallback SMA20), Hull9,
Bollinger(20,2), ATR14 (Wilder) + recommend vote.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _to_frame(candles: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
        df.columns = [str(c).lower() for c in df.columns]
    else:
        df = pd.DataFrame(candles)
        df.columns = [str(c).lower() for c in df.columns]
    for col in ("o", "h", "l", "c", "v"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _last_float(series: pd.Series, nd: int = 2) -> float | None:
    try:
        val = float(series.iloc[-1])
    except Exception:
        return None
    if not np.isfinite(val):
        return None
    return round(val, nd)


def _swing_pivots(
    h_vals: list[float], l_vals: list[float], order: int = 5
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Fractal pivots: strict local max/min over `order` bars each side."""
    n = min(len(h_vals), len(l_vals))
    pivots: list[tuple[int, float, str]] = []
    if n >= 2 * order + 1:
        for i in range(order, n - order):
            window_h = h_vals[i - order : i + order + 1]
            window_l = l_vals[i - order : i + order + 1]
            if h_vals[i] > max(window_h[:order] + window_h[order + 1 :]):
                pivots.append((i, h_vals[i], "H"))
            elif l_vals[i] < min(window_l[:order] + window_l[order + 1 :]):
                pivots.append((i, l_vals[i], "L"))
    highs = [(i, p) for i, p, s in pivots if s == "H"]
    lows = [(i, p) for i, p, s in pivots if s == "L"]
    return highs, lows


def _wma(series: pd.Series, n: int) -> pd.Series:
    weights = np.arange(1, n + 1, dtype=float)
    denom = weights.sum()
    return series.rolling(n, min_periods=n).apply(
        lambda x: float(np.dot(x, weights) / denom), raw=True
    )


def compute(
    candles: list[dict[str, Any]] | pd.DataFrame,
    benchmark: list[float] | None = None,
    ichimoku_convention: str = "offset25",
) -> dict[str, Any]:
    """Compute full technicals from candles with columns t,o,h,l,c,v.

    benchmark: optional index closes aligned by position (same market calendar);
    yields rs_vs_bench = 63d return spread in pct points (None when <20 common).
    """
    df = _to_frame(candles)
    if len(df) == 0 or "c" not in df.columns:
        raise ValueError("compute needs at least close column")
    close = df["c"].astype(float)
    high = df["h"].astype(float) if "h" in df.columns else close.copy()
    low = df["l"].astype(float) if "l" in df.columns else close.copy()
    vol = df["v"].astype(float) if "v" in df.columns else pd.Series(np.nan, index=df.index)
    n = len(df)
    last = float(close.iloc[-1]) if n else 0.0

    # RSI14 Wilder ewm alpha=1/14
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # avg_loss==0 & avg_gain>0 -> 100; both zero -> 50
    rsi = rsi.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))
    rsi = rsi.clip(0, 100)
    # Too few bars gives None, never an invented neutral 50 (same for every indicator below).
    rsi14 = _last_float(rsi)

    # Stoch (14,3)
    ll = low.rolling(14, min_periods=14).min()
    hh = high.rolling(14, min_periods=14).max()
    span_hl = hh - ll
    k = 100 * (close - ll) / span_hl.replace(0, np.nan)
    # A flat 14-bar range puts %K mid-range; bars before the window fills stay NaN.
    k = k.where(span_hl != 0, 50.0).where(span_hl.notna()).clip(0, 100)
    d = k.rolling(3, min_periods=3).mean()
    stoch_k = _last_float(k)
    stoch_d = _last_float(d)

    # CCI20
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(20, min_periods=20).mean()
    md = (tp - sma_tp).abs().rolling(20, min_periods=20).mean()
    cci = (tp - sma_tp) / (0.015 * md.replace(0, np.nan))
    cci = cci.where(md != 0, 0.0).where(md.notna())  # flat window: 0; warm-up: NaN
    cci20 = _last_float(cci)

    # ATR14 Wilder + ADX14
    prev_c = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_c).abs()
    tr3 = (low - prev_c).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    atr14 = _last_float(atr)

    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    plus_sm = plus_dm.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    minus_sm = minus_dm.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    atr_sm = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * plus_sm / atr_sm
    minus_di = 100 * minus_sm / atr_sm
    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum.replace(0, np.nan)
    # No directional movement gives DX 0; the DI warm-up stays NaN so it is not
    # averaged into ADX as fake zeros.
    dx = dx.where(~((di_sum == 0) & plus_di.notna()), 0.0)
    adx = dx.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    adx14 = _last_float(adx)

    # MACD (12,26,9)
    ema12 = close.ewm(span=12, min_periods=12, adjust=False).mean()
    ema26 = close.ewm(span=26, min_periods=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, min_periods=9, adjust=False).mean()
    line_f = _last_float(macd_line, 4)
    sig_f = _last_float(macd_signal, 4)
    hist_f = round(line_f - sig_f, 4) if line_f is not None and sig_f is not None else None

    # Momentum10
    mom = close - close.shift(10)
    momentum10 = _last_float(mom)

    # AO (5,34 median)
    median = (high + low) / 2
    ao_s = median.rolling(5, min_periods=5).mean() - median.rolling(34, min_periods=34).mean()
    ao = _last_float(ao_s)

    # EMA / SMA
    ema10 = _last_float(close.ewm(span=10, min_periods=10, adjust=False).mean())
    ema20 = _last_float(close.ewm(span=20, min_periods=20, adjust=False).mean())
    ema50 = _last_float(close.ewm(span=50, min_periods=50, adjust=False).mean())
    sma10 = _last_float(close.rolling(10, min_periods=10).mean())
    sma20 = _last_float(close.rolling(20, min_periods=20).mean())
    sma50 = _last_float(close.rolling(50, min_periods=50).mean())
    sma150 = _last_float(close.rolling(150, min_periods=150).mean())
    sma200 = _last_float(close.rolling(200, min_periods=200).mean())

    # 52w position in the trailing-250d high-low range (P8 SEPA legs).
    span = df.tail(250)
    try:
        hi52, lo52 = float(span["h"].max()), float(span["l"].min())
        pos_52w: float | None = round((last - lo52) / (hi52 - lo52), 4) if hi52 > lo52 else 0.5
    except Exception:
        pos_52w = None

    # Relative strength vs benchmark closes (position-aligned, same calendar).
    rs_vs_bench: float | None = None
    if benchmark:
        k = min(63, n, len(benchmark))
        if k >= 20:
            try:
                c_then, c_now = float(close.iloc[n - k]), float(last)
                b_then, b_now = float(benchmark[len(benchmark) - k]), float(benchmark[-1])
                if c_then and b_then:
                    rs_vs_bench = round((c_now / c_then - b_now / b_then) * 100, 2)
            except Exception:
                rs_vs_bench = None

    # VWMA20 fallback SMA20
    if "v" not in df.columns or vol.isna().all() or float(vol.fillna(0).sum()) == 0:
        vwma = sma20
    else:
        vw = (close * vol.fillna(0)).rolling(20, min_periods=20).sum() / vol.rolling(
            20, min_periods=20
        ).sum().replace(0, np.nan)
        vwma = _last_float(vw)
        if vwma is None:
            vwma = sma20

    # Hull9
    try:
        half = 9 // 2
        sqrt_n = int(np.sqrt(9))
        raw_hull = 2 * _wma(close, half) - _wma(close, 9)
        hull_s = _wma(raw_hull, sqrt_n)
        hull9 = _last_float(hull_s)
    except Exception:
        hull9 = None

    # Bollinger (20,2)
    mid = close.rolling(20, min_periods=20).mean()
    std = close.rolling(20, min_periods=20).std(ddof=1)
    boll_upper = _last_float(mid + 2 * std)
    boll_lower = _last_float(mid - 2 * std)

    # Ichimoku (9/26/52). This implementation aligns the current cloud with spans
    # computed 25 completed bars earlier; a 26-bar convention is also published.
    # We retain the established 25-bar contract until a reference series proves
    # which chart convention consumers need. *_ahead are the spans computed now.
    if ichimoku_convention not in ("offset25", "classic26"):
        raise ValueError(
            f"unknown ichimoku_convention {ichimoku_convention!r} (offset25|classic26)"
        )
    offset = 26 if ichimoku_convention == "classic26" else 25
    def _midpoint(period: int) -> Any:
        return (
            high.rolling(period, min_periods=period).max()
            + low.rolling(period, min_periods=period).min()
        ) / 2

    try:
        tenkan_s = _midpoint(9)
        kijun_s = _midpoint(26)
        senkou_a_s = (tenkan_s + kijun_s) / 2
        senkou_b_s = _midpoint(52)
        chikou_s = close.shift(offset)  # the close chikou is plotted against (-offset)
        tenkan = _last_float(tenkan_s)
        kijun = _last_float(kijun_s)
        senkou_a = _last_float(senkou_a_s.shift(offset))
        senkou_b = _last_float(senkou_b_s.shift(offset))
        senkou_a_ahead = _last_float(senkou_a_s)
        senkou_b_ahead = _last_float(senkou_b_s)
        chikou = _last_float(chikou_s)
    except Exception:
        tenkan = kijun = senkou_a = senkou_b = senkou_a_ahead = senkou_b_ahead = chikou = None
    cloud_parts = [x for x in (senkou_a, senkou_b) if x is not None]
    if tenkan is None or kijun is None or not cloud_parts:
        ichi_signal = None
    else:
        top = max(cloud_parts)
        bot = min(cloud_parts)
        if last > top and tenkan > kijun:
            ichi_signal = "bullish"
        elif last < bot and tenkan < kijun:
            ichi_signal = "bearish"
        else:
            ichi_signal = "neutral"
    ichimoku = {
        "offset_bars": offset,
        "convention": (
            "classic26_cloud_from_spans_26_bars_prior"
            if offset == 26
            else "current_cloud_from_spans_25_bars_prior"
        ),
        "chikou_reference": (
            f"close_{offset}_bars_ago_for_current_close_comparison"
        ),
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "senkou_a_ahead": senkou_a_ahead,
        "senkou_b_ahead": senkou_b_ahead,
        "chikou": chikou,
        "signal": ichi_signal,
    }

    # Swing structure (fractal order 5): HH/HL/LH/LL + trend + Fibonacci.
    swings: list[dict[str, Any]] = []
    try:
        h_vals = [float(x) for x in high.tolist()]
        l_vals = [float(x) for x in low.tolist()]
        highs, lows = _swing_pivots(h_vals, l_vals, order=5)
        labeled: list[tuple[int, float, str]] = []
        for k, (i, p) in enumerate(highs):
            labeled.append((i, p, "HH" if k and p > highs[k - 1][1] else ("LH" if k else "H")))
        for k, (i, p) in enumerate(lows):
            labeled.append((i, p, "HL" if k and p > lows[k - 1][1] else ("LL" if k else "L")))
        labeled.sort(key=lambda t: t[0])
        swings = [{"i": i, "price": round(p, 2), "side": s} for i, p, s in labeled[-8:]]
        if len(highs) >= 2 and len(lows) >= 2:
            up = highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]
            down = highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]
            swing_trend: str | None = "higher-high" if up else ("lower-low" if down else "mixed")
        else:
            swing_trend = "insufficient"
    except Exception:
        swing_trend = "insufficient"
    # Fibonacci retracement over the last 60 bars (or all).
    fib: dict[str, Any] = {"direction": None, "anchor_lo": None, "anchor_hi": None, "levels": {}}
    try:
        win = min(n, 60)
        w_h = [float(x) for x in high.tolist()[-win:]]
        w_l = [float(x) for x in low.tolist()[-win:]]
        hi, lo = max(w_h), min(w_l)
        if hi > lo:
            up = w_h.index(hi) >= w_l.index(lo)
            levels = {}
            for r in (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0):
                v = lo + r * (hi - lo) if up else hi - r * (hi - lo)
                levels[str(r)] = round(v, 2)
            fib = {
                "direction": "up" if up else "down",
                "anchor_lo": round(lo, 2),
                "anchor_hi": round(hi, 2),
                "levels": levels,
            }
    except Exception:
        fib = {"direction": None, "anchor_lo": None, "anchor_hi": None, "levels": {}}

    # Recommend vote: rsi / macd / adx / stoch / ma trend (an indicator without a value
    # votes Neutral).
    votes: list[str] = []
    if rsi14 is not None:
        votes.append("Buy" if rsi14 > 55 else ("Sell" if rsi14 < 45 else "Neutral"))
    else:
        votes.append("Neutral")
    if hist_f is not None:
        votes.append("Buy" if hist_f > 0 else ("Sell" if hist_f < 0 else "Neutral"))
    else:
        votes.append("Neutral")
    if stoch_k is not None and stoch_d is not None and stoch_k > stoch_d:
        votes.append("Buy")
    elif stoch_k is not None and stoch_d is not None and stoch_k < stoch_d:
        votes.append("Sell")
    else:
        votes.append("Neutral")
    if sma20 is not None:
        votes.append("Buy" if last > sma20 else ("Sell" if last < sma20 else "Neutral"))
    else:
        votes.append("Neutral")
    if adx14 is not None and adx14 >= 20 and sma20 is not None:
        votes.append("Buy" if last > sma20 else ("Sell" if last < sma20 else "Neutral"))
    else:
        votes.append("Neutral")
    buys = sum(1 for v in votes if v == "Buy")
    sells = sum(1 for v in votes if v == "Sell")
    recommend = "Buy" if buys > sells else ("Sell" if sells > buys else "Neutral")

    # Elliott wave heuristic (P2.1): 5-move impulse vs ABC corrective vs none.
    # Full wave labeling is interpretive; this flags structure + invalidation only.
    elliott: dict[str, Any] = {
        "pattern": "none",
        "waves": [],
        "confidence": "low",
        "invalidation": None,
    }
    try:
        ordered = sorted(
            [(i, p, "H") for i, p in highs] + [(i, p, "L") for i, p in lows],
            key=lambda t: t[0],
        )
        # strictly alternating tail (merge same-side runs, keep most extreme)
        alt: list[tuple[int, float, str]] = []
        for t in ordered[-14:]:
            if alt and alt[-1][2] == t[2]:
                prev = alt[-1]
                if (t[2] == "H" and t[1] > prev[1]) or (t[2] == "L" and t[1] < prev[1]):
                    alt[-1] = t
            else:
                alt.append(t)

        def _moves(win: list[tuple[int, float, str]]) -> list[dict[str, Any]]:
            return [
                {
                    "n": k + 1,
                    "from_i": win[k][0],
                    "to_i": win[k + 1][0],
                    "direction": "up" if win[k + 1][1] > win[k][1] else "down",
                    "length_pct": round(abs(win[k + 1][1] - win[k][1]) / win[k][1] * 100, 2)
                    if win[k][1]
                    else 0.0,
                }
                for k in range(len(win) - 1)
            ]

        def _check_impulse(win: list[tuple[int, float, str]]) -> dict[str, Any] | None:
            # win: 6 alternating pivots; bullish starts L, bearish starts H
            bull = win[0][2] == "L"
            moves = _moves(win)
            ups = [m for m in moves if m["direction"] == "up"]
            dns = [m for m in moves if m["direction"] == "down"]
            if bull and (len(ups) != 3 or len(dns) != 2):
                return None
            if not bull and (len(ups) != 2 or len(dns) != 3):
                return None
            trend_legs = ups if bull else dns
            ends = [win[moves.index(m) + 1][1] for m in trend_legs]
            starts = [win[moves.index(m)][1] for m in trend_legs]
            from itertools import pairwise

            ascending = (
                all(b > a for a, b in pairwise(ends)) and all(b > a for a, b in pairwise(starts))
                if bull
                else all(b < a for a, b in pairwise(ends))
                and all(b < a for a, b in pairwise(starts))
            )
            if not ascending:
                return None
            lens = [m["length_pct"] for m in trend_legs]
            w3_not_shortest = lens[1] >= min(lens)
            # wave-4 extreme must not overlap wave-1 extreme
            w1_end = ends[0]
            w4_start = starts[2]
            no_overlap = (w4_start > w1_end) if bull else (w4_start < w1_end)
            if not (w3_not_shortest and no_overlap):
                return {"partial": True, "moves": moves, "invalidation": None}
            gap = abs(w4_start - w1_end) / w1_end if w1_end else 0.0
            strong = lens[1] == max(lens) and gap > 0.01
            return {
                "partial": False,
                "moves": moves,
                "invalidation": round(w4_start, 2),
                "confidence": "high" if strong else "medium",
            }

        found = None
        starts = range(len(alt) - 6, -1, -1) if len(alt) >= 6 else []
        for s in starts:
            hit = _check_impulse(alt[s : s + 6])
            if hit and not hit.get("partial"):
                found = hit
                break
            found = found or hit
        if found and not found.get("partial"):
            elliott = {
                "pattern": "impulse",
                "waves": found["moves"],
                "confidence": found["confidence"],
                "invalidation": found["invalidation"],
            }
        else:
            # developing: last 5 pivots = waves 1-4 done, wave 5 pending
            dev = None
            for j in range(len(alt) - 5, -1, -1) if len(alt) >= 5 else []:
                win5 = alt[j : j + 5]
                if win5[0][2] != "L":
                    continue
                moves = _moves(win5)
                ups = [m for m in moves if m["direction"] == "up"]
                dns = [m for m in moves if m["direction"] == "down"]
                if len(ups) != 2 or len(dns) != 2:
                    continue
                up_ends = [win5[moves.index(m) + 1][1] for m in ups]
                dn_starts = [win5[moves.index(m)][1] for m in dns]
                if (
                    up_ends[1] > up_ends[0]
                    and dn_starts[1] > dn_starts[0]
                    and dn_starts[1] > up_ends[0]
                ):
                    dev = moves
                    break
            if dev is not None:
                elliott = {
                    "pattern": "impulse-developing",
                    "waves": dev,
                    "confidence": "low",
                    "invalidation": None,
                }
            elif found:
                elliott = {
                    "pattern": "impulse-developing",
                    "waves": found["moves"],
                    "confidence": "low",
                    "invalidation": None,
                }
            elif len(alt) >= 4:
                # ABC corrective: 3 alternating moves, counter-trend drift
                last3 = _moves(alt[-4:])
                if len(last3) == 3 and len({m["direction"] for m in last3}) == 2:
                    elliott = {
                        "pattern": "corrective",
                        "waves": last3,
                        "confidence": "low",
                        "invalidation": None,
                    }
    except Exception:
        elliott = {"pattern": "none", "waves": [], "confidence": "low", "invalidation": None}

    # Wyckoff phase heuristic (P2.1): range + volume + spring/upthrust.
    wyckoff: dict[str, Any] = {"phase": "unknown", "confidence": "low", "evidence": []}
    try:
        evidence: list[str] = []
        win_n = min(n, 40)
        w_close = [float(x) for x in close.tolist()[-win_n:]]
        w_high = [float(x) for x in high.tolist()[-win_n:]]
        w_low = [float(x) for x in low.tolist()[-win_n:]]
        w_vol = [float(x) for x in vol.tolist()[-win_n:] if x == x]
        rng = (max(w_high) - min(w_low)) / (sum(w_close) / len(w_close)) if w_close else 1.0
        dry_up = False
        if len(w_vol) >= 20:
            first = sum(w_vol[:10]) / 10
            last_v = sum(w_vol[-10:]) / 10
            dry_up = last_v < 0.7 * first if first else False
            if dry_up:
                evidence.append("volume drying up into range")
        spring = False
        upthrust = False
        if len(w_low) >= 30:
            prior_lo = min(w_low[:-10])
            recent_lo = min(w_low[-10:])
            if recent_lo < prior_lo and w_close[-1] > prior_lo:
                spring = True
                evidence.append("spring: false breakdown recovered")
            prior_hi = max(w_high[:-10])
            recent_hi = max(w_high[-10:])
            if recent_hi > prior_hi and w_close[-1] < prior_hi:
                upthrust = True
                evidence.append("upthrust: false breakout failed")
        sma50_v = _last_float(close.rolling(50, min_periods=50).mean())
        if spring:
            phase = "accumulation"
        elif upthrust:
            phase = "distribution"
        elif rng < 0.12 and dry_up:
            phase = "ranging"
            evidence.append("tight range + dry volume")
        elif sma50_v is not None and last < sma50_v and swing_trend == "lower-low":
            phase = "markdown"
        elif sma50_v is not None and last > sma50_v and swing_trend == "higher-high":
            phase = "markup"
        else:
            phase = "ranging"
        conf = "high" if len(evidence) >= 2 else ("medium" if evidence else "low")
        wyckoff = {"phase": phase, "confidence": conf, "evidence": evidence}
    except Exception:
        wyckoff = {"phase": "unknown", "confidence": "low", "evidence": []}

    # Candle patterns on the last 1-2 bars + 20d swing levels (P6).
    patterns: list[str] = []
    try:
        o0, h0, l0, c0 = (
            float(df["o"].iloc[-1]),
            float(df["h"].iloc[-1]),
            float(df["l"].iloc[-1]),
            float(df["c"].iloc[-1]),
        )
        body0, rng0 = abs(c0 - o0), h0 - l0
        if rng0 > 0:
            if body0 <= 0.1 * rng0:
                patterns.append("doji")
            lower_wick = min(o0, c0) - l0
            upper_wick = h0 - max(o0, c0)
            ref = max(body0, 1e-9)
            if lower_wick >= 2 * ref and upper_wick <= ref + 1e-9:
                patterns.append("hammer")
            if n >= 2:
                o1 = float(df["o"].iloc[-2])
                c1 = float(df["c"].iloc[-2])
                prev_bear, curr_bull = c1 < o1, c0 > o0
                prev_bull, curr_bear = c1 > o1, c0 < o0
                if prev_bear and curr_bull and o0 <= c1 and c0 >= o1:
                    patterns.append("engulfing_bull")
                if prev_bull and curr_bear and o0 >= c1 and c0 <= o1:
                    patterns.append("engulfing_bear")
    except Exception:
        patterns = []
    lookback = df.tail(20)
    try:
        support = round(float(lookback["l"].min()), 2)
    except Exception:
        support = round(float(low.min()), 2) if n else 0.0
    try:
        resistance = round(float(lookback["h"].max()), 2)
    except Exception:
        resistance = round(float(high.max()), 2) if n else 0.0

    return {
        "rsi14": rsi14,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "cci20": cci20,
        "adx14": adx14,
        "macd": {"line": line_f, "signal": sig_f, "hist": hist_f},
        "momentum10": momentum10,
        "ao": ao,
        "ema10": ema10,
        "ema20": ema20,
        "ema50": ema50,
        "sma10": sma10,
        "sma20": sma20,
        "sma50": sma50,
        "sma150": sma150,
        "sma200": sma200,
        "vwma": vwma,
        "hull9": hull9,
        "boll_upper": boll_upper,
        "boll_lower": boll_lower,
        "atr14": atr14,
        "ichimoku": ichimoku,
        "swings": swings,
        "swing_trend": swing_trend,
        "fib": fib,
        "elliott": elliott,
        "wyckoff": wyckoff,
        "recommend": recommend,
        "patterns": patterns,
        "support": support,
        "resistance": resistance,
        "rs_vs_bench": rs_vs_bench,
        "pos_52w": pos_52w,
        "last": round(float(last), 2),
        "n": n,
    }
