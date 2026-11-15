"""Machine-readable failure fields for `availability: "unavailable"` envelopes.

Tools report failures as free text in `warnings`, so clients cannot tell a passing
outage from a missing key. `make_envelope` calls `failure_fields` for every
unavailable envelope, which keeps this the only place that classifies a failure.

Most tools build the envelope inside the `except` block that caught the provider
error, so `sys.exception()` still has the typed exception there (with its
`retry_after_s` and `__cause__`). Envelopes built elsewhere, such as the joined legs
of `market_overview`, only have the text. `isError` stays false either way.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from opentrading_mcp.providers.errors import ProviderAuthMissing

UPSTREAM_TIMEOUT = "upstream_timeout"
UPSTREAM_DOWN = "upstream_down"
UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
NOT_CONFIGURED = "not_configured"
AUTH_MISSING = "auth_missing"
RECENT_FAILURE = "recent_failure"
BUSY = "busy"
# The data library's vendor refused this release (or source) through its signed client
# policy, e.g. vnstock 6.0.0rc5 from 11/11/2026: only a server upgrade fixes it.
VENDOR_DISABLED = "vendor_disabled"
UNKNOWN = "unknown"

# Codes of vnstock's signed client policy (``vnstock._policy.check``): the vendor
# switched this release, or one source, off. Raised before any request; no retry or
# other source of the same release can fix it, only upgrading the package.
VENDOR_DISABLED_CODES = frozenset(
    {"VNSTOCK_RELEASE_EXPIRED", "VNSTOCK_RELEASE_DISABLED", "VNSTOCK_SOURCE_DISABLED"}
)

# A retry cannot fix these until someone changes the server's configuration.
_NOT_RETRYABLE = frozenset({NOT_CONFIGURED, AUTH_MISSING, VENDOR_DISABLED})

_NOT_CONFIGURED_TEXT = re.compile(r"\bnot (?:set|configured)\b")

# First match wins. The order matters: "briefly unavailable (recent timeout)" is not a
# timeout of this call, and "package limited" is a plan limit, not a rate limit. Matching
# is case sensitive so an upper-case ticker inside a message cannot look like a keyword.
_TEXT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\bVNSTOCK_(?:RELEASE_(?:EXPIRED|DISABLED)|SOURCE_DISABLED)\b"
            r"|Bản vnstock \S+ đã bị tắt"
        ),
        VENDOR_DISABLED,
    ),
    (re.compile(r"briefly unavailable"), RECENT_FAILURE),
    (re.compile(r"\bserver busy\b"), BUSY),
    (_NOT_CONFIGURED_TEXT, NOT_CONFIGURED),
    (re.compile(r"\brejected\b|package limited|no permitted periods"), AUTH_MISSING),
    (re.compile(r"\brate limit|\bthrottled\b|\bHTTP 429\b"), UPSTREAM_RATE_LIMITED),
    (re.compile(r"\btimed out\b|\btimeout\b"), UPSTREAM_TIMEOUT),
    (
        re.compile(
            r"\bunreachable\b|retry exhausted|cannot resolve|\bHTTP 5\d\d\b"
            r"|\bcircuit .* is open\b|has not published yet"
        ),
        UPSTREAM_DOWN,
    ),
)

# Class names, so httpx, requests and the builtins all match without importing them.
_TIMEOUT_TYPES = frozenset({"TimeoutError", "TimeoutException", "Timeout"})
_DOWN_TYPES = frozenset({"ConnectionError", "ConnectError", "TransportError"})

# Which upstream serves each tool named in ALTERNATIVES, read from its provider call.
UPSTREAMS: dict[str, str] = {
    "dnse_indices": "dnse-ws",
    "vn_company": "vnstock",
    "vs_company_info": "vietstock",
    "vn_fundamentals": "vnstock",
    "vn_retail_fx": "vietcombank",
    "vs_currency": "vietstock",
    "vs_market_index": "vietstock",
    "vs_trading_info": "vietstock",
}

# Only tools that answer the same question from a different upstream. Tools sharing an
# upstream fail together, so they must never suggest each other. Leave a tool out when
# that is not certain: a wrong suggestion costs the caller a wasted call.
ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "dnse_indices": ("vs_market_index",),  # index levels
    # Q2 (owner decision 2026-11-09): no detailed profile source since fhsc was dropped;
    # vs_company_info has name/exchange/type. One way: vn_company is not configured.
    "vn_company": ("vs_company_info",),
    "vn_fundamentals": ("vs_trading_info",),  # PE, PB, EPS
    # vs_currency rows carry no currency names (checked 2026-11-09), so it is not a
    # usable stand-in for vn_retail_fx; the reverse holds (same Vietcombank figures,
    # labelled, separate upstream).
    "vs_currency": ("vn_retail_fx",),
    "vs_trading_info": ("vn_fundamentals",),
}


def _handled_exception(warnings: list[str]) -> BaseException | None:
    """The exception being handled, if the warnings actually report it."""
    exc = sys.exception()
    text = str(exc) if exc is not None else ""
    if text and any(text in warning for warning in warnings):
        return exc
    return None


def _reason_from_text(warnings: list[str]) -> str | None:
    for pattern, reason in _TEXT_RULES:
        if any(pattern.search(warning) for warning in warnings):
            return reason
    return None


def _reason_from_causes(exc: BaseException) -> str | None:
    """Most providers wrap the transport error in a generic '<x> failed' message."""
    seen: BaseException | None = exc
    for _ in range(5):
        if seen is None:
            return None
        if str(getattr(seen, "code", "") or "") in VENDOR_DISABLED_CODES:
            return VENDOR_DISABLED
        status = getattr(getattr(seen, "response", None), "status_code", None)
        if status == 429:
            return UPSTREAM_RATE_LIMITED
        if isinstance(status, int) and status >= 500:
            return UPSTREAM_DOWN
        names = {cls.__name__ for cls in type(seen).__mro__}
        if names & _TIMEOUT_TYPES:
            return UPSTREAM_TIMEOUT
        if names & _DOWN_TYPES:
            return UPSTREAM_DOWN
        seen = seen.__cause__
    return None


def _classify(exc: BaseException | None, warnings: list[str]) -> str:
    reason = getattr(exc, "reason", None)
    if reason is not None:
        return str(reason)
    if isinstance(exc, ProviderAuthMissing):
        return NOT_CONFIGURED if _NOT_CONFIGURED_TEXT.search(str(exc)) else AUTH_MISSING
    reason = _reason_from_text(warnings)
    if reason is None and exc is not None:
        reason = _reason_from_causes(exc)
    return reason or UNKNOWN


def failure_fields(data: Any, warnings: list[str]) -> dict[str, Any]:
    """`reason`, plus `retryable`, `retry_after_s` and `alternatives` when known.

    An unclassified failure may be a bad argument, so it gets neither `retryable` nor
    `alternatives`: another tool or another try would not fix it.
    """
    exc = _handled_exception(warnings)
    reason = _classify(exc, warnings)
    fields: dict[str, Any] = {"reason": reason}
    if reason == UNKNOWN:
        return fields
    fields["retryable"] = reason not in _NOT_RETRYABLE
    retry_after_s = getattr(exc, "retry_after_s", None)
    if retry_after_s is not None:
        fields["retry_after_s"] = retry_after_s
    tool = data.get("tool") if isinstance(data, dict) else None
    alternatives = ALTERNATIVES.get(tool) if isinstance(tool, str) else None
    if alternatives:
        fields["alternatives"] = list(alternatives)
    return fields
