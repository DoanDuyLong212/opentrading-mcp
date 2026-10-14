"""Unit tests for HTTP pooling + GDELT throttle fail-fast (offline-safe).

The shared client avoids re-paying TCP+TLS handshakes (~11s observed to some
hosts); the throttle flag turns repeated 40s+ sleep+retry burns into instant
failures while GDELT rate-limits this IP.
"""

from __future__ import annotations

import time

from opentrading_mcp.providers import intel as intel_mod
from opentrading_mcp.providers.circuit import reset as circuit_reset
from opentrading_mcp.providers.errors import ProviderUnavailable


def test_shared_client_is_singleton():
    assert intel_mod._client() is intel_mod._client()


def test_gdelt_throttle_short_circuits_without_network():
    intel_mod._GDELT_THROTTLED_UNTIL = time.monotonic() + 300
    try:
        t0 = time.monotonic()
        try:
            intel_mod.gdelt_events.__wrapped__("x", 1)
        except ProviderUnavailable as exc:
            dt = time.monotonic() - t0
            assert "throttled" in str(exc)
            assert dt < 2.0, dt
        else:
            raise AssertionError("expected ProviderUnavailable")
    finally:
        intel_mod._GDELT_THROTTLED_UNTIL = 0.0


def test_gdelt_429_sets_throttle_flag(monkeypatch):
    def fake_get_json(url, params=None, timeout=20):
        raise ProviderUnavailable(f"rate limited: {url}")

    monkeypatch.setattr(intel_mod, "_get_json", fake_get_json)
    monkeypatch.setattr("time.sleep", lambda s: None)
    circuit_reset("gdelt")
    intel_mod._GDELT_THROTTLED_UNTIL = 0.0
    try:
        try:
            intel_mod.gdelt_events.__wrapped__("x", 1)
        except ProviderUnavailable:
            pass
        assert intel_mod._GDELT_THROTTLED_UNTIL > time.monotonic()
        t0 = time.monotonic()
        try:
            intel_mod.gdelt_events.__wrapped__("x", 1)
        except ProviderUnavailable as exc:
            assert "throttled" in str(exc)
            assert time.monotonic() - t0 < 2.0
        else:
            raise AssertionError("expected ProviderUnavailable")
    finally:
        intel_mod._GDELT_THROTTLED_UNTIL = 0.0
        circuit_reset("gdelt")
