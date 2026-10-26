"""TTL + key names shared by web + worker (single source of truth)."""

from __future__ import annotations

TTL_SECONDS: dict[str, int] = {
    "snapshot": 5,
    "market": 60,
    "world": 300,
    "overview": 900,
    "financeinfo": 21600,
    "documents": 86400,
    "categories": 604800,
    "odds": 2700,
    # Named buckets added for the read-through expansion (Phase 2). Values are
    # ceilings; price data additionally switches short/long by VN session hour.
    "mins10": 600,  # news, odds, fast-changing sentiment
    "hour": 3600,  # retail gold/FX, corporate calendars, event feeds, slow computes
    "market_offhours": 7200,  # prices when HOSE cannot move (night/weekend)
}


def cache_key(tool: str, fingerprint: str, preset: str = "all", *, version: str = "s05") -> str:
    """Key mcp:{version}:{tool}:{sha256}. S05 fix: the fingerprint is always a
    full SHA-256 of the complete raw string — no lossy substitution, no
    truncation, so `a/b` and `a?b` (or any long common prefixes) can never
    collide. `version` invalidates all cached payloads when the cache contract
    changes; bump it on any semantic change of cached content."""
    import hashlib as _hashlib

    digest = _hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return f"mcp:{version}:{tool}:{digest}"


def legacy_cache_key(preset: str, tool: str, fingerprint: str) -> str:
    return cache_key(tool, fingerprint, preset)
