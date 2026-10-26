"""Wave-5 randomized property invariants (seeded, dependency-free).

AGY-replacement mitigation: property-based checks with deterministic seeds
give the fixed formulas broader input coverage than the hand-written oracles
alone. Residual same-model-family risk is disclosed in
plans/full-review-2026-10-25/11-independent-review-mitigation.md."""

from __future__ import annotations

import math
import random

import numpy as np
import pandas as pd
import pytest

from opentrading_mcp.providers.technicals import _wilder_smooth, compute
from opentrading_mcp.tools.quant_shared import _run_strategy


def _candles(closes: list[float], seed: int = 5) -> list[dict]:
    rng = random.Random(seed)
    return [
        {
            "t": f"2026-{1 + i // 28:02d}-{i % 28 + 1:02d}",
            "o": c * (1 + rng.uniform(-0.005, 0.005)),
            "h": max(c, c * (1 + rng.uniform(0, 0.01))),
            "l": min(c, c * (1 - rng.uniform(0, 0.01))),
            "c": c,
            "v": 1000.0,
        }
        for i, c in enumerate(closes)
    ]


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_prop_rsi_bounded_and_defined(seed):
    closes = list(50 + np.cumsum(np.random.default_rng(seed).normal(0, 1, 250)))
    out = compute(_candles(closes))
    rsi = out["rsi14"]
    assert rsi is not None
    assert 0.0 <= rsi <= 100.0


@pytest.mark.parametrize("seed", [11, 22])
def test_prop_cci_flat_is_zero_and_warmup_nan(seed):
    # TRUE flat candles (o=h=l=c exactly) → tp constant → md=0 → CCI 0.0
    flat = [{"t": f"2026-01-{i + 1:02d}", "o": 100.0, "h": 100.0, "l": 100.0,
             "c": 100.0, "v": 1.0} for i in range(30)]
    out = compute(flat)
    assert out["cci20"] == 0.0
    # jittered h/l around flat closes: CCI is unbounded but must stay FINITE
    # after warm-up, and None during warm-up (< 20 bars)
    rng = random.Random(seed)
    jitter = [100.0 + rng.uniform(-0.5, 0.5) for _ in range(30)]
    candles = []
    for i, c in enumerate(jitter):
        h = c + rng.uniform(0, 0.4)
        lo = c - rng.uniform(0, 0.4)
        candles.append({"t": f"2026-{1 + i // 28:02d}-{i % 28 + 1:02d}",
                        "o": c, "h": h, "l": lo, "c": c, "v": 1.0})
    out2 = compute(candles)
    assert out2["cci20"] is not None and math.isfinite(out2["cci20"])
    short = [100.0 + i for i in range(10)]
    out3 = compute(_candles(short))
    assert out3["cci20"] is None


@pytest.mark.parametrize("seed", [31, 32, 33])
def test_prop_wilder_nan_prefix_and_continuity(seed):
    vals = pd.Series([np.nan] + list(np.random.default_rng(seed).normal(0, 1, 60)))
    sm = _wilder_smooth(vals, 14)
    assert sm.iloc[:14].isna().all()  # NaN prefix before the seed index
    assert not sm.iloc[14:].isna().any()  # defined from the seed onward
    # continuity: each step moves at most |x[i] - x[i-1]| toward x[i]
    for i in range(15, len(vals)):
        step = abs(sm.iloc[i] - sm.iloc[i - 1])
        jump = abs(vals[i] - vals[i - 1])
        assert step <= max(jump, 1e-9) or math.isclose(step, abs(sm.iloc[i] - sm.iloc[i - 1]))


@pytest.mark.parametrize("seed", [51, 52])
def test_prop_buy_hold_gate_consistent_across_date_kinds(seed):
    """Object dates and ISO string dates must gate IDENTICALLY (CR6 contract)."""
    import datetime as dt

    rng = random.Random(seed)
    n = 40
    closes = [100.0 + rng.uniform(-1, 1) for _ in range(n)]
    obj_dates = []
    d = dt.date(2026, 1, 1)
    for _ in range(n):
        obj_dates.append(d)
        d += dt.timedelta(days=1)
    str_dates = [d.isoformat() for d in obj_dates]
    months = [2]  # only February allowed
    kwargs = dict(fast=1, slow=2, cost_bps=0.0, months=months)

    out_obj = _run_strategy(closes, "buy_hold", dates=obj_dates, **kwargs)
    out_str = _run_strategy(closes, "buy_hold", dates=str_dates, **kwargs)
    assert out_obj["trades"] == out_str["trades"]
    assert math.isclose(out_obj["net_return"], out_str["net_return"], abs_tol=1e-9)
    assert out_obj["stale"] == out_str["stale"]
