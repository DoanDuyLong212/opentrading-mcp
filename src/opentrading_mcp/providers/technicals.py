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


def _wma(series: pd.Series, n: int) -> pd.Series:
    weights = np.arange(1, n + 1, dtype=float)
    denom = weights.sum()
    return series.rolling(n, min_periods=n).apply(
        lambda x: float(np.dot(x, weights) / denom), raw=True
    )


def compute(
    candles: list[dict[str, Any]] | pd.DataFrame,
    benchmark: list[float] | None = None,
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
    rsi14 = _last_float(rsi)
    if rsi14 is None:
        rsi14 = 50.0

    # Stoch (14,3)
    ll = low.rolling(14, min_periods=14).min()
    hh = high.rolling(14, min_periods=14).max()
    denom = (hh - ll).replace(0, np.nan)
    k = 100 * (close - ll) / denom
    k = k.where(denom.notna().fillna(False), 50.0)
    k = k.fillna(50.0).clip(0, 100)
    d = k.rolling(3, min_periods=1).mean()
    stoch_k = _last_float(k)
    stoch_d = _last_float(d)
    if stoch_k is None:
        stoch_k = 50.0
    if stoch_d is None:
        stoch_d = 50.0

    # CCI20
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(20, min_periods=20).mean()
    md = (tp - sma_tp).abs().rolling(20, min_periods=20).mean()
    cci = (tp - sma_tp) / (0.015 * md.replace(0, np.nan))
    cci = cci.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    cci20 = _last_float(cci)
    if cci20 is None:
        cci20 = 0.0

    # ATR14 Wilder + ADX14
    prev_c = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_c).abs()
    tr3 = (low - prev_c).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    atr14 = _last_float(atr)
    if atr14 is None:
        atr14 = 0.0

    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    plus_sm = plus_dm.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    minus_sm = minus_dm.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    atr_sm = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * plus_sm / atr_sm
    minus_di = 100 * minus_sm / atr_sm
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    dx = dx.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    adx = dx.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    adx14 = _last_float(adx)
    if adx14 is None:
        adx14 = 0.0

    # MACD (12,26,9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    line_f = _last_float(macd_line, 4)
    sig_f = _last_float(macd_signal, 4)
    if line_f is None:
        line_f = 0.0
    if sig_f is None:
        sig_f = 0.0
    hist_f = round(line_f - sig_f, 4)

    # Momentum10
    mom = close - close.shift(10)
    momentum10 = _last_float(mom)
    if momentum10 is None:
        momentum10 = 0.0

    # AO (5,34 median)
    median = (high + low) / 2
    ao_s = median.rolling(5, min_periods=5).mean() - median.rolling(34, min_periods=34).mean()
    ao = _last_float(ao_s)
    if ao is None:
        ao = 0.0

    # EMA / SMA
    ema10 = _last_float(close.ewm(span=10, adjust=False).mean())
    ema20 = _last_float(close.ewm(span=20, adjust=False).mean())
    ema50 = _last_float(close.ewm(span=50, adjust=False).mean())
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

    # Recommend vote: rsi / macd / adx / stoch / ma trend
    votes: list[str] = []
    votes.append("Buy" if rsi14 > 55 else ("Sell" if rsi14 < 45 else "Neutral"))
    votes.append("Buy" if hist_f > 0 else ("Sell" if hist_f < 0 else "Neutral"))
    if stoch_k > stoch_d:
        votes.append("Buy")
    elif stoch_k < stoch_d:
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
        "recommend": recommend,
        "patterns": patterns,
        "support": support,
        "resistance": resistance,
        "rs_vs_bench": rs_vs_bench,
        "pos_52w": pos_52w,
        "last": round(float(last), 2),
        "n": n,
    }
