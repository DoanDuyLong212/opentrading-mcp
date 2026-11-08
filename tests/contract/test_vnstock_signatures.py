"""Signature contract against the REAL vnstock 6 classes (#93, part 1).

Every vnstock-facing test fakes its own Market/Reference/fa, so the suite stays
green even when the adapter calls a shape the library does not have — the
review proved it by replacing vnstock with modules where every call raises. This
test needs no key and no network: it builds the real objects offline and
checks each attribute chain and keyword the adapter uses. It skips when the
wheels are absent (stand-ins from conftest).
"""

from __future__ import annotations

import inspect
import sys

import pytest

vnstock = pytest.importorskip("vnstock")
if getattr(sys.modules.get("vnstock"), "__stand_in__", False):
    pytest.skip("vnstock stand-in active (wheel not installed)", allow_module_level=True)


def _params(fn) -> tuple[set[str], bool]:
    sig = inspect.signature(fn)
    names = {p.name for p in sig.parameters.values()}
    var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    return names, var_kw


def _accepts(fn, *keywords: str) -> None:
    names, _var_kw = _params(fn)
    missing = [k for k in keywords if k not in names]
    assert not missing, f"{fn.__qualname__} has no parameter(s) {missing}: {inspect.signature(fn)}"


@pytest.mark.parametrize("source", ["ssi", "dnse"])
def test_equity_group_is_callable_and_has_ohlcv(source):
    from vnstock import Market

    group = Market(source).equity
    assert callable(group)  # Market(src).equity(symbol)...
    _accepts(group("FPT").ohlcv, "start", "end", "interval", "count_back")


def test_equity_group_quote_takes_symbols():
    """#84: the batch-quote path calls Market(src).equity.quote(symbols=...)."""
    from vnstock import Market

    _accepts(Market("ssi").equity.quote, "symbols")


def test_trades_take_start_end_limit():
    from vnstock import Market

    _accepts(Market("dnse").equity("FPT").trades, "start", "end", "limit")


@pytest.mark.parametrize("group", ["index", "futures"])
def test_index_and_futures_ohlcv(group):
    from vnstock import Market

    _accepts(getattr(Market("ssi"), group)("X").ohlcv, "start", "end", "interval", "count_back")


def test_crypto_ohlcv_on_binance():
    from vnstock import Market

    _accepts(Market("binance").crypto("BTCUSDT").ohlcv, "count_back", "interval")


def test_reference_listing_methods():
    from vnstock import Reference

    equity = Reference("ssi").equity
    for name in ("list", "list_by_group", "list_by_industry", "list_by_exchange"):
        assert callable(getattr(equity, name)), name
    _accepts(equity.list_by_group, "group")


def test_events_calendar_takes_a_window_and_symbol():
    from vnstock import Reference

    _accepts(Reference("ssi").events.calendar, "start", "end", "symbol")


def test_error_classes_the_adapter_matches_by_name_exist():
    """_error_kind matches these class names (#83); a rename would silently
    turn rate limits into plain failures again."""
    import vnstock.errors as errors

    for name in ("RateLimitedError", "RateLimitError", "CredentialError", "AccessDeniedError"):
        assert hasattr(errors, name), name


def test_fa_signatures():
    fa = pytest.importorskip("vnstock_quant").fa
    _accepts(fa.ratios, "data", "ids", "period", "format")
    _accepts(fa.Dataset.load, "symbols", "period", "source", "estimate_shares")
    _accepts(fa.Dataset.from_frames, "statements", "prices", "estimate_shares")
