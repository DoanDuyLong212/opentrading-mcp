"""vnstock gen-6 adapter contracts (plan vnstock-gen6-migration-2026-11-08, Task 3).

Stubs fake the gen-6 surface (Market/Reference with per-call source). The
provider must call source-explicit v6 shapes — `Market(<src>).equity(...).ohlcv`
— never gen-4 classes (Quote/Listing/Company/Finance), and candles must come
back sorted ascending by day regardless of upstream row order.
"""

from __future__ import annotations

import sys
import types
from typing import ClassVar

import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.units import INDEX_SYMBOLS


class _Frame:
    def __init__(self, rows):
        self._rows = [dict(r) for r in rows]

    def to_dict(self, orient="records"):
        return [dict(r) for r in self._rows]

    def __len__(self):
        return len(self._rows)


def _install(monkeypatch, **classes):
    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(**classes))


# --- quote_history: v6 ohlcv shape, source-explicit, ascending day order ----------


def test_quote_history_sorts_candles_ascending_and_uses_v6_sources(monkeypatch):
    calls: list[tuple[str | None, str, str]] = []

    class Equity:
        def __init__(self, symbol):
            self.symbol = symbol

        def ohlcv(self, *, start=None, end=None, interval=None, **kw):
            calls.append((self.symbol, interval, kw.get("source")))
            # Upstream returned DESCENDING — the adapter must re-sort by day.
            return _Frame(
                [
                    {
                        "time": "2026-11-05 07:00+07:00",
                        "open": 3,
                        "high": 3,
                        "low": 3,
                        "close": 3.0,
                        "volume": 100,
                    },
                    {
                        "time": "2026-11-03 07:00+07:00",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1.0,
                        "volume": 100,
                    },
                    {
                        "time": "2026-11-04 07:00+07:00",
                        "open": 2,
                        "high": 2,
                        "low": 2,
                        "close": 2.0,
                        "volume": 100,
                    },
                ]
            )

    class Market:
        def __init__(self, source=None, **kw):
            calls.append(("source", source, ""))

        def equity(self, symbol):
            return Equity(symbol)

    _install(monkeypatch, Market=Market)
    rows = vn_p.quote_history("FPT", days=3, interval="1D")
    assert [r["t"] for r in rows] == ["2026-11-03", "2026-11-04", "2026-11-05"]
    # first Market() construction carried a source; ohlcv got interval as named param
    assert calls[0] == ("source", "fhsc", "") or calls[0][0] == "source"
    assert any(c[0] == "FPT" and c[1] == "1D" for c in calls)


def test_quote_history_falls_back_to_second_source(monkeypatch):
    attempts: list[str | None] = []

    class Equity:
        def ohlcv(self, **kw):
            raise RuntimeError("fhsc down")

    class Market:
        def __init__(self, source=None, **kw):
            attempts.append(source)

        def equity(self, symbol):
            if attempts[-1] == "fhsc":
                return Equity()
            return types.SimpleNamespace(
                ohlcv=lambda **kw: _Frame(
                    [
                        {
                            "time": "2026-11-04 07:00+07:00",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 2.0,
                            "volume": 5,
                        }
                    ]
                )
            )

    _install(monkeypatch, Market=Market)
    rows = vn_p.quote_history("FPT", days=1, interval="1D")
    assert rows and rows[0]["c"] == 2.0
    assert "fhsc" in attempts and "ssi" in attempts


def test_quote_history_all_sources_dead_raises_unavailable(monkeypatch):
    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            raise RuntimeError("down")

    _install(monkeypatch, Market=Market)
    with pytest.raises(ProviderUnavailable):
        vn_p.quote_history("FPT", days=1, interval="1D")


# --- batch quote: group-level quote(symbols=...) on the fhsc source ---------------


def test_equity_quote_batch_uses_group_quote(monkeypatch):
    seen: dict = {}

    class EquityGroup:
        def quote(self, *, symbols=None, **kw):
            seen["symbols"] = symbols
            seen["kw"] = kw
            return _Frame([{"symbol": s, "match_price": 1.0} for s in symbols or []])

    class Market:
        def __init__(self, source=None, **kw):
            seen["source"] = source

        @property
        def equity(self):
            return EquityGroup()

    _install(monkeypatch, Market=Market)
    rows = vn_p.equity_quote_batch.__wrapped__(["FPT", "VCB"])
    assert seen["source"] == "fhsc"
    assert seen["symbols"] == ["FPT", "VCB"]
    assert rows and rows[0]["symbol"] == "FPT"


# --- listing: Reference(<src>).equity.list — never Listing().all_symbols ----------


def test_listing_symbols_uses_reference_equity_list(monkeypatch):
    seen: dict = {}

    class EquityRef:
        def list(self, **kw):
            seen.update(kw)
            return _Frame(
                [
                    {"symbol": "FPT", "exchange": "HOSE"},
                    {"symbol": "VCB", "exchange": "HOSE"},
                ]
            )

    class Reference:
        def __init__(self, source=None, **kw):
            seen["source"] = source

        @property
        def equity(self):
            return EquityRef()

    _install(monkeypatch, Reference=Reference)
    monkeypatch.setattr(vn_p, "_listing", None)
    rows = vn_p.listing_symbols()
    assert seen["source"] in ("ssi", "fhsc")
    assert [r["symbol"] for r in rows] == ["FPT", "VCB"]


# --- company: Reference("fhsc").company(<sym>) — never Company() ------------------


def test_company_info_uses_reference_company(monkeypatch):
    seen: dict = {}

    class Company:
        def info(self):
            return _Frame([{"symbol": "FPT", "short_name": "FPT Corp"}])

        def shareholders(self):
            return _Frame([{"shareholder": "SFIT"}])

        def officers(self):
            return _Frame([{"name": "CEO"}])

    class Reference:
        def __init__(self, source=None, **kw):
            seen["source"] = source

        def company(self, symbol):
            seen["symbol"] = symbol
            return Company()

    _install(monkeypatch, Reference=Reference)
    out = vn_p.company_info("FPT", detail=True)
    assert seen["source"] == "fhsc" and seen["symbol"] == "FPT"
    assert out["info"]["short_name"] == "FPT Corp"
    assert out["shareholders"][0]["shareholder"] == "SFIT"
    assert out["officers"][0]["name"] == "CEO"


def test_insider_and_events_use_reference_company(monkeypatch):
    seen: list[str] = []

    class Company:
        def insider_trading(self):
            seen.append("insider")
            return _Frame([{"symbol": "FPT"}] * 30)

        def events(self):
            seen.append("events")
            return _Frame([{"symbol": "FPT", "ex_date": "2026-11-05"}])

    class Reference:
        def __init__(self, source=None, **kw):
            pass

        def company(self, symbol):
            return Company()

    _install(monkeypatch, Reference=Reference)
    assert len(vn_p.insider_trading("FPT", limit=5)) == 5
    assert vn_p.corp_events("FPT", limit=5)[0]["ex_date"] == "2026-11-05"
    assert seen == ["insider", "events"]


# --- alt groups: count_back + interval, no legacy count/resolution ----------------


def test_alt_ohlcv_groups_use_count_back_and_named_interval(monkeypatch):
    seen: list[tuple] = []

    class G:
        def __init__(self, group, symbol):
            self.group, self.symbol = group, symbol

        def ohlcv(self, **kw):
            seen.append((self.group, self.symbol, kw))
            return _Frame(
                [{"time": "2026-11-07", "open": 1, "high": 1, "low": 1, "close": 1.0, "volume": 1}]
            )

    class Market:
        def __init__(self, source=None, **kw):
            seen.append(("source", source))

        def __getattr__(self, group):
            def make(symbol=None, *a, **kw):
                return G(group, symbol)

            return make

    _install(monkeypatch, Market=Market)
    vn_p.equity_ohlcv("FPT", count=30)
    vn_p.index_ohlcv("VNINDEX", count=30)
    vn_p.futures_ohlcv("VN30F1M", count=30)
    vn_p.forex_ohlcv("USDVND", count=30)
    vn_p.crypto_ohlv("BTCUSDT", count=30)
    vn_p.global_index("USA30", count=30)
    groups = [s[0] for s in seen if s[0] != "source"]
    assert groups == ["equity", "index", "futures", "forex", "crypto", "global_index"]
    for _, _, kw in (s for s in seen if s[0] != "source"):
        assert "count" not in kw and "resolution" not in kw
        assert kw.get("count_back") == 30
        assert "interval" in kw
    sources = [s[1] for s in seen if s[0] == "source"]
    assert "binance" in sources  # crypto must run keyless via binance
    assert all(s for s in sources)  # every call is source-explicit


def test_candles_range_uses_v6_ohlcv_sorts_and_normalizes(monkeypatch):
    seen: dict = {}

    class Equity:
        def ohlcv(self, *, start=None, end=None, interval=None, **kw):
            seen.update({"start": start, "end": end, "interval": interval})
            return _Frame(
                [
                    {
                        "time": "2026-11-05 07:00+07:00",
                        "open": 2,
                        "high": 2,
                        "low": 2,
                        "close": 2.0,
                        "volume": 200,
                    },
                    {
                        "time": "2026-11-04 07:00+07:00",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1.0,
                        "volume": 100,
                    },
                ]
            )

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            return Equity()

    _install(monkeypatch, Market=Market)
    rows = vn_p.candles_range("FPT", "2026-11-01", "2026-11-08")
    assert [r["t"] for r in rows] == ["2026-11-04", "2026-11-05"]
    assert rows[0]["c"] == 1.0 and rows[0]["v"] == 100.0
    assert seen["start"] == "2026-11-01" and seen["end"] == "2026-11-08"
    assert seen["interval"] == "1D"


def test_candles_range_raises_unavailable_when_empty(monkeypatch):
    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            return types.SimpleNamespace(ohlcv=lambda **kw: _Frame([]))

    _install(monkeypatch, Market=Market)
    with pytest.raises(ProviderUnavailable):
        vn_p.candles_range("FPT", "2026-11-01", "2026-11-08")


# --- msn_fx_gold: v6 Market forex + commodity (explorer.msn is gone) --------------


def test_msn_fx_gold_uses_v6_forex_and_commodity(monkeypatch):
    seen: list[tuple] = []

    class G:
        def __init__(self, group, symbol):
            self.group, self.symbol = group, symbol

        def ohlcv(self, *, start=None, end=None, interval=None, **kw):
            seen.append((self.group, self.symbol, start, end, interval))
            close = 25000.0 if self.group == "forex" else 4000.0
            return _Frame([{"time": "2026-11-07", "close": close}])

    class Market:
        def __init__(self, source=None, **kw):
            seen.append(("source", source))

        def __getattr__(self, group):
            def make(symbol=None):
                return G(group, symbol)

            return make

    _install(monkeypatch, Market=Market)
    out = vn_p.msn_fx_gold(days=35)
    pairs = {(s[0], s[1]) for s in seen if s[0] != "source"}
    assert ("forex", "USDVND") in pairs
    assert ("commodity", "GC") in pairs  # XAUUSD rides the GC futures contract
    sources = {s[1] for s in seen if s[0] == "source"}
    assert sources <= {"fhsc", "fmp"}
    assert all(s[2] and s[3] for s in seen if s[0] != "source")  # start/end always set
    by_symbol = {row["symbol"]: row for row in out}
    assert by_symbol["USDVND"]["points"] == 1
    assert by_symbol["XAUUSD"]["points"] == 1


# --- fix-pass contracts from the whole-branch review -------------------------------


def test_quote_history_routes_index_symbols_to_the_index_group(monkeypatch):
    """Cycle refresh feeds VNINDEX/VN30/... — the equity group cannot serve them."""
    seen: list[str] = []

    class Equity:
        def ohlcv(self, **kw):
            seen.append("equity")
            raise RuntimeError("index code is not an equity")

    class IndexG:
        def ohlcv(self, **kw):
            seen.append("index")
            return _Frame(
                [{"time": "2026-11-05", "open": 1, "high": 1, "low": 1,
                  "close": 1300.0, "volume": 5}]
            )

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            return Equity()

        def index(self, symbol):
            return IndexG()

    _install(monkeypatch, Market=Market)
    rows = vn_p.quote_history("VNINDEX", days=5)
    assert seen == ["index"]
    assert rows and rows[0]["c"] == 1300.0


class _ScalingMarket:
    """Live behaviour measured 2026-11-08 (ssi): the equity group DOES answer
    for an index code, but in thousand-dong scaling (VN100 1764.3 → 1.76);
    only the index group returns points. A fake that raises on the equity
    group hides exactly that silent mis-scaling."""

    seen: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, source=None, **kw):
        pass

    def _group(self, name, symbol, close):
        seen = self.seen

        class G:
            def ohlcv(self, **kw):
                seen.append((name, symbol))
                return _Frame(
                    [{"time": "2026-11-06", "open": close, "high": close, "low": close,
                      "close": close, "volume": 5}]
                )

        return G()

    def equity(self, symbol):
        return self._group("equity", symbol, 1.76)

    def index(self, symbol):
        return self._group("index", symbol, 1764.3)


@pytest.mark.parametrize("code", sorted(INDEX_SYMBOLS))
def test_every_index_symbol_rides_the_index_group(monkeypatch, code):
    """#77: route on units.INDEX_SYMBOLS (26 codes), not a hand-copied subset."""
    _ScalingMarket.seen = []
    _install(monkeypatch, Market=_ScalingMarket)
    rows = vn_p.quote_history(code, days=5)
    assert {group for group, _ in _ScalingMarket.seen} == {"index"}
    assert rows[-1]["c"] == 1764.3  # points, not the equity group's /1000 figure


@pytest.mark.parametrize("code", ["vn100", " VNMID ", "UpcomIndex"])
def test_index_routing_normalises_the_code(monkeypatch, code):
    _ScalingMarket.seen = []
    _install(monkeypatch, Market=_ScalingMarket)
    vn_p.candles_range(code, "2026-11-01", "2026-11-07")
    assert _ScalingMarket.seen == [("index", code.strip().upper())]


def test_stock_symbols_stay_on_the_equity_group(monkeypatch):
    _ScalingMarket.seen = []
    _install(monkeypatch, Market=_ScalingMarket)
    vn_p.quote_history("FPT", days=5)
    assert _ScalingMarket.seen == [("equity", "FPT")]


def test_equity_ohlcv_refuses_index_codes(monkeypatch):
    """vn_equity_ohlcv is labelled thousand dong: an index code would come back
    /1000 from the equity group. Point the caller at vn_index_ohlcv instead."""
    _ScalingMarket.seen = []
    _install(monkeypatch, Market=_ScalingMarket)
    with pytest.raises(ProviderBadData, match="vn_index_ohlcv"):
        vn_p.equity_ohlcv("VN100", count=5)
    assert _ScalingMarket.seen == []


def test_index_ohlcv_sorts_ascending(monkeypatch):
    class IndexG:
        def ohlcv(self, **kw):
            return _Frame(
                [
                    {"time": "2026-11-05", "close": 2.0},
                    {"time": "2026-11-04", "close": 1.0},
                ]
            )

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def index(self, symbol):
            return IndexG()

    _install(monkeypatch, Market=Market)
    rows = vn_p.index_ohlcv("VNINDEX", count=5)
    assert [r["time"] for r in rows] == ["2026-11-04", "2026-11-05"]


def test_equity_trades_returns_newest_first(monkeypatch):
    """v4 contract: newest-first. Gen-6 profiles flip row order — normalize here."""
    class Equity:
        def trades(self, **kw):
            return _Frame(
                [
                    {"time": "09:15:00", "volume": 100},
                    {"time": "14:45:00", "volume": 300},
                    {"time": "11:00:00", "volume": 200},
                ]
            )

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            return Equity()

    _install(monkeypatch, Market=Market)
    rows = vn_p.equity_trades("FPT", limit=2)
    assert [r["time"] for r in rows] == ["14:45:00", "11:00:00"]


def test_candles_range_drops_nan_close_rows(monkeypatch):
    class Equity:
        def ohlcv(self, **kw):
            return _Frame(
                [
                    {"time": "2026-11-04", "open": 1, "high": 1, "low": 1,
                     "close": float("nan"), "volume": 0},
                    {"time": "2026-11-05", "open": 1, "high": 1, "low": 1,
                     "close": 2.0, "volume": 5},
                ]
            )

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            return Equity()

    _install(monkeypatch, Market=Market)
    rows = vn_p.candles_range("FPT", "2026-11-01", "2026-11-08")
    assert [r["t"] for r in rows] == ["2026-11-05"]


# --- key helpers: v6 has no change_api_key/vnai; source keys decide "keyed" -------


def test_ensure_api_key_reports_source_keys(monkeypatch):
    for var in ("VNSTOCK_API_KEY", "FHSC_API_KEY", "SSI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert vn_p.ensure_api_key() == "anonymous"
    assert vn_p.quota_info()["tier"] == "anonymous"

    monkeypatch.setenv("FHSC_API_KEY", "k1")
    assert vn_p.ensure_api_key() == "keyed"
    q = vn_p.quota_info()
    assert isinstance(q, dict) and "tier" in q and q["sources"]["fhsc"] is True
