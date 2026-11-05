"""Unavailable envelopes say why, in fields a client can act on.

`warnings` alone left clients unable to tell a passing outage from a missing key.
"""

from __future__ import annotations

import functools
import time
from typing import Any

import httpx
import pytest

from opentrading_mcp.failures import ALTERNATIVES, UPSTREAMS
from opentrading_mcp.providers import circuit
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.server import create_server, register_all
from opentrading_mcp.tools import shared
from opentrading_mcp.tools.brief import _na as brief_na
from opentrading_mcp.tools.vn import _na as vn_na

FAILURE_FIELDS = {"reason", "retryable", "retry_after_s", "alternatives"}


def _server():
    server = create_server()
    register_all(server)
    return server


def _caught(exc: Exception, tool: str = "some_tool") -> dict[str, Any]:
    """The envelope a tool builds inside `except ... as exc`, as nearly all of them do."""
    try:
        raise exc
    except Exception as caught:
        return vn_na(tool, str(caught))


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("vietstock timeout: /data/x", "upstream_timeout"),
        ("vn_quote_history timed out after 60.0s", "upstream_timeout"),
        ("fetch timed out: https://example.com", "upstream_timeout"),
        ("dnse unreachable: /price", "upstream_down"),
        ("vietstock retry exhausted: /data/x", "upstream_down"),
        ("adsb.lol HTTP 503", "upstream_down"),
        ("cannot resolve example.com", "upstream_down"),
        ("ws worker has not published yet", "upstream_down"),
        ("rate limited: https://example.com", "upstream_rate_limited"),
        ("upstream rate limit reached: quota", "upstream_rate_limited"),
        ("gdelt throttled, retry later", "upstream_rate_limited"),
        ("x briefly unavailable (recent timeout), retry shortly", "recent_failure"),
        ("x shed: server busy (9 calls outstanding), retry shortly", "busy"),
    ],
)
def test_each_temporary_reason_is_retryable(message, reason):
    env = _caught(ProviderUnavailable(message))
    assert env["reason"] == reason
    assert env["retryable"] is True
    assert env["warnings"] == [message]


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("VIETSTOCK_COOKIE_HEADER/HAR not configured", "not_configured"),
        ("FRED_API_KEY is not set", "not_configured"),
        ("VIETSTOCK_EMAIL/VIETSTOCK_PASSWORD are not set", "not_configured"),
        ("vietstock session rejected", "auth_missing"),
        ("vietstock package limited: 123", "auth_missing"),
        ("vietstock UpgradeRequired: please upgrade", "auth_missing"),
    ],
)
def test_config_failures_are_not_retryable(message, reason):
    env = _caught(ProviderAuthMissing(message))
    assert env["reason"] == reason
    assert env["retryable"] is False
    assert "retry_after_s" not in env


@pytest.mark.parametrize(
    "exc",
    [
        ProviderUnavailable("no candles for FPT"),
        ProviderUnavailable("vnstock not installed"),
        ProviderBadData("unknown interval '2D' (1D|1W|1M)"),
        ValueError("filter error: bad column"),
    ],
)
def test_unclassified_failures_are_unknown_without_retryable(exc):
    env = _caught(exc, "vn_fundamentals")
    assert env["reason"] == "unknown"
    assert not FAILURE_FIELDS & set(env) - {"reason"}


def test_failures_outside_except_are_classified_from_text():
    """market_overview joins its failed legs, long after each except ended."""
    joined = "vietstock timeout: /a; dnse unreachable: /b"
    assert vn_na("market_overview", joined)["reason"] == "upstream_timeout"
    env = brief_na("brief_build", "FIREANT_TOKEN is not set")
    assert (env["reason"], env["retryable"]) == ("not_configured", False)
    assert vn_na("breadth_scan", "unknown exchange 'X' (HOSE|HNX|UPCOM)")["reason"] == "unknown"


def test_upper_case_ticker_is_not_a_keyword():
    assert vn_na("x", "no candles for TIMEOUT")["reason"] == "unknown"


def test_exception_the_warning_does_not_report_is_ignored():
    """A retry hint must come from the failure being reported, not an older one."""
    try:
        raise ProviderUnavailable("earlier failure", retry_after_s=30)
    except ProviderUnavailable:
        env = vn_na("x", "vietstock timeout: /a")
    assert env["reason"] == "upstream_timeout"
    assert "retry_after_s" not in env


@pytest.mark.parametrize(
    ("cause", "reason"),
    [
        (httpx.ReadTimeout("slow"), "upstream_timeout"),
        (TimeoutError("slow"), "upstream_timeout"),
        (httpx.ConnectError("refused"), "upstream_down"),
        (ConnectionError("reset"), "upstream_down"),
        (
            httpx.HTTPStatusError(
                "busy",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(429),
            ),
            "upstream_rate_limited",
        ),
        (
            httpx.HTTPStatusError(
                "bad gateway",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(502),
            ),
            "upstream_down",
        ),
    ],
)
def test_generic_provider_message_is_classified_from_its_cause(cause, reason):
    wrapped = ProviderUnavailable("vnstock fundamentals failed: FPT")
    wrapped.__cause__ = cause
    env = _caught(wrapped)
    assert (env["reason"], env["retryable"]) == (reason, True)


async def _recent_failure(tool: str = "negtool") -> dict[str, Any]:
    try:
        await shared.run_blocking(lambda: 1, tool, 5.0)
    except ProviderUnavailable as exc:
        return vn_na(tool, str(exc))
    raise AssertionError("expected a negative cache hit")


async def test_recent_failure_reports_the_remaining_ttl_not_the_constant(monkeypatch):
    monkeypatch.setenv("MCP_NEG_TTL", "90")
    shared._neg["negtool"] = time.monotonic() + 36.5
    env = await _recent_failure()
    assert env["reason"] == "recent_failure"
    assert env["retryable"] is True
    assert 35 <= env["retry_after_s"] <= 37


async def test_remaining_ttl_shrinks_and_follows_the_configured_ttl(monkeypatch):
    monkeypatch.setenv("MCP_NEG_TTL", "20")
    shared._neg_mark("negtool")
    first = (await _recent_failure())["retry_after_s"]
    assert first == 20
    shared._neg["negtool"] -= 5
    assert (await _recent_failure())["retry_after_s"] == 15


async def test_last_fraction_of_the_ttl_rounds_up_to_a_real_wait(monkeypatch):
    monkeypatch.setenv("MCP_NEG_TTL", "90")
    shared._neg["negtool"] = time.monotonic() + 0.4
    assert (await _recent_failure())["retry_after_s"] == 1


def test_recent_failure_text_without_the_exception_omits_the_wait():
    env = vn_na("x", "x briefly unavailable (recent timeout), retry shortly")
    assert env["reason"] == "recent_failure"
    assert "retry_after_s" not in env


async def test_timeout_says_when_the_negative_cache_lets_a_retry_through(monkeypatch):
    monkeypatch.setenv("MCP_NEG_TTL", "40")
    try:
        await shared.run_blocking(lambda: time.sleep(1), "slowtool", 0.05)
    except ProviderUnavailable as exc:
        env = vn_na("slowtool", str(exc))
    assert env["reason"] == "upstream_timeout"
    assert env["retry_after_s"] == 40


async def test_timeout_without_negative_cache_omits_the_wait(monkeypatch):
    monkeypatch.setenv("MCP_NEG_TTL", "0")
    try:
        await shared.run_blocking(lambda: time.sleep(1), "slowtool", 0.05)
    except ProviderUnavailable as exc:
        env = vn_na("slowtool", str(exc))
    assert env["reason"] == "upstream_timeout"
    assert "retry_after_s" not in env


async def test_shed_call_is_busy(monkeypatch):
    monkeypatch.setattr(shared, "shed_limit", lambda: 0)
    try:
        await shared.run_blocking(lambda: 1, "busytool", 5.0)
    except ProviderUnavailable as exc:
        env = vn_na("busytool", str(exc))
    assert (env["reason"], env["retryable"]) == ("busy", True)
    assert "retry_after_s" not in env


def test_open_circuit_reports_its_remaining_recovery_time():
    breaker = circuit.CircuitBreaker("up", failure_threshold=1, recovery_timeout=60.0)

    def fail() -> None:
        raise ProviderUnavailable("up unreachable")

    with pytest.raises(ProviderUnavailable):
        breaker.call(fail)
    try:
        breaker.call(lambda: None)
    except ProviderUnavailable as exc:
        env = vn_na("x", str(exc))
    assert (env["reason"], env["retryable"]) == ("upstream_down", True)
    assert 1 <= env["retry_after_s"] <= 60


async def test_real_tool_returns_the_fields_and_does_not_raise(monkeypatch):
    """The whole path: registered tool, negative cache hit, envelope, no MCP error."""
    monkeypatch.setenv("MCP_NEG_TTL", "90")
    call = functools.partial(vn_p.quote_history, "FPT", 5, "1D")
    shared._neg[shared._neg_key("vn_quote_history", call)] = time.monotonic() + 30
    tool = _server()._tool_manager.get_tool("vn_quote_history")
    env = await tool.run({"symbol": "FPT", "days": 5})
    assert env["availability"] == "unavailable"
    assert env["reason"] == "recent_failure"
    assert 29 <= env["retry_after_s"] <= 30
    assert env["warnings"] == [
        "vn_quote_history briefly unavailable (recent timeout), retry shortly"
    ]
    assert env["data"]["tool"] == "vn_quote_history"
    assert env["provenance"]["source"] == "unavailable"


async def test_real_tool_reports_a_missing_key_as_not_retryable(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    def missing(*_: Any, **__: Any) -> None:
        raise ProviderAuthMissing("VIETSTOCK_COOKIE_HEADER/HAR not configured")

    monkeypatch.setattr(vs_p, "financeinfo", missing)
    tool = _server()._tool_manager.get_tool("vs_financeinfo")
    env = await tool.run({"symbol": "FPT"})
    assert (env["reason"], env["retryable"]) == ("not_configured", False)


def test_alternative_is_offered_only_for_a_classified_failure():
    env = _caught(ProviderUnavailable("ws worker has not published yet"), "dnse_indices")
    assert env["alternatives"] == ["vs_market_index"]
    assert "alternatives" not in _caught(ProviderBadData("bad"), "dnse_indices")
    assert "alternatives" not in _caught(ProviderUnavailable("dnse timeout: /x"), "dnse_tool")


def test_every_alternative_is_a_registered_tool_on_another_upstream():
    names = {t.name for t in _server()._tool_manager.list_tools()}
    for tool, alternatives in ALTERNATIVES.items():
        assert tool in names
        assert alternatives
        for alternative in alternatives:
            assert alternative in names
            assert UPSTREAMS[alternative] != UPSTREAMS[tool], (tool, alternative)


def test_vietstock_tools_never_suggest_each_other():
    vietstock = {tool for tool, upstream in UPSTREAMS.items() if upstream == "vietstock"}
    for tool in vietstock:
        assert not vietstock & set(ALTERNATIVES.get(tool, ()))


@pytest.mark.parametrize(
    ("data", "availability", "warnings"),
    [
        ({"rows": [1]}, None, None),
        ({"rows": [1]}, "available", ["vietstock timeout: /a"]),
        ({"rows": [1]}, "partial", ["vietstock timeout: /a"]),
        ({}, None, None),
        ([], "empty", ["FRED_API_KEY is not set"]),
    ],
)
def test_other_availabilities_keep_the_old_envelope(data, availability, warnings):
    try:
        raise ProviderUnavailable("vietstock timeout: /a", retry_after_s=9)
    except ProviderUnavailable:
        env = make_envelope(data, source="vnstock", warnings=warnings, availability=availability)
    assert set(env) == {"data", "provenance", "warnings", "availability"}


def test_unavailable_keeps_every_existing_field():
    env = vn_na("vn_fundamentals", "vietstock timeout: /a")
    assert env["data"] == {"tool": "vn_fundamentals"}
    assert env["provenance"]["source"] == "unavailable"
    assert env["warnings"] == ["vietstock timeout: /a"]
    assert env["availability"] == "unavailable"
    assert "isError" not in env
