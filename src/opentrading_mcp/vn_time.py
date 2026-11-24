"""Vietnam wall-clock helpers (#136): one answer to "what day is it in VN?".

Market dates, freshness and trade dates are VN dates, not the container clock.
VN has no DST, so a fixed +07:00 offset is exact and needs no tzdata — the
Render slim image ships none. UTC stays in request signatures and international
timestamps (`fetched_at`, HTTP dates); only calendar labels come from here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
VN_TZ_NAME = "Asia/Ho_Chi_Minh"


def as_vn(moment: datetime | None = None) -> datetime:
    """``moment`` in VN time; a naive value is taken as VN wall time."""
    current = moment or datetime.now(VN_TZ)
    if current.tzinfo is None:
        return current.replace(tzinfo=VN_TZ)
    return current.astimezone(VN_TZ)


def vn_now(moment: datetime | None = None) -> datetime:
    """Now, or ``moment``, as a VN-aware datetime."""
    return as_vn(moment)


def vn_today(moment: datetime | None = None) -> date:
    """The VN calendar date at ``moment`` (default: now).

    A UTC host at 16:59Z on 16/11 is still 16/11 in VN; at 17:00Z it is 17/11.
    """
    return as_vn(moment).date()


def vn_today_iso(moment: datetime | None = None) -> str:
    """``vn_today`` as ``YYYY-MM-DD`` — the label every market payload carries."""
    return vn_today(moment).isoformat()
