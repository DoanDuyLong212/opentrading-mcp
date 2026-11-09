"""An empty answer must not open the shared "vnstock" breaker (found 2026-11-09).

During HOSE ATO (09:00-09:15) DNSE has no trade yet, so ``equity_trades`` raised
"no data for trades FPT (dnse: empty)". That counted as an upstream failure on the
breaker that 14 vnstock routes share: five empty answers in a row (an ATO poll, a
scan over illiquid symbols) would have blocked candles, indices and the listing
for 60 s.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.providers import circuit
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderNoData, ProviderUnavailable


@pytest.fixture(autouse=True)
def _fresh_breaker():
    circuit.reset("test-no-data")
    yield
    circuit.reset("test-no-data")


def _calls(n: int, exc: Exception) -> None:
    breaker = circuit.get_circuit("test-no-data")
    for _ in range(n):
        with pytest.raises(ProviderUnavailable):
            breaker.call(lambda: (_ for _ in ()).throw(exc))


def test_empty_answers_do_not_open_the_breaker():
    _calls(10, ProviderNoData("no data for trades FPT (dnse: empty)"))
    assert circuit.get_circuit("test-no-data").call(lambda: "ok") == "ok"


def test_real_failures_still_open_it():
    _calls(5, ProviderUnavailable("dnse timeout"))
    with pytest.raises(circuit.CircuitOpenError):
        circuit.get_circuit("test-no-data").call(lambda: "ok")


def test_all_sources_empty_is_no_data_but_errors_are_not():
    assert isinstance(vn_p._chain_error("trades FPT", [], ["dnse"]), ProviderNoData)
    mixed = vn_p._chain_error("candles FPT", [("ssi", RuntimeError("HTTP 502"))], ["dnse"])
    assert type(mixed) is ProviderUnavailable


def test_rewrap_keeps_the_no_data_class():
    inner = vn_p._chain_error("trades FPT", [], ["dnse"])
    outer = vn_p._rewrap(inner, "vnstock trades failed: FPT")
    assert isinstance(outer, ProviderNoData) and "dnse: empty" in str(outer)
    assert type(vn_p._rewrap(ProviderUnavailable("x"), "y")) is ProviderUnavailable


def test_trades_before_the_first_match_leave_the_vnstock_breaker_closed(monkeypatch):
    import pandas as pd

    circuit.reset("vnstock")
    monkeypatch.setattr(vn_p, "SRC_TRADES", ("dnse",))

    class _Empty:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return lambda *a, **k: self

        def trades(self, *a, **k):
            return pd.DataFrame()

    import vnstock

    monkeypatch.setattr(vnstock, "Market", _Empty, raising=False)
    for _ in range(8):
        with pytest.raises(ProviderNoData):
            vn_p.equity_trades("FPT", limit=10)
    assert circuit.get_circuit("vnstock")._opened_at is None
    circuit.reset("vnstock")
