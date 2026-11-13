"""A vendor-refused vnstock release (13/11/2026: "Bản vnstock 6.0.0rc5 đã bị tắt…").

It was reported as reason "unknown", opened the shared vnstock breaker, lost its code
and URL to a 160-character cut, and market_candles_batch showed it with warnings [].
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from opentrading_mcp.providers import circuit
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderUnavailable
from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.tools.vn import _na as vn_na

URL = "https://vnstocks.com/onboard-member/migration"
MESSAGE = (
    "Bản vnstock 6.0.0rc5 đã bị tắt. Dừng hoạt động các phiên bản vnstock cũ trước "
    f"phiên bản 6.0.0 từ 11/11/2026. Chuyển đổi theo hướng dẫn: {URL}"
)


class PolicyError(Exception):
    """Shape of vnstock.errors.PolicyError: message, code, context in str()."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return f"{self.message} (code={self.code}, update_command=pip install -U …)"


class AuthError(Exception):
    def __init__(self, message: str, code: str = "VNSTOCK_AUTH_DEVICE_LIMIT") -> None:
        super().__init__(message)
        self.code = code


def _refused(code: str = "VNSTOCK_RELEASE_DISABLED") -> Any:
    def call() -> Any:
        raise PolicyError(MESSAGE, code)

    return call


@pytest.mark.parametrize(
    "code", ["VNSTOCK_RELEASE_DISABLED", "VNSTOCK_RELEASE_EXPIRED", "VNSTOCK_SOURCE_DISABLED"]
)
def test_chain_error_is_vendor_disabled_and_keeps_code_and_url(code):
    with pytest.raises(ProviderUnavailable) as caught:
        vn_p._fetch_frame([("ssi", _refused(code)), ("dnse", _refused(code))], "candles HPG")
    exc = caught.value
    assert exc.reason == "vendor_disabled"
    assert code in str(exc)
    assert URL in str(exc)
    assert "upgrade" in str(exc)


def test_refusal_beats_other_errors_in_the_chain():
    def timeout() -> Any:
        raise TimeoutError("dnse timeout")

    with pytest.raises(ProviderUnavailable) as caught:
        vn_p._fetch_frame([("ssi", _refused()), ("dnse", timeout)], "candles HPG")
    assert caught.value.reason == "vendor_disabled"


def test_envelope_is_not_retryable():
    try:
        vn_p._fetch_frame([("ssi", _refused())], "candles HPG")
    except ProviderUnavailable as exc:
        env = vn_na("vn_quote_history", str(exc))
    assert (env["reason"], env["retryable"]) == ("vendor_disabled", False)


@pytest.mark.parametrize(
    "text",
    [
        f"events calendar: fetch failed: {MESSAGE}",
        "x failed (code=VNSTOCK_RELEASE_EXPIRED)",
        "y: VNSTOCK_SOURCE_DISABLED: nguồn ssi đang tắt",
    ],
)
def test_text_only_refusal_is_classified(text):
    """Envelopes built outside the except block only have the warning text."""
    env = vn_na("x", text)
    assert env["reason"] == "vendor_disabled"


def test_wrapped_refusal_is_classified_from_its_cause():
    """Paths that raise 'vnstock listing failed' from the vendor error."""
    try:
        try:
            raise PolicyError(MESSAGE, "VNSTOCK_RELEASE_EXPIRED")
        except PolicyError as inner:
            raise ProviderUnavailable("vnstock listing failed") from inner
    except ProviderUnavailable as exc:
        env = vn_na("vn_listing", str(exc))
    assert env["reason"] == "vendor_disabled"


def test_refusal_does_not_open_the_breaker():
    breaker = circuit.CircuitBreaker("vnstock-test", failure_threshold=2, recovery_timeout=60.0)

    def refused() -> None:
        vn_p._fetch_frame([("ssi", _refused())], "candles X")

    for _ in range(5):
        with pytest.raises(ProviderUnavailable) as caught:
            breaker.call(refused)
        assert caught.value.reason == "vendor_disabled"  # never "circuit … is open"


def test_device_limit_and_auth_error_are_auth_not_outage():
    def device() -> Any:
        raise AuthError("device limit reached")

    with pytest.raises(ProviderUnavailable) as caught:
        vn_p._fetch_frame([("ssi", device)], "candles HPG")
    assert caught.value.reason == "not_configured"
    assert "rejected" in str(caught.value)


async def test_candles_batch_reports_the_failures_in_warnings(monkeypatch):
    def refused(symbol: str, days: int, *a: Any, **k: Any) -> Any:
        vn_p._fetch_frame([("ssi", _refused())], f"candles {symbol}")

    monkeypatch.setattr(vn_p, "quote_history", refused)
    server = create_server()
    register_all(server)
    tool = server._tool_manager.get_tool("market_candles_batch")
    tag = uuid.uuid4().hex[:6].upper()  # the envelope cache may outlive one run
    syms = [f"Z{tag}{i}" for i in range(7)]
    env = await tool.run({"symbols": syms, "days": 11})
    assert env["availability"] == "unavailable"
    assert env["reason"] == "vendor_disabled"
    assert env["retryable"] is False
    # one shared cause: one warning naming the symbols, not seven copies
    assert len(env["warnings"]) == 1
    assert env["warnings"][0].startswith(", ".join(syms[:5]) + " +2: ")
    assert URL in env["warnings"][0]
    assert len(env["data"]["missing"]) == 7
