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
}


def cache_key(tool: str, fingerprint: str, preset: str = "all") -> str:
    """Key mcp:{tool}:{fp}. Param preset giữ để tương thích call-site cũ (bỏ qua)."""
    safe = "".join(c if c.isalnum() or c in "_-:" else "_" for c in fingerprint)[:128]
    return f"mcp:{tool}:{safe}"


def legacy_cache_key(preset: str, tool: str, fingerprint: str) -> str:
    return cache_key(tool, fingerprint, preset)
