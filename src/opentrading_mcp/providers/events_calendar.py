"""Corporate actions from the ssi market-wide events calendar (owner decision Q1,
2026-11-09).

fhsc served per-symbol corporate events; the owner dropped fhsc. The only gen-6
source with amounts and ratios is ``Reference("ssi").events.calendar``, which
downloads the WHOLE market for the requested window whatever ``symbol`` says:
measured 2026-11-09, one calendar year = 3,128 events in 215 s. So:

- one fetch per calendar year (this year and last year), kept in the shared store
  (Redis when configured, else process memory): this year refreshes every 24 h,
  last year every 7 days, so a Render instance waking from sleep reads the store
  instead of downloading again;
- only dividend and share-issue events are kept (cash_dividend, stock_dividend,
  bonus_share, rights_issue, other); meetings and polls are dropped (~2/3 of rows);
- a daemon thread warms the years in the background (``start_warm``, 120 s after
  boot); until a year is loaded a call says so, with ``retry_after_s``, and is a
  ``ProviderNoData`` so the shared vnstock circuit breaker does not count it.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date
from typing import Any

from opentrading_mcp.providers.errors import ProviderNoData, ProviderUnavailable

log = logging.getLogger(__name__)

SOURCE = "ssi.events.calendar"
KEEP_TYPES = frozenset({"cash_dividend", "stock_dividend", "bonus_share", "rights_issue", "other"})
_CODES = {"cash_dividend": "DIV", "stock_dividend": "ISS", "bonus_share": "ISS",
          "rights_issue": "ISS"}
CURRENT_TTL_S = 24 * 3600
PAST_TTL_S = 7 * 24 * 3600
RETRY_AFTER_S = 240
_STORE_KEY = "vn:events_calendar:v1:{year}"

# After a failed fetch (ssi answered 429 during a concurrent burst on 2026-11-09)
# a year is not fetched again for this long, so callers cannot hammer ssi, which
# is also the primary candle source of every other tool.
RETRY_BACKOFF_S = 600.0

_years: dict[int, tuple[float, list[dict[str, Any]]]] = {}
_failed_at: dict[int, float] = {}
_lock = threading.Lock()
_loading = threading.Event()


def _years_wanted(today: date | None = None) -> list[int]:
    year = (today or date.today()).year
    return [year, year - 1]


def _ttl(year: int, today: date | None = None) -> int:
    return CURRENT_TTL_S if year >= (today or date.today()).year else PAST_TTL_S


def _day(value: Any) -> str | None:
    text = str(value or "")
    return text[:10] if len(text) >= 10 and text[:4].isdigit() else None


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def compact(record: dict[str, Any]) -> dict[str, Any] | None:
    """One ssi calendar row → the legacy corp_events row (fhsc key names the
    dividends_splits tool reads), or None for a meeting/poll."""
    kind = str(record.get("event_type") or "")
    if kind not in KEEP_TYPES:
        return None
    return {
        "symbol": str(record.get("symbol") or "").upper(),
        "event_type": kind,
        "event_code": _CODES.get(kind, "OTHER"),
        "event_title_vi": record.get("event_title"),
        "exright_date": _day(record.get("ex_right_date")),
        "record_date": _day(record.get("record_date")),
        # ssi leaves payout_date empty and puts the payment day in issue_date
        "payout_date": _day(record.get("payout_date")) or _day(record.get("issue_date")),
        "value_per_share": _num(record.get("value")),  # dong per share (cash)
        "exercise_ratio": _num(record.get("ratio")),  # 0.1 = 10 new per 100 held
        "dividend_percent": _num(record.get("dividend_percent")),  # % of par 10,000
        "exercise_price": _num(record.get("exercise_price")),
    }


def _fetch_year(year: int) -> list[dict[str, Any]]:
    from opentrading_mcp.providers import vnstock as vn_p

    if not vn_p._source_ready("ssi"):
        raise ProviderUnavailable(
            "corporate events: ssi keys not set (SSI_API_KEY/SSI_API_SECRET)",
            reason="not_configured",
        )
    from vnstock import Reference

    frame = Reference("ssi").events.calendar(start=f"{year}-01-01", end=f"{year}-12-31")
    records = frame.to_dict(orient="records") if frame is not None else []
    return [row for row in (compact(r) for r in records) if row is not None]


def _from_store(year: int) -> list[dict[str, Any]] | None:
    from opentrading_mcp.providers.store import cache_get

    try:
        raw = cache_get(_STORE_KEY.format(year=year))
    except Exception:
        return None
    if not raw:
        return None
    try:
        rows = json.loads(raw)
    except ValueError:
        return None
    return rows if isinstance(rows, list) else None


def _rows_for(year: int, now: float | None = None) -> tuple[list[dict[str, Any]] | None, bool]:
    """(rows, stale) for ``year`` from process memory, else the shared store."""
    now = time.time() if now is None else now
    with _lock:
        hit = _years.get(year)
    if hit is not None:
        return hit[1], now - hit[0] > _ttl(year)
    rows = _from_store(year)
    if rows is not None:
        with _lock:
            # the store entry expires on its own TTL; treat it as fresh until then
            _years[year] = (now, rows)
        return rows, False
    return None, True


def warm(years: list[int] | None = None) -> None:
    """Fetch every wanted year that is missing or stale (blocking; one at a time)."""
    from opentrading_mcp.providers.store import cache_set

    for year in years or _years_wanted():
        rows, stale = _rows_for(year)
        if rows is not None and not stale:
            continue
        with _lock:
            failed = _failed_at.get(year)
        if failed is not None and time.monotonic() - failed < RETRY_BACKOFF_S:
            continue
        started = time.monotonic()
        try:
            fresh = _fetch_year(year)
        except Exception as exc:
            with _lock:
                _failed_at[year] = time.monotonic()
            log.warning("events calendar %s: fetch failed: %s", year, str(exc)[:200])
            continue
        with _lock:
            _failed_at.pop(year, None)
        with _lock:
            _years[year] = (time.time(), fresh)
        try:
            cache_set(_STORE_KEY.format(year=year), fresh, _ttl(year))
        except Exception as exc:
            log.warning("events calendar %s: store write failed: %s", year, exc)
        log.warning(
            "events calendar %s: %d rows in %.0fs", year, len(fresh), time.monotonic() - started
        )


def _warm_in_background(delay_s: float = 0.0) -> bool:
    """Start one warm thread unless one is running. True when this call started it."""
    if _loading.is_set():
        return False
    _loading.set()

    def run() -> None:
        try:
            if delay_s > 0:
                time.sleep(delay_s)
            warm()
        finally:
            _loading.clear()

    threading.Thread(target=run, name="events-calendar-warm", daemon=True).start()
    return True


def start_warm(delay_s: float = 120.0) -> None:
    """Boot hook (cli serve): warm the calendar after the server is up. MCP_WARMUP=0
    turns it off, like the vnstock warm-up."""
    import os

    if os.environ.get("MCP_WARMUP", "1") == "0":
        return
    _warm_in_background(delay_s)


def events_for(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    """Dividend/share-issue events of ``symbol`` from this year and last year,
    newest ex-right date first."""
    from opentrading_mcp.providers import vnstock as vn_p

    if not vn_p._source_ready("ssi"):
        # without ssi keys the calendar can never load: say so, do not "load" forever
        raise ProviderUnavailable(
            "corporate events: ssi keys not set (SSI_API_KEY/SSI_API_SECRET)",
            reason="not_configured",
        )
    sym = symbol.strip().upper()
    loaded: list[dict[str, Any]] = []
    missing: list[int] = []
    any_stale = False
    for year in _years_wanted():
        rows, stale = _rows_for(year)
        any_stale = any_stale or stale
        if rows is None:
            missing.append(year)
        else:
            loaded.extend(r for r in rows if r.get("symbol") == sym)
    if missing or any_stale:
        _warm_in_background()
    if missing and len(missing) == len(_years_wanted()):
        raise ProviderNoData(
            "corporate events calendar is still loading (ssi serves the whole market, "
            f"about 4 minutes per year; years {missing}): retry in a few minutes",
            retry_after_s=RETRY_AFTER_S,
        )
    loaded.sort(key=lambda r: r.get("exright_date") or "", reverse=True)
    return loaded[: max(int(limit), 1)]


def coverage() -> dict[str, Any]:
    """Which years are loaded (for the tool envelope / source_status)."""
    out: dict[str, Any] = {"source": SOURCE, "years": {}}
    for year in _years_wanted():
        rows, stale = _rows_for(year)
        out["years"][str(year)] = (
            "loading" if rows is None else ("stale" if stale else f"{len(rows)} events")
        )
    out["loading"] = _loading.is_set()
    return out
