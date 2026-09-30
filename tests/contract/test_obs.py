"""Circuit breaker + observability contract tests (no network)."""

import json
import time

import pytest

from opentrading_mcp.providers import circuit
from opentrading_mcp.providers.errors import ProviderAuthMissing, ProviderUnavailable


def _flaky(failures: int, value: str = "ok"):
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if state["calls"] <= failures:
            raise ProviderUnavailable("downstream timeout")
        return value

    fn.state = state  # type: ignore[attr-defined]
    return fn


def test_closed_breaker_passes_through():
    breaker = circuit.CircuitBreaker("test", failure_threshold=3, recovery_timeout=60.0)
    assert breaker.call(_flaky(0)) == "ok"


def test_breaker_opens_after_threshold():
    breaker = circuit.CircuitBreaker("test", failure_threshold=3, recovery_timeout=60.0)
    fn = _flaky(10)
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            breaker.call(fn)
    assert fn.state["calls"] == 3
    with pytest.raises(circuit.CircuitOpenError):
        breaker.call(fn)
    assert fn.state["calls"] == 3  # no further upstream calls while open


def test_breaker_recovers_after_timeout():
    breaker = circuit.CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.05)
    fn = _flaky(2)
    with pytest.raises(ProviderUnavailable):
        breaker.call(fn)
    with pytest.raises(ProviderUnavailable):
        breaker.call(fn)
    with pytest.raises(circuit.CircuitOpenError):
        breaker.call(fn)
    time.sleep(0.06)
    assert breaker.call(fn) == "ok"


def test_auth_errors_do_not_trip_breaker():
    breaker = circuit.CircuitBreaker("test", failure_threshold=2, recovery_timeout=60.0)

    def bad_auth():
        raise ProviderAuthMissing("bad key")

    for _ in range(5):
        with pytest.raises(ProviderAuthMissing):
            breaker.call(bad_auth)
    assert breaker.call(_flaky(0)) == "ok"


def test_open_breaker_is_caught_as_provider_unavailable():
    from opentrading_mcp.providers.errors import ProviderUnavailable as BaseUnavailable

    assert issubclass(circuit.CircuitOpenError, BaseUnavailable)
    circuit.reset("test-upstream-2")

    @circuit.guarded("test-upstream-2")
    def always_down():
        raise ProviderUnavailable("down")

    for _ in range(5):
        try:
            always_down()
        except BaseUnavailable:
            pass
        else:
            raise AssertionError("expected ProviderUnavailable")
    circuit.reset("test-upstream-2")


def test_guarded_decorator_uses_named_breaker():
    @circuit.guarded("test-upstream")
    def maybe():
        raise ProviderUnavailable("down")

    circuit.reset("test-upstream")
    for _ in range(5):
        with pytest.raises(ProviderUnavailable):
            maybe()
    with pytest.raises(circuit.CircuitOpenError):
        maybe()
    circuit.reset("test-upstream")


def test_metrics_render_prometheus_lines():
    from opentrading_mcp import obs

    obs.reset()
    obs.record_tool_call("market_snapshot", duration_ms=120.0, ok=True, error_code="")
    obs.record_tool_call(
        "market_snapshot", duration_ms=80.0, ok=False, error_code="upstream_timeout"
    )
    text = obs.render_metrics()
    assert 'tool_calls_total{tool="market_snapshot"} 2' in text
    assert 'tool_errors_total{tool="market_snapshot",error="upstream_timeout"} 1' in text
    assert "tool_latency_ms_sum" in text


def test_log_line_has_no_args_or_data(capsys):
    from opentrading_mcp import obs

    obs.log_tool_call("vs_financial_values", duration_ms=10.0, ok=True, error_code="")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    entry = json.loads(line)
    assert entry["event"] == "tool_call"
    assert entry["tool"] == "vs_financial_values"
    assert "args" not in entry and "data" not in entry and "output" not in entry


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
