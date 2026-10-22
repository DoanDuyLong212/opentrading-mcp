"""Technicals report null instead of invented values; Ichimoku uses the standard formula.

Fixture: live FPT daily candles to 2026-10-22. On that day signals_technical
gave tenkan 57.47 where the standard (highest high + lowest low) / 2 over 9 bars
is 57.30, and on 1W it showed cci20 0.0 and ema50 70.61 while sma50 was null.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opentrading_mcp.providers import technicals as tech

CANDLES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "fpt_1d_20261022.json").read_text(encoding="utf-8")
)["candles"]


def _mid(rows: list[dict[str, Any]], n: int) -> float:
    window = rows[-n:]
    return (max(r["h"] for r in window) + min(r["l"] for r in window)) / 2


def test_ichimoku_lines_are_high_low_midpoints():
    ich = tech.compute(CANDLES)["ichimoku"]
    assert ich["tenkan"] == pytest.approx(_mid(CANDLES, 9), abs=0.01)
    assert ich["kijun"] == pytest.approx(_mid(CANDLES, 26), abs=0.01)
    assert ich["senkou_b_ahead"] == pytest.approx(_mid(CANDLES, 52), abs=0.01)


def test_ichimoku_cloud_under_price_is_the_spans_from_26_bars_ago():
    full = tech.compute(CANDLES)["ichimoku"]
    earlier = tech.compute(CANDLES[:-26])["ichimoku"]
    assert full["senkou_a"] == earlier["senkou_a_ahead"]
    assert full["senkou_b"] == earlier["senkou_b_ahead"]
    assert full["chikou"] == round(CANDLES[-27]["c"], 2)


def test_ichimoku_without_a_cloud_has_no_signal():
    # 40 bars: tenkan/kijun exist, but no span was computed 26 bars ago yet.
    ich = tech.compute(CANDLES[:40])["ichimoku"]
    assert ich["tenkan"] is not None and ich["kijun"] is not None
    assert ich["senkou_a"] is None and ich["senkou_b"] is None
    assert ich["signal"] is None


def test_short_history_gives_null_not_neutral_numbers():
    out = tech.compute(CANDLES[:10])
    for key in ("rsi14", "cci20", "adx14", "atr14", "ao", "momentum10", "ema20", "ema50",
                "stoch_k", "stoch_d"):
        assert out[key] is None, key
    assert out["macd"] == {"line": None, "signal": None, "hist": None}
    assert out["ema10"] is not None
    assert out["recommend"] == "Neutral"


def test_ema_and_macd_wait_for_their_window():
    out = tech.compute(CANDLES[:40])
    assert out["ema50"] is None and out["sma50"] is None
    assert out["macd"]["line"] is not None  # 26 bars
    assert out["macd"]["signal"] is not None  # 26 + 9 - 1 = 34 bars
    assert out["cci20"] is not None and out["ao"] is not None


def test_adx_is_not_averaged_over_warm_up_zeros():
    # DI needs 14 bars, ADX 14 more DX values: 20 bars is not enough.
    assert tech.compute(CANDLES[:20])["adx14"] is None
    assert tech.compute(CANDLES[:40])["adx14"] is not None
