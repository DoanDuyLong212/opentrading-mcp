"""vnstock gen-6 adapter contracts (plan vnstock-gen6-migration-2026-11-08, Task 3).

Stubs fake the gen-6 surface (Market/Reference with per-call source). The
provider must call source-explicit v6 shapes — `Market(<src>).equity(...).ohlcv`
— never gen-4 classes (Quote/Listing/Company/Finance), and candles must come
back sorted ascending by day regardless of upstream row order.
"""

from __future__ import annotations

import sys
import types

import pytest

from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderUnavailable


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


def _legacy_chain(monkeypatch, **chains: tuple[str, ...]) -> None:
    """Re-enable a discontinued fhsc chain so the route's PARSER stays tested
    until its replacement lands (fhsc/fmp were dropped on 2026-11-08)."""
    for name, chain in chains.items():
        monkeypatch.setattr(vn_p, name, chain)


def test_quote_history_falls_back_to_second_source(monkeypatch):
    attempts: list[str | None] = []

    class Equity:
        def ohlcv(self, **kw):
            raise RuntimeError("ssi down")

    class Market:
        def __init__(self, source=None, **kw):
            attempts.append(source)

        def equity(self, symbol):
            if attempts[-1] == "ssi":
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
    assert attempts == ["ssi", "dnse"]  # fhsc is no longer in any chain


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
    _legacy_chain(monkeypatch, SRC_QUOTE=("fhsc",))
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
    _legacy_chain(monkeypatch, SRC_FUNDAMENTAL=("fhsc",))
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
    _legacy_chain(monkeypatch, SRC_FUNDAMENTAL=("fhsc",))
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
    monkeypatch.setattr(vn_p, "_today_partial_bar", lambda symbol: None)  # Q4, tested apart
    vn_p.equity_ohlcv("FPT", count=30)
    vn_p.index_ohlcv("VNINDEX", count=30)
    vn_p.futures_ohlcv("VN30F1M", count=30)
    vn_p.crypto_ohlv("BTCUSDT", count=30)
    groups = [s[0] for s in seen if s[0] != "source"]
    assert groups == ["equity", "index", "futures", "crypto"]
    for _, _, kw in (s for s in seen if s[0] != "source"):
        assert "count" not in kw and "resolution" not in kw
        assert kw.get("count_back") == 30
        assert "interval" in kw
    sources = [s[1] for s in seen if s[0] == "source"]
    assert sources == ["ssi", "ssi", "ssi", "binance"]  # ssi first; crypto keyless
    assert all(s for s in sources)  # every call is source-explicit


@pytest.mark.parametrize(
    "call",
    [
        lambda: vn_p.equity_quote_batch(["FPT"]),
        lambda: vn_p.company_info("FPT"),
        lambda: vn_p.insider_trading("FPT"),
        lambda: vn_p.corp_events("FPT"),
        lambda: vn_p.cashflow("FPT"),
        lambda: vn_p.equity_ratios("FPT", "year"),
    ],
    ids=["quote", "company", "insider", "events", "cashflow", "ratios"],
)
def test_fhsc_only_routes_fail_as_not_configured(monkeypatch, call):
    """Routes only fhsc/fmp/tcbs serve must say 'not configured' (not retryable)
    without calling upstream, and must not open the shared vnstock breaker."""
    calls: list[str] = []

    class Anything:
        def __init__(self, source=None, **kw):
            calls.append(str(source))

        def __getattr__(self, name):
            raise AssertionError(f"upstream touched: {name}")

    _install(monkeypatch, Market=Anything, Reference=Anything, Fundamental=Anything)
    from opentrading_mcp.providers import circuit

    circuit.reset("vnstock")
    for _ in range(circuit.get_circuit("vnstock").failure_threshold + 1):
        with pytest.raises(ProviderUnavailable) as info:
            call()
        assert info.value.reason == "not_configured", info.value
    assert calls == []
    circuit.get_circuit("vnstock").call(lambda: None)  # breaker still closed


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


# --- fix-pass contracts from the whole-branch review -------------------------------


def test_quote_history_routes_index_symbols_to_the_index_group(monkeypatch):
    """Cycle refresh feeds VNINDEX/VN30/... — the equity group cannot serve them."""
    monkeypatch.setattr(vn_p, "_today_partial_bar", lambda symbol: None)  # Q4, tested apart
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


_KEY_VARS = (
    "VNSTOCK_API_KEY", "FHSC_API_KEY", "FMP_API_KEY", "SSI_API_KEY", "SSI_API_SECRET",
    "DNSE_API_KEY", "DNSE_API_SECRET", "DNSE_SECRET",
)


def _clear_keys(monkeypatch):
    for var in _KEY_VARS:
        monkeypatch.delenv(var, raising=False)


def test_ensure_api_key_reports_source_keys(monkeypatch):
    _clear_keys(monkeypatch)
    assert vn_p.ensure_api_key() == "anonymous"
    assert vn_p.quota_info()["tier"] == "anonymous"

    # #87: a discontinued source's key, or half of SSI's pair, unlocks nothing
    monkeypatch.setenv("FHSC_API_KEY", "k1")
    monkeypatch.setenv("SSI_API_KEY", "k2")
    assert vn_p.ensure_api_key() == "anonymous"
    q = vn_p.quota_info()
    assert q["sources"]["ssi"] is False and "fhsc" not in q["sources"]

    monkeypatch.setenv("SSI_API_SECRET", "s2")
    assert vn_p.ensure_api_key() == "keyed"
    q = vn_p.quota_info()
    assert q["tier"] == "source-keyed" and q["sources"]["ssi"] is True


def test_quota_info_reports_which_route_chains_can_answer(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("SSI_API_KEY", "k")
    monkeypatch.setenv("SSI_API_SECRET", "s")
    chains = vn_p.quota_info()["chains"]
    assert chains["equity"] == ["ssi"] and chains["index"] == ["ssi"]
    assert chains["trades"] == []  # dnse only
    assert chains["crypto"] == ["binance"]  # keyless
    for route in ("quote", "fundamental"):
        assert chains[route] == [], route  # fhsc/tcbs-only routes
    assert "forex" not in chains and "global" not in chains  # moved to yfinance


def test_dnse_secret_is_aliased_for_vnstock(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("DNSE_SECRET", "shared-secret")
    vn_p._alias_dnse_secret()
    import os

    assert os.environ["DNSE_API_SECRET"] == "shared-secret"


def test_dnse_alias_never_overrides_an_explicit_value(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("DNSE_SECRET", "project-secret")
    monkeypatch.setenv("DNSE_API_SECRET", "vnstock-secret")
    vn_p._alias_dnse_secret()
    import os

    assert os.environ["DNSE_API_SECRET"] == "vnstock-secret"


# --- #83: per-source errors and a machine-readable reason ---------------------------


class _VnstockError(Exception):
    def __init__(self, msg, code=""):
        super().__init__(msg)
        self.code = code


class RateLimitedError(_VnstockError):
    pass


class CredentialError(_VnstockError):
    pass


def _failing(errors: dict[str, Exception]):
    return [(src, (lambda e=exc: (_ for _ in ()).throw(e))) for src, exc in errors.items()]


def test_fetch_frame_rate_limit_is_not_hidden_by_a_later_auth_error():
    """#83: v4 kept only the LAST error — fhsc's rate limit vanished behind
    ssi's missing key. Every source's outcome survives now."""
    with pytest.raises(ProviderUnavailable) as info:
        vn_p._fetch_frame(
            _failing({
                "ssi": RateLimitedError("slow down", code="VNSTOCK_RATE_LIMITED"),
                "dnse": CredentialError("Chưa có khoá", code="VNSTOCK_CREDENTIAL_MISSING"),
            }),
            "candles FPT",
        )
    assert info.value.reason == "upstream_rate_limited"
    from opentrading_mcp.tools.shared import RATE_LIMITED

    assert RATE_LIMITED in str(info.value)  # cycle-refresh back-off keys on this
    assert "ssi: slow down" in str(info.value) and "dnse: Chưa có khoá" in str(info.value)


def test_fetch_frame_all_keys_missing_is_not_configured():
    with pytest.raises(ProviderUnavailable) as info:
        vn_p._fetch_frame(
            _failing({
                "ssi": CredentialError("no ssi key", code="VNSTOCK_CREDENTIAL_MISSING"),
                "dnse": CredentialError("no dnse key", code="VNSTOCK_CREDENTIAL_MISSING"),
            }),
            "candles FPT",
        )
    assert info.value.reason == "not_configured"


def test_fetch_frame_empty_plus_auth_is_plain_no_data():
    """One source answered (empty), so this is not a configuration problem."""
    with pytest.raises(ProviderUnavailable) as info:
        vn_p._fetch_frame(
            [("ssi", lambda: _Frame([])), *_failing({"dnse": CredentialError("no key")})],
            "candles VNMID",
        )
    assert info.value.reason is None
    assert "ssi: empty" in str(info.value)


def test_not_configured_does_not_open_the_breaker():
    from opentrading_mcp.providers import circuit
    from opentrading_mcp.providers.errors import ProviderUnavailable as PU

    breaker = circuit.CircuitBreaker("test-config")
    for _ in range(breaker.failure_threshold + 2):
        with pytest.raises(PU):
            breaker.call(lambda: (_ for _ in ()).throw(PU("no key", reason="not_configured")))
    breaker.call(lambda: None)  # still closed


def test_candles_range_has_its_own_breaker(monkeypatch):
    """#83: cycle refresh must not open the breaker interactive tools share."""
    from opentrading_mcp.providers import circuit

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            raise RuntimeError("upstream down")

    _install(monkeypatch, Market=Market)
    circuit.reset("vnstock")
    circuit.reset("vnstock-batch")
    for _ in range(circuit.get_circuit("vnstock-batch").failure_threshold):
        with pytest.raises(ProviderUnavailable):
            vn_p.candles_range("FPT", "2026-11-01", "2026-11-07")
    circuit.get_circuit("vnstock").call(lambda: None)  # interactive breaker closed
    circuit.reset("vnstock-batch")


async def test_quote_batch_tool_envelope_says_not_configured(monkeypatch):
    """What clients see for a discontinued route: unavailable, not retryable."""
    from opentrading_mcp.server import create_server, register_preset

    class Anything:
        def __init__(self, *a, **kw):
            raise AssertionError("upstream touched")

    _install(monkeypatch, Market=Anything)
    server = create_server("all")
    register_preset(server, "all")
    env = await server._tool_manager.get_tool("vn_equity_quote_batch").fn(symbols=["FPT"])
    assert env["availability"] == "unavailable"
    assert env["reason"] == "not_configured"
    assert env["retryable"] is False


def test_not_configured_is_not_counted_as_upstream_failure(monkeypatch):
    from opentrading_mcp import obs

    before = dict(obs._upstream_failures)
    with pytest.raises(ProviderUnavailable):
        vn_p.equity_quote_batch(["FPT"])
    assert obs._upstream_failures.get("vnstock", 0) == before.get("vnstock", 0)


def test_records_turn_timestamps_into_iso_strings():
    """Gen-6 frames carry tz-aware pd.Timestamp; envelopes must json-serialise."""
    import json

    import pandas as pd

    frame = pd.DataFrame(
        {"time": [pd.Timestamp("2026-11-06 14:45:02.813", tz="Asia/Ho_Chi_Minh")],
         "price": [50.8]}
    )
    rows = vn_p._records(frame)
    assert rows == [{"time": "2026-11-06T14:45:02.813000+07:00", "price": 50.8}]
    json.dumps(rows)


def test_equity_trades_asks_dnse_for_big_pages(monkeypatch):
    """dnse pages the whole session using `limit` as the page size (500-page cap):
    small limits meant hundreds of requests and a truncated day."""
    seen: dict = {}

    class Equity:
        def trades(self, **kw):
            seen.update(kw)
            return _Frame([
                {"time": f"2026-11-06T14:{m:02d}:00+07:00", "price": 50.0 + m, "volume": 1}
                for m in range(10)
            ])

    class Market:
        def __init__(self, source=None, **kw):
            seen["source"] = source

        def equity(self, symbol):
            return Equity()

    _install(monkeypatch, Market=Market)
    rows = vn_p.equity_trades("FPT", limit=3)
    assert seen["source"] == "dnse"
    assert seen["limit"] >= 1000
    assert [r["price"] for r in rows] == [59.0, 58.0, 57.0]  # newest first, sliced


class _RefEquity:
    """gen-6 Reference(src).equity shape (pinned by test_vnstock_signatures)."""

    def __init__(self, source, calls, fail=()):
        self.source, self.calls, self.fail = source, calls, fail

    def _rows(self):
        import pandas as pd

        if self.source in self.fail:
            raise RuntimeError(f"{self.source} down")
        return pd.DataFrame([
            {"symbol": "VCB", "exchange": "HOSE", "icb_code": "8355", "icb_name": "Ngân hàng"},
            {"symbol": "FPT", "exchange": "HOSE", "icb_code": "9533", "icb_name": "Phần mềm"},
            {"symbol": "SHS", "exchange": "HNX", "icb_code": "8777", "icb_name": "Môi giới"},
        ])

    def list_by_exchange(self, exchange=None):
        self.calls.append((self.source, "exchange", exchange))
        rows = self._rows()
        return rows[rows["exchange"] == exchange] if exchange else rows

    def list_by_industry(self, exchange=None):
        self.calls.append((self.source, "industry", exchange))
        return self._rows()

    def list_by_group(self, group):
        self.calls.append((self.source, "group", group))
        import pandas as pd

        if self.source in self.fail:
            raise RuntimeError(f"{self.source} down")
        return pd.DataFrame([{"symbol": "VCB", "index_symbol": group}])

    def list(self, **kw):
        raise AssertionError("reference_equity must not fall back to a different method")


def _install_reference(monkeypatch, fail=()):
    calls: list[tuple] = []

    class Reference:
        def __init__(self, source=None, **kw):
            self.equity = _RefEquity(source, calls, fail)

    _install(monkeypatch, Reference=Reference)
    return calls


def test_reference_exchange_is_passed_upstream(monkeypatch):
    """#88: v6 pulled the whole market on every call and filtered locally."""
    calls = _install_reference(monkeypatch)
    rows = vn_p.reference_equity("HOSE")
    assert calls == [("ssi", "exchange", "HOSE")]
    assert {r["symbol"] for r in rows} == {"VCB", "FPT"}


def test_reference_industry_filters_on_icb(monkeypatch):
    """gen 6's list_by_industry has no industry argument: v6 passed the industry
    name as the exchange. Filter on icb_name (substring) or icb_code (exact)."""
    calls = _install_reference(monkeypatch)
    assert [r["symbol"] for r in vn_p.reference_equity("HOSE", by="industry",
                                                       key="ngân hàng")] == ["VCB"]
    assert [r["symbol"] for r in vn_p.reference_equity("ALL", by="industry",
                                                       key="8777")] == ["SHS"]
    assert calls[0] == ("ssi", "industry", "HOSE") and calls[1] == ("ssi", "industry", None)


def test_reference_group_rides_the_chain(monkeypatch):
    calls = _install_reference(monkeypatch, fail=("ssi",))
    rows = vn_p.reference_equity(by="group", key="VN30")
    assert rows[0]["symbol"] == "VCB"
    assert calls == [("ssi", "group", "VN30"), ("dnse", "group", "VN30")]


def test_reference_failure_keeps_every_source_and_never_retries_ssi(monkeypatch):
    """v6 retried ssi with .list() after the chain failed, masking the real error."""
    calls = _install_reference(monkeypatch, fail=("ssi", "dnse"))
    with pytest.raises(ProviderUnavailable) as info:
        vn_p.reference_equity("HOSE")
    assert "ssi: ssi down" in str(info.value) and "dnse: dnse down" in str(info.value)
    assert [c[0] for c in calls] == ["ssi", "dnse"]


def test_dnse_trade_volumes_are_scaled_to_shares(monkeypatch):
    """dnse counts lots of 10: the 2026-11-06 FPT session summed to 1,216,220
    while 12,162,200 shares traded (v4 and the DNSE board agree on the latter)."""
    import pandas as pd

    class Equity:
        def trades(self, **kw):
            return pd.DataFrame([
                {"time": "2026-11-06T14:45:02+07:00", "price": 50.8, "volume": 20,
                 "match_type": "ATC", "accumulated_volume": 1216220},
                {"time": "2026-11-06T14:27:52+07:00", "price": 50.9, "volume": 620,
                 "match_type": "sell", "accumulated_volume": 1100000},
            ])

    class Market:
        def __init__(self, source=None, **kw):
            pass

        def equity(self, symbol):
            return Equity()

    _install(monkeypatch, Market=Market)
    rows = vn_p.equity_trades("FPT", limit=5)
    assert [r["volume"] for r in rows] == [200, 6200]  # v4 shows the 6,200-share print
    assert rows[0]["accumulated_volume"] == 12162200
    assert rows[0]["price"] == 50.8  # prices are already thousand dong, as in v4


def test_redact_hides_vnstock_secret_names():
    from opentrading_mcp.auth import redact

    for name in ("DNSE_API_SECRET", "SSI_API_SECRET", "SSI_API_PRIVATE"):
        assert redact(f"env {name}=abc") == "[REDACTED]"
