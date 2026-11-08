"""Expiry of the pinned vnstock release candidate (#80).

vnstock 6 release candidates stop working on a fixed date: the team's measured
API notes (plans/vnstock-gen6-api-notes-2026-11-08.md) record "vnstock 6.0.0rc4
dùng được đến 07/12/2026", and vnstock_quant ships a ``ReleaseExpiredError``.
After that date every vnstock-backed tool fails — candles, indices, futures and
the listing included, even on the ssi/dnse chains. ``vnstock.status()`` would
say so itself, but it requires a registered device, so the date is pinned here.

When uv.lock moves to another vnstock version, add its expiry (or nothing, for
a final release) to ``RELEASE_EXPIRY``; an unknown release candidate is flagged
as such rather than reported healthy.
"""

from __future__ import annotations

from datetime import date
from importlib import metadata
from typing import Any

RELEASE_EXPIRY: dict[str, date] = {"6.0.0rc4": date(2026, 12, 7)}
WARN_DAYS = 30


def installed_version() -> str | None:
    """Installed vnstock version from package metadata (no import of vnstock)."""
    try:
        return metadata.version("vnstock")
    except metadata.PackageNotFoundError:
        return None


def release_status(today: date | None = None, version: str | None = None) -> dict[str, Any]:
    """{version, status, expires, days_left, warning?} — status is one of
    ok / expiring / expired / unknown_expiry / not_installed. Never raises."""
    today = today or date.today()
    version = version if version is not None else installed_version()
    if version is None:
        return {"version": None, "status": "not_installed"}
    expires = RELEASE_EXPIRY.get(version)
    if expires is None:
        if "rc" in version or "a" in version.split(".")[-1] or "b" in version.split(".")[-1]:
            return {
                "version": version,
                "status": "unknown_expiry",
                "warning": f"vnstock {version} is a pre-release with no recorded expiry date",
            }
        return {"version": version, "status": "ok"}
    days_left = (expires - today).days
    out: dict[str, Any] = {
        "version": version,
        "expires": expires.isoformat(),
        "days_left": days_left,
    }
    if days_left < 0:
        out["status"] = "expired"
        out["warning"] = (
            f"vnstock {version} expired on {expires.isoformat()}: every vnstock-backed tool "
            "fails until the server is upgraded"
        )
    elif days_left <= WARN_DAYS:
        out["status"] = "expiring"
        out["warning"] = (
            f"vnstock {version} expires on {expires.isoformat()} ({days_left} days): upgrade "
            "the pin before then or every vnstock-backed tool stops"
        )
    else:
        out["status"] = "ok"
    return out
