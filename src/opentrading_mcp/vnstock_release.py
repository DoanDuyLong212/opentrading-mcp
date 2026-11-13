"""Expiry of the pinned vnstock release candidate (#80).

vnstock 6 release candidates stop working on a fixed date. ``vnstock doctor``
(which reads the date from vnstocks.com) printed on 2026-11-09: "Bản vnstock
6.0.0rc4 — Dùng được đến hết ngày 07/12/2026" (usable through 07/12/2026), and
vnstock_quant ships a ``ReleaseExpiredError``. After that date every
vnstock-backed tool fails — candles, indices, futures and the listing included,
even on the ssi/dnse chains. ``vnstock.status()`` needs a registered device and
``doctor`` is an interactive CLI, so the date is pinned here instead.

Release lifetimes (vendor docs, 2026-11-13): a release candidate runs 30 days from
its build, a final release 365 days (6.0.0: until 2027-11-10). The vendor can also
switch a release off early through its signed client policy: 6.0.0rc5 was refused
from 11/11/2026 (code ``VNSTOCK_RELEASE_*``), four weeks before the date below,
so this table is only a fallback. Upgrade with ``uv lock --upgrade-package vnstock
--upgrade-package vnstock-oapi --upgrade-package vnstock-quant`` and keep the
pyproject floors on final releases.
"""

from __future__ import annotations

from datetime import date
from importlib import metadata
from typing import Any

# rc5 (published 2026-11-09, `vnstock doctor`: "Dùng được đến hết ngày 09/12/2026") lives
# ~30 days like rc4: each release candidate must be replaced about monthly.
RELEASE_EXPIRY: dict[str, date] = {
    "6.0.0rc4": date(2026, 12, 7),
    "6.0.0rc5": date(2026, 12, 9),
}
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
