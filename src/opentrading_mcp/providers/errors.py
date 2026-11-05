"""Upstream error taxonomy (maps to ErrorCode strings for envelopes)."""

from __future__ import annotations


class ProviderUnavailable(Exception):
    """Upstream unreachable or timed out (retryable).

    `reason` and `retry_after_s` are for whoever raises this and knows them. They feed
    the envelope (see `failures.py`); the message stays the human-readable warning.
    """

    def __init__(
        self, *args: object, reason: str | None = None, retry_after_s: int | None = None
    ) -> None:
        super().__init__(*args)
        self.reason = reason
        self.retry_after_s = retry_after_s


class ProviderAuthMissing(Exception):
    """Credentials absent (not retryable without config)."""


class ProviderBadData(Exception):
    """Upstream returned malformed data (not retryable as-is)."""
