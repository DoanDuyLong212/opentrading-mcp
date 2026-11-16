"""#118: after one DNSE connect timeout, DNSE calls fail at once for a while.

On prod (16/11/2026) dnse_ohlc_history, dnse_latest_trade, dnse_orderbook and then
vn_equity_quote_batch each waited the full 20 s connect timeout in a row.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from opentrading_mcp.providers import circuit, dnse, dnse_board
from opentrading_mcp.providers.errors import ProviderUnavailable


class _Client:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(url)
        if self.exc is not None:
            raise self.exc
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("DNSE_API_KEY", "k")
    monkeypatch.setenv("DNSE_SECRET", "s")
    monkeypatch.setenv("DNSE_API_SECRET", "s")
    circuit.reset("dnse")
    yield
    circuit.reset("dnse")


def _use(monkeypatch, client: _Client) -> None:
    monkeypatch.setattr(dnse, "shared_client", lambda: client)


def test_connect_timeout_makes_the_next_call_fail_at_once(monkeypatch):
    client = _Client(httpx.ConnectTimeout("connect timed out"))
    _use(monkeypatch, client)
    with pytest.raises(ProviderUnavailable, match="dnse timeout"):
        dnse._get("/price/FPT/quotes/latest")
    with pytest.raises(ProviderUnavailable, match="dnse unreachable") as fast:
        dnse._get("/price/FPT/trades/latest")
    assert len(client.calls) == 1  # the second call never reached the network
    assert fast.value.reason == "upstream_down"
    assert 0 < fast.value.retry_after_s <= dnse.CONNECT_DOWN_FOR_S + 1
    # the board treats it as unreachable, so it still falls back to ssi
    assert dnse_board._unreachable(fast.value)


def test_a_read_timeout_does_not_arm_the_window(monkeypatch):
    client = _Client(httpx.ReadTimeout("read timed out"))
    _use(monkeypatch, client)
    for _ in range(2):
        with pytest.raises(ProviderUnavailable, match="dnse timeout"):
            dnse._get("/price/FPT/quotes/latest")
    assert len(client.calls) == 2


def test_dnse_is_tried_again_when_the_window_ends(monkeypatch):
    _use(monkeypatch, _Client(httpx.ConnectTimeout("connect timed out")))
    with pytest.raises(ProviderUnavailable):
        dnse._get("/price/FPT/quotes/latest")
    monkeypatch.setattr(dnse, "_connect_down_until", 0.0)  # the window has passed
    healthy = _Client()
    _use(monkeypatch, healthy)
    assert dnse._get("/price/FPT/quotes/latest") == {"ok": True}
    assert len(healthy.calls) == 1
