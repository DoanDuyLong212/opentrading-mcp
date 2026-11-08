"""vnstock provider (gen 6: Market/Reference/Fundamental over Open API, source-explicit).

Gen 6 removed the gen-4 classes (Quote/Listing/Company/Finance/Trading) and the
implicit VCI/KBS/MSN sources: every call carries an explicit ``source`` and the
first non-empty frame wins across the chain below. Mapping notes live in
plans/vnstock-gen6-migration-2026-11-08.md; measured API in the SDD workspace.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from pandas.api.types import is_bool

from opentrading_mcp.providers.circuit import guarded
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable

# Gen-6 source chains (first non-empty frame wins). The owner stopped using the
# fhsc and fmp keys on 2026-11-08, so ssi is primary and dnse the fallback;
# both return the same closes in the same units (equity, index and futures,
# measured live 2026-11-08). vnstock routes only fhsc/fmp/tcbs serve have an
# empty chain and fail as not configured: batch quote, statements/fa, company
# profile, insider trades, forex, commodity and global indices.
SRC_EQUITY = ("ssi", "dnse")
SRC_QUOTE: tuple[str, ...] = ()  # market.equity.quote: fhsc/tcbs only
SRC_TRADES = ("dnse",)  # market.equity.trades: dnse/tcbs only
SRC_LISTING = ("ssi", "dnse")
SRC_INDEX = ("ssi", "dnse")
SRC_DERIV = ("ssi", "dnse")
SRC_FX: tuple[str, ...] = ()  # market.forex / market.commodity: fhsc/fmp only
SRC_GLOBAL: tuple[str, ...] = ()  # market.global_index: fhsc/fmp only
SRC_CRYPTO = ("binance",)
SRC_FUNDAMENTAL: tuple[str, ...] = ()  # fundamental.* and reference.company.*: fhsc only

# Every variable a source needs (vnstock's names). binance is keyless.
SOURCE_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "ssi": ("SSI_API_KEY", "SSI_API_SECRET"),
    "dnse": ("DNSE_API_KEY", "DNSE_API_SECRET"),
    "binance": (),
}
SOURCE_CHAINS: dict[str, tuple[str, ...]] = {
    "equity": SRC_EQUITY,
    "index": SRC_INDEX,
    "listing": SRC_LISTING,
    "futures": SRC_DERIV,
    "trades": SRC_TRADES,
    "crypto": SRC_CRYPTO,
    "quote": SRC_QUOTE,
    "fundamental": SRC_FUNDAMENTAL,
    "forex": SRC_FX,
    "global": SRC_GLOBAL,
}


def _alias_dnse_secret() -> None:
    """The project's own DNSE client (and Render) use ``DNSE_SECRET``; vnstock
    reads ``DNSE_API_SECRET``. Fill the vnstock name when it is unset, so one
    secret serves both. An explicit ``DNSE_API_SECRET`` always wins."""
    secret = os.environ.get("DNSE_SECRET", "").strip()
    if secret and not os.environ.get("DNSE_API_SECRET", "").strip():
        os.environ["DNSE_API_SECRET"] = secret


_alias_dnse_secret()


def _source_ready(source: str) -> bool:
    if source not in SOURCE_CREDENTIALS:
        return False
    return all(str(os.environ.get(var, "")).strip() for var in SOURCE_CREDENTIALS[source])


def _error_kind(exc: BaseException) -> str:
    """'rate' / 'auth' / 'error' for one source's failure (vnstock 6 class names
    and ``code`` strings, matched by name so no vnstock import is needed)."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    code = str(getattr(exc, "code", "") or "")
    if names & {"RateLimitedError", "RateLimitError"} or "RATE_LIMIT" in code:
        return "rate"
    if names & {"CredentialError", "AccessDeniedError"} or "CREDENTIAL" in code:
        return "auth"
    return "error"


def _chain_error(
    label: str, errors: list[tuple[str, BaseException]], empty: list[str]
) -> ProviderUnavailable:
    """One error for a whole source chain: every source's outcome, plus a
    machine-readable ``reason`` (#83) — a rate limit anywhere wins, then
    'every source lacks its keys'."""
    from opentrading_mcp.failures import NOT_CONFIGURED, UPSTREAM_RATE_LIMITED
    from opentrading_mcp.tools.shared import RATE_LIMITED

    if not errors and not empty:
        return ProviderUnavailable(
            f"no source configured for {label} (fhsc/fmp discontinued)", reason=NOT_CONFIGURED
        )
    parts = [f"{src}: {str(exc)[:160]}" for src, exc in errors]
    parts += [f"{src}: empty" for src in empty]
    detail = "; ".join(parts)
    kinds = {_error_kind(exc) for _, exc in errors}
    if "rate" in kinds:
        return ProviderUnavailable(
            f"{RATE_LIMITED}: {label} ({detail})", reason=UPSTREAM_RATE_LIMITED
        )
    if kinds == {"auth"} and not empty:
        return ProviderUnavailable(
            f"no data for {label}: source keys not set ({detail})", reason=NOT_CONFIGURED
        )
    return ProviderUnavailable(f"no data for {label} ({detail})")


def _fetch_frame(fetchers: list[tuple[str, Any]], label: str) -> Any:
    """Try ``(source, callable)`` pairs in order; return the first non-empty frame.

    Keeps every source's outcome: a missing key on one source must not hide a
    rate limit on another (the error and its ``reason`` cover the whole chain).
    """
    errors: list[tuple[str, BaseException]] = []
    empty: list[str] = []
    for source, call in fetchers:
        try:
            candidate = call()
        except Exception as exc:
            errors.append((source, exc))
            continue
        if candidate is None:
            empty.append(source)
            continue
        try:
            if len(candidate) == 0:
                empty.append(source)
                continue
        except TypeError:
            pass  # frame without __len__ — trust it and let the caller parse
        return candidate
    raise _chain_error(label, errors, empty)


def _rewrap(exc: Exception, message: str) -> ProviderUnavailable:
    """Add caller context to a chain error without losing its reason."""
    return ProviderUnavailable(
        f"{message}: {exc}",
        reason=getattr(exc, "reason", None),
        retry_after_s=getattr(exc, "retry_after_s", None),
    )


def _no_source(route: str) -> ProviderUnavailable:
    """A vnstock route whose only sources were fhsc/fmp/tcbs (discontinued)."""
    from opentrading_mcp.failures import NOT_CONFIGURED

    return ProviderUnavailable(
        f"vnstock {route}: no source configured (only fhsc/fmp/tcbs serve it; "
        "fhsc and fmp were discontinued)",
        reason=NOT_CONFIGURED,
    )


def ensure_api_key() -> str:
    """Gen-6: per-source Open API keys decide availability — no runtime
    registration call exists. "keyed" when at least one keyed source of a
    chain (ssi, dnse) has every variable it needs. Never raises.
    """
    return "keyed" if any(_source_ready(s) for s in ("ssi", "dnse")) else "anonymous"


def quota_info() -> dict[str, Any]:
    """Source-key report for source_status (never raises): per source whether
    every variable is set, and per route chain which sources can answer — an
    empty list means that route has no usable source (#87)."""
    try:
        sources = {name: _source_ready(name) for name in SOURCE_CREDENTIALS}
        chains = {
            route: [s for s in chain if sources.get(s)] for route, chain in SOURCE_CHAINS.items()
        }
        keyed = any(sources[s] for s in ("ssi", "dnse"))
        return {
            "tier": "source-keyed" if keyed else "anonymous",
            "sources": sources,
            "chains": chains,
            "discontinued": ["fhsc", "fmp"],
        }
    except Exception as exc:
        return {"tier": "unknown", "note": str(exc)[:100]}


def _ascending_by_time(rows: list[dict[str, Any]], key: str = "time") -> list[dict[str, Any]]:
    """Chronological order for frame rows. Gen-6 profiles flip row order between
    functions; consumers (market_timing rows[-1], corp.py closes[-1], msn_fx_gold
    series[-35:]) all assume ascending, so every raw ohlcv path normalizes here."""
    return sorted(rows, key=lambda r: str(r.get(key, ""))[:24])


def _candle_day(value: Any) -> str:
    """ISO date of a candle. vnstock keeps the date in a ``time`` column under a RangeIndex,
    so the index alone gave "15", "16", ... and models wrote "T-15" instead of dates."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return text


# Index codes served by the index group only (cycle refresh feeds these).
_VN_INDEX_SYMBOLS = frozenset(
    {"VNINDEX", "VN30", "VNFIN", "VNFINLEAD", "VNMAT", "VNREAL", "VNUTI", "VNIT",
     "VNSI", "HNXINDEX", "HNX30"}
)


def _candle_fetchers(symbol: str, **ohlcv_kwargs: Any) -> list[tuple[str, Any]]:
    """Source fetchers for daily candles — index codes ride the index group."""
    from vnstock import Market

    symbol = symbol.upper()
    if symbol in _VN_INDEX_SYMBOLS:
        return [
            (
                source,
                (lambda source=source: Market(source).index(symbol).ohlcv(**ohlcv_kwargs)),
            )
            for source in SRC_INDEX
        ]
    return [
        (
            source,
            (lambda source=source: Market(source).equity(symbol).ohlcv(**ohlcv_kwargs)),
        )
        for source in SRC_EQUITY
    ]


@guarded("vnstock")
def quote_history(symbol: str, days: int = 365, interval: str = "1D") -> list[dict[str, Any]]:
    """Daily/weekly/monthly candles; interval 1D|1W|1M. Gen-6 Market().equity().ohlcv."""
    try:
        from vnstock import Market  # noqa: F401 — presence check before building fetchers
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    symbol = symbol.upper()
    iv = interval.strip().upper()
    if iv not in ("1D", "1W", "1M"):
        raise ProviderBadData(f"unknown interval {interval!r} (1D|1W|1M)")
    span = max(days, 5) + 30
    if iv == "1D":
        # `days` counts candles. A year has ~250 sessions in ~365 calendar days, plus Tet
        # and other holidays, so 1.5x calendar days + 30 always covers the count.
        span = int(max(days, 5) * 1.5) + 30
    elif iv == "1W":
        span = span * 7 + 40
    elif iv == "1M":
        span = span * 31 + 60
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=span)).isoformat()
    frame = _fetch_frame(
        _candle_fetchers(symbol, start=start, end=end, interval=iv),
        f"candles {symbol}",
    )
    try:
        rows: list[dict[str, Any]] = []
        for row in _records(frame):
            close = float(row.get("close", 0))
            if not math.isfinite(close) or close <= 0:
                # A period with no session (the Tet week on 1W) comes back as a NaN row;
                # one NaN poisons every rolling indicator for the next N bars.
                continue
            rows.append(
                {
                    "t": _candle_day(row.get("time")),
                    "o": float(row.get("open", 0)),
                    "h": float(row.get("high", 0)),
                    "l": float(row.get("low", 0)),
                    "c": close,
                    "v": float(row.get("volume", 0)),
                }
            )
        # Gen-6 sources may return newest-first; the rolling indicators and the
        # `rows[-days:]` window below both assume chronological order.
        rows.sort(key=lambda r: r["t"])
        return rows[-max(days, 1) :]
    except Exception as exc:
        raise ProviderBadData(f"malformed vnstock frame for {symbol}") from exc


# Own breaker: cycle refresh fetches ~150 symbols through here, and a batch run
# hitting a rate limit must not open the breaker every interactive tool shares.
@guarded("vnstock-batch")
def candles_range(symbol: str, start: str, end: str, interval: str = "1D") -> list[dict[str, Any]]:
    """Daily candles for an explicit date range, ascending by day (cycle refresh)."""
    try:
        from vnstock import Market  # noqa: F401 — presence check before building fetchers
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    frame = _fetch_frame(
        _candle_fetchers(symbol, start=start, end=end, interval=interval),
        f"candles {symbol}",
    )
    rows: list[dict[str, Any]] = []
    for row in _records(frame):
        t = _candle_day(row.get("time"))
        if len(t) != 10 or t[4] != "-":
            raise ProviderBadData(f"bad candle time {t!r} for {symbol}")
        try:
            close = float(row.get("close", 0) or 0)
            if not math.isfinite(close) or close <= 0:
                # A no-session row (Tet week on 1W) is NaN here too: one NaN row
                # poisons the cycle statistics the same way it poisons indicators.
                continue
            rows.append(
                {
                    "t": t,
                    "o": float(row.get("open", 0) or 0),
                    "h": float(row.get("high", 0) or 0),
                    "l": float(row.get("low", 0) or 0),
                    "c": close,
                    "v": float(row.get("volume", 0) or 0),
                }
            )
        except (TypeError, ValueError) as exc:
            raise ProviderBadData(f"malformed candle for {symbol}: {exc}") from exc
    rows.sort(key=lambda r: r["t"])
    return rows


@guarded("vnstock")
def equity_quote_batch(symbols: list[str]) -> list[dict[str, Any]]:
    """Batch quotes, sub-batched in 10s with per-chunk timeouts (P22: full-VN30
    single batch hangs from some networks — partial results beat a hang)."""
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    syms = [str(s).upper() for s in symbols or []]
    if not syms:
        return []
    if not SRC_QUOTE:
        raise _no_source("batch quote")

    def _one(chunk: list[str]) -> list[dict[str, Any]]:
        try:
            frame = Market(SRC_QUOTE[0]).equity.quote(symbols=chunk)
        except Exception as exc:
            raise ProviderUnavailable(f"vnstock batch quote failed: {exc}") from exc
        try:
            records = frame.to_dict(orient="records")
        except Exception:
            records = []
        return [{str(k): record[k] for k in record} for record in records]

    out: list[dict[str, Any]] = []
    missing: list[str] = []
    chunks = [syms[i : i + 10] for i in range(0, len(syms), 10)]
    # NOTE: P05 fix — a module-level shared pool (max 3 workers) bounds the
    # total number of live vnstock threads process-wide: a hung chunk thread
    # occupies one slot and degrades later batches to `missing` instead of
    # accumulating unbounded zombie threads (OOM → 502). The wait budget is a
    # single 45s TOTAL for the whole batch (matches the historical hang-return
    # contract), not 45s per chunk.
    pool = _shared_batch_pool(len(chunks))
    deadline = time.monotonic() + _VN_BATCH_WAIT_SECONDS
    futs = {}
    try:
        for chunk in chunks:
            # A shared executor alone has an unbounded queue. Admit at most
            # three physical legs, including work retained after caller timeout.
            if not _VN_BATCH_SLOTS.acquire(blocking=False):
                missing.extend(chunk)
                continue
            try:
                fut = pool.submit(_one, chunk)
            except BaseException:
                _VN_BATCH_SLOTS.release()
                raise
            fut.add_done_callback(lambda _f: _VN_BATCH_SLOTS.release())
            futs[fut] = chunk
        for fut, chunk in futs.items():
            remaining = max(0.0, deadline - time.monotonic())
            try:
                out.extend(fut.result(timeout=remaining))
            except Exception:
                missing.extend(chunk)
    finally:
        # Cancel work that never started; running work retains its admission
        # until its Future completes. No expired requests run after recovery.
        for fut in futs:
            fut.cancel()
    if missing and not out:
        raise ProviderUnavailable(f"vnstock batch quote failed for {len(missing)} symbols")
    if missing:
        out.append({"_missing": sorted(set(missing))})
    return out


_VN_BATCH_POOL: ThreadPoolExecutor | None = None
_VN_BATCH_POOL_LOCK = threading.Lock()
_VN_BATCH_SLOTS = threading.BoundedSemaphore(3)
_VN_BATCH_WAIT_SECONDS = 45.0


def _shared_batch_pool(min_workers: int) -> ThreadPoolExecutor:
    """P05: one process-wide bounded pool for vnstock batch legs. Hung legs
    occupy a worker but can never multiply across calls; the hard bound keeps
    live thread count ≤ 3 no matter how many batches time out."""
    global _VN_BATCH_POOL
    with _VN_BATCH_POOL_LOCK:
        if _VN_BATCH_POOL is None:
            _VN_BATCH_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="vnstock-batch")
        return _VN_BATCH_POOL


def split_batch(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Split equity_quote_batch rows into (real quotes, missing symbols)."""
    quotes = [r for r in rows if isinstance(r, dict) and "_missing" not in r]
    missing: list[str] = []
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("_missing"), list):
            missing.extend(str(s) for s in r["_missing"])
    return quotes, sorted(set(missing))


@guarded("vnstock")
def equity_trades(
    symbol: str,
    limit: int = 20,
    board: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Intraday trades. Gen 6 has no ``board`` param (silently dropped);
    ``from_date``/``to_date`` map to v6 ``start``/``end``; ``limit`` defaults to
    100 upstream when omitted."""
    del board  # gen-6 trades has no board filter
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        kwargs: dict[str, Any] = {"limit": max(int(limit), 1)}
        if from_date is not None:
            kwargs["start"] = from_date
        if to_date is not None:
            kwargs["end"] = to_date
        frame = _fetch_frame(
            [
                (
                    source,
                    (lambda source=source: Market(source).equity(symbol.upper()).trades(**kwargs)),
                )
                for source in SRC_TRADES
            ],
            f"trades {symbol}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock trades failed: {symbol}") from exc
    rows = sorted(_records(frame), key=lambda r: str(r.get("time", ""))[:24], reverse=True)
    return rows[: max(limit, 1)]


# The symbol list changes a few times a year; symbol_lookup used to fetch all ~1,600
# rows on every call. Cached per process; the lock makes concurrent cold calls share
# one fetch instead of each running it.
_LISTING_TTL = 6 * 3600.0
_listing: tuple[float, list[dict[str, str]]] | None = None
_listing_lock = threading.Lock()
# After a failed fetch, callers queued on the lock fail fast for a few seconds instead
# of each repeating the fetch in turn.
_listing_failed_until = 0.0


def listing_symbols(limit: int | None = None) -> list[dict[str, str]]:
    global _listing, _listing_failed_until
    with _listing_lock:
        if _listing is None or time.monotonic() - _listing[0] > _LISTING_TTL:
            if time.monotonic() < _listing_failed_until:
                raise ProviderUnavailable("vnstock listing failed (retry shortly)")
            try:
                _listing = (time.monotonic(), _fetch_listing())
            except Exception:
                _listing_failed_until = time.monotonic() + 10.0
                raise
        rows = _listing[1]
    if limit is not None:
        rows = rows[: max(int(limit), 1)]
    return list(rows)


@guarded("vnstock")
def _fetch_listing() -> list[dict[str, str]]:
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    last: Exception | None = None
    for source in SRC_LISTING:
        try:
            frame = Reference(source).equity.list()
            rows = frame.to_dict(orient="records")
            if rows:
                return [
                    {
                        "symbol": str(r.get("symbol", "")),
                        "name": str(r.get("organ_name", r.get("name", ""))),
                    }
                    for r in rows
                ]
        except Exception as exc:
            last = exc
            continue
    raise ProviderUnavailable("vnstock listing failed") from last


def _records(frame: Any) -> list[dict[str, Any]]:
    try:
        rows = frame.to_dict(orient="records")
    except Exception:
        return []
    return [{str(k): v for k, v in r.items()} for r in rows]


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make provider rows JSON-safe: NaN/NaT/None -> None, exotic scalars -> str."""
    import math

    clean: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, val in row.items():
            try:
                if val is None:
                    item[key] = None
                elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    item[key] = None
                elif isinstance(val, (str, int, bool)):
                    item[key] = val
                elif isinstance(val, float):
                    item[key] = val
                else:
                    text = str(val)
                    item[key] = None if text in ("NaT", "nan", "None", "") else text
            except Exception:
                item[key] = None
        clean.append(item)
    return clean


@guarded("vnstock")
def index_ohlcv(
    symbol: str = "VNINDEX", count: int = 100, interval: str = "1D"
) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = _fetch_frame(
            [
                (
                    source,
                    (
                        lambda source=source: (
                            Market(source)
                            .index(symbol.upper())
                            .ohlcv(count_back=count, interval=interval)
                        )
                    ),
                )
                for source in SRC_INDEX
            ],
            f"index bars {symbol}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock index ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no index bars for {symbol}")
    return _ascending_by_time(rows)


@guarded("vnstock")
def equity_ohlcv(symbol: str, count: int = 100, interval: str = "1D") -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = _fetch_frame(
            [
                (
                    source,
                    (
                        lambda source=source: (
                            Market(source)
                            .equity(symbol.upper())
                            .ohlcv(count_back=count, interval=interval)
                        )
                    ),
                )
                for source in SRC_EQUITY
            ],
            f"equity bars {symbol}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock equity ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no equity bars for {symbol}")
    return _ascending_by_time(rows)


@guarded("vnstock")
def futures_ohlcv(
    symbol: str = "VN30F1M", count: int = 100, interval: str = "1D"
) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = _fetch_frame(
            [
                (
                    source,
                    (
                        lambda source=source: (
                            Market(source)
                            .futures(symbol.upper())
                            .ohlcv(count_back=count, interval=interval)
                        )
                    ),
                )
                for source in SRC_DERIV
            ],
            f"futures bars {symbol}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock futures ohlcv failed: {symbol}") from exc
    rows = _records(frame)
    if not rows:
        raise ProviderUnavailable(f"no futures bars for {symbol}")
    return _ascending_by_time(rows)


@guarded("vnstock")
def forex_ohlcv(pair: str = "USDVND", count: int = 30) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = _fetch_frame(
            [
                (
                    source,
                    (
                        lambda source=source: (
                            Market(source)
                            .forex(pair.upper())
                            .ohlcv(count_back=count, interval="1D")
                        )
                    ),
                )
                for source in SRC_FX
            ],
            f"forex bars {pair}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock forex failed: {pair}") from exc
    return _ascending_by_time(_records(frame))


@guarded("vnstock")
def crypto_ohlv(symbol: str = "BTCUSDT", count: int = 30) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        frame = _fetch_frame(
            [
                (
                    source,
                    (
                        lambda source=source: (
                            Market(source)
                            .crypto(symbol.upper())
                            .ohlcv(count_back=count, interval="1D")
                        )
                    ),
                )
                for source in SRC_CRYPTO
            ],
            f"crypto bars {symbol}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock crypto failed: {symbol}") from exc
    return _ascending_by_time(_records(frame))


# Common spellings → the MSN-style codes vnstock's global index accepts
# (vnstock.explorer.msn.const._GLOBAL_INDICES: INX, USA30, COMP...). Keys are already
# normalized: upper case, no spaces, hyphens or dots ("S&P 500" → "S&P500").
GLOBAL_INDEX_ALIASES = {
    "SPX": "INX",
    "GSPC": "INX",
    "^GSPC": "INX",
    "SP500": "INX",
    "S&P500": "INX",
    "S&P": "INX",
    "DJIA": "USA30",
    "DJI": "USA30",
    "^DJI": "USA30",
    "DOW": "USA30",
    "DOWJONES": "USA30",
    "IXIC": "COMP",
    "^IXIC": "COMP",
    "NASDAQ": "COMP",
    "NASDAQCOMPOSITE": "COMP",
    "RUSSELL2000": "RUT",
    "^RUT": "RUT",
    "^NYA": "NYA",
    "CAC": "PX1",
    "CAC40": "PX1",
    "FCHI": "PX1",
    "^FCHI": "PX1",
    "FTSE": "UKX",
    "FTSE100": "UKX",
    "^FTSE": "UKX",
    "GDAXI": "DAX",
    "^GDAXI": "DAX",
    "NIKKEI": "N225",
    "NIKKEI225": "N225",
    "^N225": "N225",
    "HANGSENG": "HSI",
    "^HSI": "HSI",
    "SHCOMP": "000001",
    "SSEC": "000001",
    "SHANGHAI": "000001",
    "SHANGHAICOMPOSITE": "000001",
    "000001SS": "000001",
    "^BSESN": "SENSEX",
    "VNINDEX": "VNI",
}


def _normalize_global_symbol(symbol: str) -> str:
    """Map common spellings (SPX, "S&P 500", Dow Jones...) to vnstock's global codes."""
    raw = re.sub(r"[\s.\-]+", "", str(symbol)).upper()
    return GLOBAL_INDEX_ALIASES.get(raw, raw)


VALID_GLOBAL_SYMBOLS = (
    "INX (S&P 500), USA30/DJI (Dow Jones), COMP (Nasdaq Composite), RUT (Russell 2000), "
    "NYA (NYSE Composite), RUI/RUA (Russell 1000/3000), UKX (FTSE 100), DAX, PX1 (CAC 40), "
    "N225 (Nikkei 225), 000001 (Shanghai SE), HSI (Hang Seng), SENSEX, VNI (VN-Index)"
)


@guarded("vnstock")
def global_index(symbol: str = "USA30", count: int = 30) -> list[dict[str, Any]]:
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    normalized = _normalize_global_symbol(symbol)
    try:
        frame = _fetch_frame(
            [
                (
                    source,
                    (
                        lambda source=source: (
                            Market(source)
                            .global_index(normalized)
                            .ohlcv(count_back=count, interval="1D")
                        )
                    ),
                )
                for source in SRC_GLOBAL
            ],
            f"global index bars {normalized}",
        )
    except ProviderUnavailable as exc:
        raise _rewrap(
            exc,
            f"vnstock global index failed: {symbol} (→ {normalized}). "
            f"Valid symbols: {VALID_GLOBAL_SYMBOLS}. "
            f"For indices not listed here (e.g. Nasdaq-100 NDX) use yf_global_indices",
        ) from exc
    return _ascending_by_time(_records(frame))


# --- vnstock_quant.fa table (gen 6) -------------------------------------------------
# The gen-6 Open API has no ratio(): ratios are computed locally by
# vnstock_quant.fa from the three fhsc statements. fa emits RT_* codes with
# decimal "ratio" units; consumers (screener, valuation tools) still speak the
# v4 item_id table (percent ratios, P/E as a multiple), so translate here.
_RT_TO_V4: dict[str, tuple[str, ...]] = {
    "RT_VALUE_EPS": ("trailing_eps",),
    "RT_VALUE_BVPS": ("book_value_per_share_bvps",),
    "RT_VALUE_PE": ("p_e",),
    "RT_VALUE_PB": ("p_b",),
    "RT_VALUE_PS": ("p_s",),
    "RT_VALUE_EV_EBIT": ("ev_ebit",),
    "RT_VALUE_EV_EBITDA": ("ev_ebitda",),
    "RT_PRT_ROE": ("roe", "roe_trailling"),
    "RT_PRT_ROA": ("roa",),
    "RT_PRT_GROSS_MARGIN": ("gross_profit_margin",),
    "RT_PRT_NET_MARGIN": ("net_profit_margin",),
    "RT_PRT_EBIT_MARGIN": ("ebit_margin",),
}
_V4_RATIO_LABELS = {
    "trailing_eps": "Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)",
    "book_value_per_share_bvps": "Giá trị sổ sách của cổ phiếu (BVPS)",
    "p_e": "Chỉ số giá thị trường trên thu nhập (P/E)",
    "p_b": "Chỉ số giá thị trường trên giá trị sổ sách (P/B)",
    "p_s": "Chỉ số giá thị trường trên doanh thu (P/S)",
    "ev_ebit": "EV/EBIT",
    "ev_ebitda": "EV/EBITDA",
    "roe": "Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân (ROEA)",
    "roe_trailling": "ROE bình quân 4 quý gần nhất",
    "roa": "Tỷ suất lợi nhuận trên tổng tài sản bình quân (ROAA)",
    "gross_profit_margin": "Tỷ suất lợi nhuận gộp biên",
    "net_profit_margin": "Tỷ suất lợi nhuận ròng biên",
    "ebit_margin": "Tỷ suất lợi nhuận EBIT biên",
    "dividend_yield": "Tỷ suất cổ tức",
    "roic": "Tỷ suất sinh lời trên vốn đầu tư (ROIC)",
    "beta": "Hệ số beta",
}
# v4 table ids with no vnstock_quant.fa equivalent (RT_PRT_ROIC, RT_VALUE_BETA
# and RT_VALUE_DIVIDEND_YIELD are not in fa.catalog()); rows stay all-None.
_FA_GAP_IDS = ("dividend_yield", "roic", "beta")
_RATIO_METRIC_BASIS = {
    "trailing_eps": "trailing_four_quarters",
    "roe_trailling": "trailing_four_quarters",
}


@guarded("vnstock")
def cashflow(symbol: str, period: str = "quarter") -> dict[str, Any]:
    """Cash-flow statement via gen-6 Fundamental (wide format) — fallback when
    Vietstock LCTT norms are empty upstream. Best-effort parse, VND billions.

    Returns {symbol, period, periods, rows: [{name, values}]}.
    """
    try:
        from vnstock import Fundamental
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    if not SRC_FUNDAMENTAL:
        raise _no_source("cash flow statement")
    try:
        frame = (
            Fundamental(SRC_FUNDAMENTAL[0])
            .equity(symbol.upper())
            .cash_flow(period=period, format="wide")
        )
    except Exception as exc:
        raise ProviderUnavailable(f"no cashflow for {symbol}: {exc}") from exc
    try:
        import pandas as pd

        if hasattr(frame, "index") and getattr(frame.index, "name", None):
            frame = frame.reset_index()
        rows: list[dict[str, Any]] = []
        periods: list[str] = []
        if isinstance(frame, pd.DataFrame):
            cols = list(frame.columns)
            import re as _re

            def _is_period(c: Any) -> bool:
                s = str(c)
                return bool(_re.search(r"(19|20)\d{2}|Q\s*[1-4]", s))

            label_col = cols[0]
            period_cols = [c for c in cols[1:] if _is_period(c)]
            if not period_cols:  # fallback: all non-label columns
                period_cols = list(cols[1:])
            periods = [str(c) for c in period_cols]
            for _, row in frame.iterrows():
                vals = []
                for c in period_cols:
                    try:
                        v = row[c]
                        # statements are raw VNĐ — normalize to VND billions
                        vals.append(None if pd.isna(v) else round(float(v) / 1e9, 1))
                    except (TypeError, ValueError):
                        vals.append(None)
                rows.append({"name": str(row[label_col]), "values": vals})
        return {
            "symbol": symbol.upper(),
            "period": period,
            "unit": "VNDbn",
            "periods": periods,
            "rows": rows,
            "source": "gen6.fundamental.cash_flow",
        }
    except Exception as exc:
        raise ProviderBadData(f"malformed vnstock cashflow for {symbol}: {exc}") from exc


# --- fa → v4 table translation ------------------------------------------------------


def _load_fa_dataset(symbol: str) -> Any:
    """fa.Dataset for one symbol: 3 statements x (year, quarter) via fhsc.

    ``estimate_shares`` lets valuation ratios (P/E, P/B…) run from charter
    capital when the source does not send shares outstanding.
    """
    from vnstock_quant import fa

    if not SRC_FUNDAMENTAL:
        raise _no_source("financial statements (fa ratios)")
    return fa.Dataset.load([symbol], period="both", source=SRC_FUNDAMENTAL[0], estimate_shares=True)


_FA_TTL = 6 * 3600.0
_fa_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_fa_cache_lock = threading.Lock()


def _fa_cache_get(symbol: str, period: str) -> dict[str, Any] | None:
    with _fa_cache_lock:
        hit = _fa_cache.get((symbol.upper(), period))
        if hit is None:
            return None
        at, table = hit
        if time.monotonic() - at > _FA_TTL:
            del _fa_cache[(symbol.upper(), period)]
            return None
        return table


def _fa_cache_put(symbol: str, period: str, table: dict[str, Any]) -> None:
    with _fa_cache_lock:
        _fa_cache[(symbol.upper(), period)] = (time.monotonic(), table)


def _period_sort_key(label: str) -> tuple[int, int]:
    match = re.match(r"^(\d{4})(?:-Q([1-4]))?$", str(label))
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))


def _fa_to_v4_table(symbol: str, period: str, long_frame: Any) -> dict[str, Any]:
    """Translate ``fa.ratios`` long output into the v4 ``{periods, ratios}`` table.

    fa decimals ("ratio" unit) are scaled x100 to the v4 percent convention;
    NaN/±Infinity cells and MISSING_INPUT/MISSING_MARKET reasons become None
    plus a quality_note. RT_PRT_ROE feeds both the v4 ``roe`` and
    ``roe_trailling`` ids: fa's quarterly ROE is already the trailing four
    quarters (annual rows are the audited year).
    """
    rows_by_id: dict[str, dict[str, Any]] = {}
    periods: set[str] = set()
    for row in _records(long_frame):
        rt_id = str(row.get("id", "")).strip()
        v4_ids = _RT_TO_V4.get(rt_id)
        if not v4_ids:
            continue
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            value = None
        if is_bool(row.get("value")):  # defensive: fa emits numerics, never bools
            value = None
        if value is not None and not math.isfinite(value):
            value = None
        unit = str(row.get("unit", "")).strip().lower()
        if value is not None and unit in ("ratio", "decimal", "fraction"):
            value *= 100.0  # fa decimals → v4 percent table
        period_label = str(row.get("period", "")).strip()
        if not period_label:
            continue
        periods.add(period_label)
        reason = str(row.get("reason") or "").strip() or None
        for v4_id in v4_ids:
            entry = rows_by_id.setdefault(
                v4_id,
                {
                    "item_id": v4_id,
                    "item": _V4_RATIO_LABELS.get(v4_id, v4_id),
                    "rt_id": rt_id,
                    "unit": str(row.get("unit", "")),
                    "values": {},
                },
            )
            entry["values"][period_label] = value
            if value is None and reason:
                entry["quality_note"] = f"{rt_id}: {reason}"
    ordered = sorted(periods, key=_period_sort_key, reverse=True)
    discarded = sorted(p for p in periods if _period_sort_key(p) == (0, 0))
    ordered = [p for p in ordered if p not in set(discarded)]
    ratios: list[dict[str, Any]] = []
    for v4_id, entry in rows_by_id.items():
        entry["values"] = {p: entry["values"].get(p) for p in ordered}
        if v4_id in _RATIO_METRIC_BASIS:
            # fa quarter rows are trailing four quarters; year rows are the
            # audited annual figures — never label the annual number TTM.
            entry["basis"] = (
                _RATIO_METRIC_BASIS[v4_id] if period == "quarter" else "reported_period_ratio"
            )
        ratios.append(entry)
    for v4_id in _FA_GAP_IDS:
        ratios.append(
            {
                "item_id": v4_id,
                "item": _V4_RATIO_LABELS.get(v4_id, v4_id),
                "values": {p: None for p in ordered},
                "quality_note": (
                    "not in vnstock_quant.fa — compute from prices or the annual report"
                ),
            }
        )
    return {
        "symbol": symbol.upper(),
        "period": period,
        "frequency": (
            "annual" if period == "year" else "quarterly" if period == "quarter" else None
        ),
        "period_basis": "computed_from_statements",
        "periods": ordered,
        "ratios": ratios,
        "discarded_period_labels": discarded,
        "source": "vnstock_quant.fa",
    }


@guarded("vnstock")
def equity_ratios(symbol: str, period: str = "year") -> dict[str, Any]:
    """Full ratio table computed by vnstock_quant.fa, v4 table shape.

    {symbol, period, periods (newest first), ratios}: rows {item_id, item,
    values: {period: value}} — margins/returns in percent (roe 14.29 = 14.29%),
    EPS/BVPS in dong, multiples as plain numbers. Cells fa could not compute
    (MISSING_INPUT, MISSING_MARKET without prices) are None with a quality_note.
    Results are cached in-process for 6h: the community tier allows 30 fa
    computes/day, and screener enrichment fans out over many symbols.
    """
    cached = _fa_cache_get(symbol, period)
    if cached is not None:
        return cached
    try:
        from vnstock_quant import fa
    except ImportError as exc:
        raise ProviderUnavailable("vnstock_quant not installed") from exc
    try:
        ds = _load_fa_dataset(symbol)
        long_frame = fa.ratios(ds, period=period, format="long")
    except ProviderUnavailable as exc:
        raise _rewrap(exc, f"vnstock ratios failed: {symbol}") from exc
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock ratios failed: {symbol}: {exc}") from exc
    table = _fa_to_v4_table(symbol, period, long_frame)
    _fa_cache_put(symbol, period, table)
    return table


@guarded("vnstock")
def equity_fundamentals(symbol: str, period: str = "year") -> dict[str, Any]:
    """Per-symbol PE/ROE/EPS/BVPS from the fa table (v4 semantics: ROE fraction).

    Missing metrics come back as None. ``period_label`` names the report period
    the numbers belong to ('2025' = year-end 2025), so a year-end PE is never
    mistaken for today's multiple.
    """
    table = equity_ratios(symbol, period)
    by_id = {r["item_id"]: r for r in table["ratios"]}

    def _newest(item_id: str) -> float | None:
        row = by_id.get(item_id)
        if not row:
            return None
        for p in table["periods"]:
            if row["values"].get(p) is not None:
                return row["values"][p]
        return None

    roe_pct = _newest("roe")
    return {
        "symbol": symbol.upper(),
        "pe": _newest("p_e"),
        "roe": roe_pct / 100.0 if roe_pct is not None else None,
        "market_cap": None,
        "market_cap_status": "missing_from_ratio_table",
        "eps": _newest("trailing_eps"),
        "bvps": _newest("book_value_per_share_bvps"),
        "period_label": table["periods"][0] if table["periods"] else None,
        "frequency": table["frequency"],
        "eps_basis": "trailing_four_quarters",
        "discarded_period_labels": [],
        "source": "vnstock_quant.fa",
    }


_EXCHANGE_KEYS = ("exchange", "san", "floor", "exchangecode", "exchange_code")


@guarded("vnstock")
def reference_equity(
    exchange: str = "HOSE", by: str = "exchange", key: str | None = None
) -> list[dict[str, Any]]:
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    try:
        if by == "group":
            frame = Reference("ssi").equity.list_by_group(key or exchange)
            return _records(frame)
        if by == "industry":
            frame = Reference("ssi").equity.list_by_industry(key or exchange)
            return _records(frame)
        frame = None
        for source in SRC_LISTING:
            try:
                candidate = Reference(source).equity.list_by_exchange()
                if candidate is not None and len(candidate) > 0:
                    frame = candidate
                    break
            except Exception:
                continue
        if frame is None:
            frame = Reference(SRC_LISTING[0]).equity.list()
    except Exception as exc:
        raise ProviderUnavailable("vnstock reference failed") from exc
    rows = _records(frame)
    query = exchange.upper()
    if query not in ("ALL", ""):
        lowered_keys = {k.lower(): k for r in rows for k in r}
        hit_key = next((lowered_keys[k] for k in _EXCHANGE_KEYS if k in lowered_keys), None)
        if hit_key is None:
            # Fail-closed: never return unfiltered rows on schema drift.
            # The vn_reference tool maps ProviderBadData → unavailable envelope
            # with a warning, instead of silently returning the whole market.
            raise ProviderBadData(
                "reference frame has no exchange key; refusing unfiltered fallback"
            )
        rows = [r for r in rows if str(r.get(hit_key, "")).strip().upper() == query]
    return [{**r, "exchange": str(r.get("exchange") or exchange.upper()).upper()} for r in rows]


@guarded("vnstock")
def company_info(symbol: str, detail: bool = False) -> dict[str, Any]:
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    if not SRC_FUNDAMENTAL:
        raise _no_source("company profile")
    try:
        client = Reference(SRC_FUNDAMENTAL[0]).company(symbol.upper())
        info = client.info()
    except Exception as exc:
        raise ProviderUnavailable(f"vnstock company failed: {symbol}") from exc
    try:
        rows = info.to_dict(orient="records")
        data: dict[str, Any] = {"symbol": symbol.upper(), "info": rows[0] if rows else {}}
    except Exception:
        return {"symbol": symbol.upper(), "info": str(info)[:2000]}
    if not detail:
        return data
    for key, method in (("shareholders", "shareholders"), ("officers", "officers")):
        try:
            data[key] = _records(getattr(client, method)())
        except Exception:
            continue
    return data


@guarded("vnstock")
def insider_trading(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    if not SRC_FUNDAMENTAL:
        raise _no_source("insider trading")
    frame = None
    for source in SRC_FUNDAMENTAL:
        try:
            candidate = Reference(source).company(symbol.upper()).insider_trading()
            if candidate is not None:
                frame = candidate
                break
        except Exception:
            continue
    if frame is None:
        raise ProviderUnavailable(f"vnstock insider failed: {symbol}")
    rows = _records(frame)
    return rows[: max(limit, 1)]


@guarded("vnstock")
def corp_events(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    """Corporate actions (cash dividends, share issues) via vnstock Reference.company.

    Returns JSON-safe records, newest first as upstream orders them.
    """
    try:
        from vnstock import Reference
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    if not SRC_FUNDAMENTAL:
        raise _no_source("corporate events")
    frame = None
    for source in SRC_FUNDAMENTAL:
        try:
            candidate = Reference(source).company(symbol.upper()).events()
            if candidate is not None and len(candidate) > 0:
                frame = candidate
                break
        except Exception:
            continue
    if frame is None or len(frame) == 0:
        raise ProviderUnavailable(f"vnstock events failed: {symbol}")
    return _clean(_records(frame))[: max(limit, 1)]


def msn_fx_gold(symbols: list[str] | None = None, days: int = 35) -> list[dict[str, Any]]:
    """USDVND and international gold (GC futures) via gen-6 Market forex/commodity.

    Name is historical (the MSN explorer is gone in gen 6). XAUUSD maps to the
    GC commodity contract — the v6 Open API has no spot XAUUSD route.
    """
    try:
        from vnstock import Market
    except ImportError as exc:
        raise ProviderUnavailable("vnstock not installed") from exc
    from datetime import date, timedelta

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=max(days, 5))).isoformat()
    out: list[dict[str, Any]] = []
    legs: list[tuple[str, str, str, tuple[str, ...]]] = [
        # (returned symbol, v6 group, upstream symbol, source chain)
        ("USDVND", "forex", "USDVND", SRC_FX),
        ("XAUUSD", "commodity", "GC", SRC_FX),  # GC = gold futures contract
    ]
    for symbol, group, upstream, sources in legs:
        if symbols and symbol not in symbols:
            continue
        try:
            frame = _fetch_frame(
                [
                    (
                        source,
                        (
                            lambda source=source, group=group, upstream=upstream: getattr(
                                Market(source), group
                            )(upstream).ohlcv(start=start, end=end, interval="1D")
                        ),
                    )
                    for source in sources
                ],
                f"{group} bars {upstream}",
            )
        except ProviderUnavailable as exc:
            raise _rewrap(exc, f"vnstock {group} failed: {symbol}") from exc
        rows = _ascending_by_time(_clean(_records(frame)))
        out.append(
            {
                "symbol": symbol,
                "points": len(rows),
                "last": rows[-1] if rows else None,
                "series": rows[-35:] if rows else [],
            }
        )
    return out


VN30 = [
    "ACB",
    "BCM",
    "BID",
    "BVH",
    "CTG",
    "FPT",
    "GAS",
    "GVR",
    "HDB",
    "HPG",
    "LPB",
    "MBB",
    "MSN",
    "MWG",
    "NAB",
    "NVL",
    "PJB",
    "PLX",
    "PNJ",
    "SAB",
    "SSI",
    "STB",
    "TCB",
    "TPB",
    "VCB",
    "VHM",
    "VIC",
    "VJC",
    "VNM",
    "VPB",
]
