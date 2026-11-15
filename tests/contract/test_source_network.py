"""A source that never answers (vnstock-oapi NetworkError, code VNSTOCK_SOURCE_NETWORK).

Prod, 15/11/2026: DNSE blocks the Render IP, so vn_trades failed with
"dnse: Hết thời gian chờ: ConnectTimeout (code=VNSTOCK_SOURCE_NETWORK, source=dnse)"
and was reported as reason "unknown". The same timeouts also counted toward the shared
"vnstock" breaker that the candle, index and futures tools use.
"""

from __future__ import annotations

import sys
import time
import types
from typing import Any

import pytest

from opentrading_mcp.providers import circuit
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.tools.vn import _na as vn_na

TEXT = "Hết thời gian chờ: ConnectTimeout"


class NetworkError(Exception):
    """Shape of vnstock.errors.NetworkError."""

    def __init__(self, message: str = TEXT) -> None:
        super().__init__(message)
        self.code = "VNSTOCK_SOURCE_NETWORK"

    def __str__(self) -> str:
        return f"{self.args[0]} (code={self.code}, source=dnse)"


def _down(message: str = TEXT) -> Any:
    def call() -> Any:
        raise NetworkError(message)

    return call


def test_timeout_is_upstream_timeout_and_retryable():
    with pytest.raises(ProviderUnavailable) as caught:
        vn_p._fetch_frame([("dnse", _down())], "trades FPT")
    assert caught.value.reason == "upstream_timeout"
    env = vn_na("vn_trades", f"vnstock trades failed: FPT: {caught.value}")
    assert (env["reason"], env["retryable"]) == ("upstream_timeout", True)


def test_connection_refused_is_upstream_down():
    with pytest.raises(ProviderUnavailable) as caught:
        vn_p._fetch_frame([("dnse", _down("connection refused"))], "trades FPT")
    assert caught.value.reason == "upstream_down"


def test_mixed_with_a_plain_error_stays_unclassified_by_the_chain():
    def broken() -> Any:
        raise ValueError("bad payload")

    with pytest.raises(ProviderUnavailable) as caught:
        vn_p._fetch_frame([("ssi", broken), ("dnse", _down())], "candles FPT")
    assert caught.value.reason is None


@pytest.mark.parametrize(
    "text",
    [
        "vnstock trades failed: FPT: no data for trades FPT (dnse: Hết thời gian chờ: "
        "ConnectTimeout (code=VNSTOCK_SOURCE_NETWORK, source=dnse))",
        "x: ReadTimeout",
    ],
)
def test_text_only_timeout_is_classified(text):
    assert vn_na("vn_trades", text)["reason"] == "upstream_timeout"


def test_text_only_network_code_is_upstream_down():
    text = "x (code=VNSTOCK_SOURCE_NETWORK, source=dnse)"
    assert vn_na("vn_trades", text)["reason"] == "upstream_down"


def test_trades_timeouts_never_open_the_vnstock_breaker(monkeypatch):
    class Market:
        def __init__(self, source: str) -> None:
            pass

        def equity(self, symbol: str) -> Any:
            return self

        def trades(self, **kwargs: Any) -> Any:
            raise NetworkError()

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Market=Market))
    circuit.reset("vnstock")
    circuit.reset("vnstock-trades")
    try:
        threshold = circuit.get_circuit("vnstock-trades").failure_threshold
        for _ in range(threshold + 2):
            with pytest.raises(ProviderUnavailable):
                vn_p.equity_trades("FPT")
        now = time.monotonic()
        assert circuit.get_circuit("vnstock")._failures == 0
        assert not circuit.get_circuit("vnstock")._is_open(now)
        assert circuit.get_circuit("vnstock-trades")._is_open(now)
    finally:
        circuit.reset("vnstock")
        circuit.reset("vnstock-trades")
