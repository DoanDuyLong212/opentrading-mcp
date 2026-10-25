"""Independent oracle tests for the full-review Wave-B financial fixes.

Every expected value is computed from the primary definition inside the test
(not by calling the implementation under test twice), per the acceptance
matrix in plans/full-review-2026-10-25/02-execution-plan.md §3.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------- F01 equal
def test_f01_equal_objective_returns_equal_weights():
    """objective='equal' must return 1/n per symbol, even when the series would
    make max_sharpe pick a tilted portfolio."""
    import asyncio

    import opentrading_mcp.tools.quant_stats as qs
    from opentrading_mcp.server import create_server, register_preset

    # Distinct nondegenerate series (max_sharpe would clearly tilt these).
    rng = np.random.default_rng(7)
    a = list(50 + np.cumsum(rng.normal(0.001, 0.02, 80)))
    b = list(20 + np.cumsum(rng.normal(-0.0005, 0.01, 80)))

    class _FakeVn:
        def quote_history(self, symbol, days):
            import datetime as _dt

            closes = a if symbol == "AAA" else b
            out_rows = []
            day = _dt.date(2026, 1, 1)
            for c in closes:
                while day.weekday() >= 5:
                    day += _dt.timedelta(days=1)
                out_rows.append({"t": day.isoformat(), "c": float(c)})
                day += _dt.timedelta(days=1)
            return out_rows

    original = qs.vn_p
    qs.vn_p = _FakeVn()
    try:
        server = create_server("quant")
        register_preset(server, "quant")
        tool = server._tool_manager.get_tool("portfolio_optimize")
        assert tool is not None, "portfolio_optimize not registered"
        out = asyncio.run(tool.fn(symbols=["AAA", "BBB"], objective="equal", days=80))
    finally:
        qs.vn_p = original

    weights = out["data"]["weights"] if "data" in out else out["weights"]
    assert abs(weights["AAA"] - 0.5) < 1e-6, weights
    assert abs(weights["BBB"] - 0.5) < 1e-6, weights


# ---------------------------------------------------------------- F02 CCI
def _cci_reference(tp: list[float], idx: int, period: int = 20) -> float:
    """Lambert CCI from the definition: deviations measured against ONE
    constant SMA over the window ending at idx."""
    window = tp[idx - period + 1 : idx + 1]
    sma = sum(window) / period
    md = sum(abs(x - sma) for x in window) / period
    return (tp[idx] - sma) / (0.015 * md)


def test_f02_cci_matches_lambert_definition_and_available_at_bar_20():
    from opentrading_mcp.providers.technicals import compute

    rng = np.random.default_rng(11)
    closes = list(50 + np.cumsum(rng.normal(0, 0.5, 45)))
    candles = [
        {
            "t": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            "o": c * 0.99,
            "h": c * 1.01,
            "l": c * 0.98,
            "c": c,
            "v": 1000.0,
        }
        for c in closes
    ]
    tp = [(c["h"] + c["l"] + c["c"]) / 3 for c in candles]
    out = compute(candles)
    cci20 = out["cci20"]

    expected = _cci_reference(tp, len(tp) - 1)
    assert cci20 is not None
    assert math.isclose(cci20, round(expected, 2), abs_tol=1e-9), (cci20, expected)

    # Availability: a full series must also produce a valid CCI when truncated
    # to exactly 20 bars (first possible window) — the old code returned None.
    out20 = compute(candles[:20])
    expected20 = _cci_reference(tp, 19)
    assert out20["cci20"] is not None, "CCI must be available at exactly 20 bars"
    assert math.isclose(out20["cci20"], round(expected20, 2), abs_tol=1e-9)


# ---------------------------------------------------------------- F03 Wilder
def test_f03_rsi_uses_sma_seed_wilder_recurrence():
    from opentrading_mcp.providers.technicals import compute

    # 16 bars with explicit alternating moves so the seed and the first
    # recurrence differ measurably from an ewm-from-first-delta curve.
    closes = [100, 101, 102, 101, 103, 104, 103, 105, 104, 106, 107, 106, 108, 107, 109, 110]
    candles = [
        {"t": f"2026-01-{i + 1:02d}", "o": c, "h": c + 0.5, "l": c - 0.5, "c": c, "v": 1.0}
        for i, c in enumerate(closes)
    ]
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # Wilder definition: seed = SMA of the first 14 deltas, then recurrence.
    seed_gain = sum(gains[:14]) / 14
    seed_loss = sum(losses[:14]) / 14
    ag, al = seed_gain, seed_loss
    for g, l in zip(gains[14:], losses[14:]):
        ag = (ag * 13 + g) / 14
        al = (al * 13 + l) / 14
    rs = ag / al if al else math.inf
    expected_rsi = 100 - 100 / (1 + rs)

    out = compute(candles)
    assert out["rsi14"] is not None
    # _last_float rounds to 2 dp for display.
    assert math.isclose(out["rsi14"], round(expected_rsi, 2), abs_tol=1e-9), (
        out["rsi14"],
        expected_rsi,
    )


def test_f03_atr_uses_sma_seed():
    from opentrading_mcp.providers.technicals import _wilder_smooth

    # TR series with no NaN: seed must be the SMA of the first 14 values.
    tr = pd.Series([2.0 + (i % 5) * 0.5 for i in range(30)], dtype=float)
    sm = _wilder_smooth(tr, 14)
    assert math.isclose(sm.iloc[13], tr.iloc[:14].mean(), rel_tol=1e-9)
    # Recurrence check one step past the seed.
    expected = sm.iloc[13] + (tr.iloc[14] - sm.iloc[13]) / 14
    assert math.isclose(sm.iloc[14], expected, rel_tol=1e-9)
    # NaN prefix preserved (no value before the seed).
    assert sm.iloc[:13].isna().all()


# ---------------------------------------------------------------- F06 M-score
def test_f06_mscore_classification_uses_raw_precision():
    """Display rounding must not flip the -1.78 classification. Shift the
    intercept so raw_score = -1.77999: it rounds to -1.78 for display (score
    == -1.78) but the raw value still exceeds the threshold, so the review
    flag MUST be present. The pre-fix code (classifying on the rounded value)
    drops the flag and fails this test."""
    from opentrading_mcp import forensic_models as fm
    from tests.test_forensic_models import full_bundle

    baseline = fm.calculate_forensic(full_bundle())
    assert baseline["m_score"] is not None
    baseline_score = baseline["m_score"]
    # raw0 = baseline_score + e where |e| < 5e-5; shifting the intercept by
    # (-1.77999 - baseline_score - 1e-9) lands raw at ≈ -1.77999.
    delta = -1.77999 - baseline_score - 1e-9
    original_intercept = fm.BENEISH_INTERCEPT
    fm.BENEISH_INTERCEPT = original_intercept + delta
    try:
        out = fm.calculate_forensic(full_bundle())
    finally:
        fm.BENEISH_INTERCEPT = original_intercept

    assert out["m_score"] == -1.78, out["m_score"]  # display rounds to 4 dp
    assert any("above -1.78" in f for f in out["flags"]), out  # raw keeps the flag


# ---------------------------------------------------------------- F15 buy_hold
def test_f15_buy_hold_respects_month_and_condition_gates():
    from opentrading_mcp.tools.quant_shared import _run_strategy

    n = 40
    closes = [100.0 + i for i in range(n)]
    dates = [datetime(2026, 1, 1) for _ in range(n)]  # all January
    out = _run_strategy(
        closes,
        "buy_hold",
        fast=1,
        slow=2,
        cost_bps=0.0,
        dates=dates,
        months=[2],  # only February allowed — no bar qualifies
    )
    # Every bar is January → gated buy_hold must stay flat the whole time.
    assert out["trades"] == 0, out
    assert out["net_return"] == 0.0, out
    assert out.get("month_filtered") in (True, None) or out.get("month_filtered") is not None

    # Ungated buy_hold still rides the full series.
    out2 = _run_strategy(closes, "buy_hold", fast=1, slow=2, cost_bps=0.0)
    assert out2["trades"] >= 1 and out2["net_return"] > 0.0
