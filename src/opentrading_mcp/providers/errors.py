"""Upstream error taxonomy (maps to ErrorCode strings for envelopes)."""

from __future__ import annotations


class ProviderUnavailable(Exception):
    """Upstream unreachable or timed out (retryable)."""


class ProviderAuthMissing(Exception):
    """Credentials absent (not retryable without config)."""


class ProviderBadData(Exception):
    """Upstream returned malformed data (not retryable as-is)."""
