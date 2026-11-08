"""#89: the parity harness compares VALUES (it used to call any non-empty list a match)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "parity_compare", Path(__file__).resolve().parents[1] / "scripts" / "parity_compare.py"
)
assert _SPEC and _SPEC.loader
parity = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(parity)


def test_candles_match_within_tolerance_and_name_the_worst_day():
    v4 = [{"t": "2026-11-05", "c": 52.9}, {"t": "2026-11-06", "c": 50.8}]
    v6 = [{"time": "2026-11-05T07:00:00+07:00", "close": 52.9},
          {"time": "2026-11-06T07:00:00+07:00", "close": 50.9}]
    status, detail = parity.compare_candles(v4, v6)
    assert status == "match" and "2 shared days" in detail and "2026-11-06" in detail


def test_candles_flag_a_unit_error():
    """The #77 class of bug: an index served /1000 must be a DIFF, not a match."""
    status, detail = parity.compare_candles(
        [{"t": "2026-11-06", "c": 1764.3}], [{"t": "2026-11-06", "c": 1.76}]
    )
    assert status == "DIFF" and "1764.3" in detail


def test_candles_without_overlap_are_not_a_match():
    status, _ = parity.compare_candles([{"t": "2026-10-01", "c": 1.0}],
                                       [{"t": "2026-11-01", "c": 1.0}])
    assert status == "NO OVERLAP"


def test_crypto_unit_change_is_recognised():
    """v4 priced BTCUSDT in VND; a USD/VND-sized ratio is that unit change."""
    v4 = [{"time": "2026-11-07", "close": 1937606367.08}]
    v6 = [{"time": "2026-11-07T00:00:00+00:00", "close": 75855.44}]
    status, detail = parity.compare_crypto(v4, v6)
    assert status == "expected DIFF (unit VND -> USDT)" and "25,54" in detail
    same = [{"t": "x", "c": 75855.0}]
    assert parity.compare_crypto(same, same)[0] == "match"


def test_listing_compares_symbols_and_names():
    v4 = [{"symbol": "A32", "name": "Công ty Cổ phần 32"}, {"symbol": "AAA", "name": "X"}]
    v6 = [{"symbol": "A32", "name": "Công ty Cổ phần 32"}, {"symbol": "AAA", "name": "Y"}]
    status, detail = parity.compare_listing(v4, v6)
    assert status == "match" and "names equal for 1/2" in detail
    status, _ = parity.compare_listing(v4, v6[:1])
    assert status == "DIFF"


def test_ratios_compare_values_on_shared_periods():
    v4 = {"periods": ["2025", "2024"], "ratios": [
        {"item_id": "p_e", "values": {"2025": 15.91, "2024": 26.74}},
        {"item_id": "trailing_eps", "values": {"2025": 6021.21}}]}
    v6 = {"periods": ["2025"], "ratios": [
        {"item_id": "p_e", "values": {"2025": 15.91}},
        {"item_id": "trailing_eps", "values": {"2025": 6021.0}}]}
    status, detail = parity.compare_ratios(v4, v6)
    assert status == "match" and "2 values on 1 periods" in detail
    v6["ratios"][0]["values"]["2025"] = 0.016  # a P/E off by 1000x
    assert parity.compare_ratios(v4, v6)[0] == "DIFF"


def test_render_writes_totals():
    text = parity.render([{"probe": "a", "status": "match", "detail": "x"},
                          {"probe": "b", "status": "match", "detail": "y"}])
    assert "| a | match | x |" in text and "Totals: match 2" in text
