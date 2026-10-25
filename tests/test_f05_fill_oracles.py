"""F05 oracles — fill convention, missing-condition gating, stale flag.

F05a: decision at close[i-1] fills at open[i]; holding accrues open-to-open.
F05b: missing cond_ok data blocks entry (never authorizes a trade).
F05c: missing/short dates surface as stale=true in the output.
Expected values are hand-derived from the definitions, not from the engine.
"""

from __future__ import annotations

from opentrading_mcp.tools.quant_shared import _run_strategy


def _bars(closes, opens, month=1):
    dates = [f"2026-{month:02d}-{i + 1:02d}" for i in range(len(closes))]
    return closes, opens, dates


def test_f05a_next_bar_open_fill_hand_computed():
    """Single entry: signal at close[0], fill at open[1], hold open[1]→open[2],
    marked to close[2]. All fees zero.

    closes = [100, 110, 121]; opens = [100, 100, 110]
    pos = buy_hold (ungated) → pos = [1,1,1]
    fill at open[1]=100; holding leg open[1]→open[2] = +10%
    final mark: close[2]/open[2] = 121/110 = +10%
    equity = 1 * 1.10 * 1.10 = 1.21 → net_return = 0.21
    """
    closes = [100.0, 110.0, 121.0]
    opens = [100.0, 100.0, 110.0]
    closes_b, opens_b, dates = _bars(closes, opens)
    out = _run_strategy(
        closes_b, "buy_hold", fast=1, slow=2, cost_bps=0.0, dates=dates, opens=opens_b
    )
    assert out["fill"] == "next-bar-open"
    assert out["trades"] == 1
    assert abs(out["net_return"] - 0.21) < 1e-6, out


def test_f05a_exit_fills_at_next_open():
    """Exit signal at close[2] must fill at open[3] (next open), not at the
    signal close.

    closes = [100, 90, 95, 105]; opens = [100, 100, 89, 94]
    cond_ok = [True, True, False, False] → pos = [1, 1, 0, 0]
    Entry: decision pos[0] at close[0] → fill open[1] = 100
    Held leg  open[1]→open[2] = 100→89   (-11%)
    Exit:     decision pos[2] at close[2] → fill open[3] = 94
    Held leg  open[2]→open[3] = 89→94    (+5.618%)
    equity = 0.89 * (94/89) = 0.94 → net_return = -0.06, trades = 1
    """
    closes = [100.0, 90.0, 95.0, 105.0]
    opens = [100.0, 100.0, 89.0, 94.0]
    closes_b, opens_b, dates = _bars(closes, opens)
    out = _run_strategy(
        closes_b,
        "buy_hold",
        fast=1,
        slow=2,
        cost_bps=0.0,
        dates=dates,
        cond_ok=[True, True, False, False],
        opens=opens_b,
    )
    assert out["trades"] == 1, out
    assert abs(out["net_return"] - (-0.06)) < 1e-6, out


def test_f05b_missing_condition_data_blocks_entry():
    """cond_ok shorter than bars: bars beyond the list have no condition data
    and must NOT enter (old code allowed them)."""
    closes = [100.0, 110.0, 121.0, 133.0]
    opens = [100.0, 100.0, 110.0, 121.0]
    closes_b, opens_b, dates = _bars(closes, opens)
    out = _run_strategy(
        closes_b,
        "buy_hold",
        fast=1,
        slow=2,
        cost_bps=0.0,
        dates=dates,
        cond_ok=[True],  # only bar 0 has condition data; bars 1..3 missing
        opens=opens_b,
    )
    # bar 1's decision (pos[0]=1, cond_ok[0]=True) fills at open[1]; bars 2-3
    # have missing condition data → forced flat at their fills.
    # entry open[1]=100, exit open[2]=110 → net +10%.
    assert out["trades"] == 1, out
    assert abs(out["net_return"] - 0.10) < 1e-6, out

    # All-missing cond_ok → no trades at all.
    out2 = _run_strategy(
        closes_b,
        "buy_hold",
        fast=1,
        slow=2,
        cost_bps=0.0,
        dates=dates,
        cond_ok=[None, None, None, None],
        opens=opens_b,
    )
    assert out2["trades"] == 0 and out2["net_return"] == 0.0, out2


def test_f05c_stale_flag_when_dates_missing():
    closes = [100.0, 110.0, 121.0]
    opens = [100.0, 100.0, 110.0]
    # dates shorter than bars → stale observations
    dates_short = ["2026-01-01", "2026-01-02"]
    closes_b, opens_b, _ = _bars(closes, opens)
    out = _run_strategy(
        closes_b,
        "buy_hold",
        fast=1,
        slow=2,
        cost_bps=0.0,
        dates=dates_short,
        opens=opens_b,
    )
    assert out["stale"] is True, out
    assert "stale" in out.get("stale_note", "")

    # complete dates → not stale
    closes_b2, opens_b2, dates_full = _bars(closes, opens)
    out2 = _run_strategy(
        closes_b2,
        "buy_hold",
        fast=1,
        slow=2,
        cost_bps=0.0,
        dates=dates_full,
        opens=opens_b2,
    )
    assert out2["stale"] is False, out2

    # opens unavailable → documented fallback to next-bar-close
    out3 = _run_strategy(closes_b, "buy_hold", fast=1, slow=2, cost_bps=0.0, dates=dates_full)
    assert out3["fill"] == "next-bar-close-fallback", out3
    # next-bar-close fills: entry close[1]=110, mark close[2]=121 → +10%
    assert abs(out3["net_return"] - 0.10) < 1e-6, out3
