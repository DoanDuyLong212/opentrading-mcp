"""Expiry of the pinned vnstock release candidate (#80).

vnstock 6 release candidates stop working on a fixed date. ``vnstock doctor``
(which reads the date from vnstocks.com) printed on 2026-11-09: "Bản vnstock
6.0.0rc4 — Dùng được đến hết ngày 07/12/2026" (usable through 07/12/2026), and
vnstock_quant ships a ``ReleaseExpiredError``. After that date every
vnstock-backed tool fails — candles, indices, futures and the listing included,
even on the ssi/dnse chains.

``release_report`` asks the installed library first: ``vnstock.status()["release"]``
carries the vendor's signed verdict (``allowed``, ``expires_at``) and works in guest
mode, no login and no device (checked on 6.0.0, 2026-11-13). The table below is the
fallback when that call fails.

Release lifetimes (vendor docs, 2026-11-13): a release candidate runs 30 days from
its build, a final release 365 days (6.0.0: until 2027-11-10). The vendor can also
switch a release off early through its signed client policy: 6.0.0rc5 was refused
from 11/11/2026 (code ``VNSTOCK_RELEASE_*``), four weeks before the date below,
so this table is only a fallback. Upgrade with ``uv lock --upgrade-package vnstock
--upgrade-package vnstock-oapi --upgrade-package vnstock-quant`` and keep the
pyproject floors on final releases.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
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


# The live verdict changes rarely; vnstock caches its policy too. A failed read is
# retried sooner so a passing network error does not hide the verdict for long.
_LIVE_TTL_S = 600.0
_LIVE_FAIL_TTL_S = 60.0
_live_lock = threading.Lock()
_live_cache: tuple[float, dict[str, Any] | None] | None = None


def _read_live_release() -> dict[str, Any] | None:
    """``vnstock.status()["release"]``, or None when it cannot be read. Imports vnstock
    (seconds of CPU on first use) and may refresh the policy over the network, so call
    it off the event loop."""
    try:
        import vnstock

        status = vnstock.status()
        release = dict(status).get("release") if status is not None else None
        return dict(release) if release else None
    except Exception:
        return None


def live_release() -> dict[str, Any] | None:
    """The cached live verdict (see ``_read_live_release``). Never raises."""
    global _live_cache
    now = time.monotonic()
    with _live_lock:
        if _live_cache is not None and _live_cache[0] > now:
            return _live_cache[1]
    release = _read_live_release()
    ttl = _LIVE_TTL_S if release is not None else _LIVE_FAIL_TTL_S
    with _live_lock:
        _live_cache = (time.monotonic() + ttl, release)
    return release


def _expiry_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def release_report(
    today: date | None = None, live: dict[str, Any] | bool | None = True
) -> dict[str, Any]:
    """``release_status`` plus the vendor's live verdict when it can be read.

    ``source`` is ``live`` or ``table``. A release the vendor no longer allows is
    ``disabled`` whatever its date says: 6.0.0rc5 was switched off on 11/11/2026 while
    the table still gave it until 09/12. Pass ``live`` (a release dict, or None for
    "could not read") to skip the lookup in tests. Never raises.
    """
    today = today or date.today()
    release = live_release() if live is True else (live or None)
    if not release:
        return {**release_status(today=today), "source": "table"}
    version = str(release.get("version") or installed_version() or "")
    out: dict[str, Any] = {"version": version, "source": "live"}
    expires = _expiry_date(release.get("expires_at"))
    if expires is not None:
        out["expires"] = expires.isoformat()
        out["days_left"] = (expires - today).days
    if release.get("build_date"):
        out["build_date"] = str(release["build_date"])
    if release.get("allowed") is False:
        out["status"] = "disabled"
        out["warning"] = (
            f"vnstock {version} is switched off by the vendor: every vnstock-backed tool "
            "fails until the server is upgraded"
        )
        return out
    days_left = out.get("days_left")
    if isinstance(days_left, int) and days_left < 0:
        out["status"] = "expired"
        out["warning"] = (
            f"vnstock {version} expired on {out['expires']}: every vnstock-backed tool "
            "fails until the server is upgraded"
        )
    elif isinstance(days_left, int) and days_left <= WARN_DAYS:
        out["status"] = "expiring"
        out["warning"] = (
            f"vnstock {version} expires on {out['expires']} ({days_left} days): upgrade "
            "the pin before then or every vnstock-backed tool stops"
        )
    else:
        out["status"] = "ok"
    return out
