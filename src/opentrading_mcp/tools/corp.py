"""Corp tools: dividends/splits and holders for VN + world (P6)."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.providers import dnse as dnse_p
from opentrading_mcp.providers import vietstock as vs_p
from opentrading_mcp.providers import vn_public as pub_p
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers import yfinance as yf_p
from opentrading_mcp.providers.errors import (
    ProviderAuthMissing,
    ProviderBadData,
    ProviderUnavailable,
)
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext, run_blocking


def _fnum(val: Any) -> float | None:
    """Best-effort float for mixed upstream numerics."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def register_corp_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def dividends_splits(
        symbol: str,
        region: str = "vn",
        limit: int = 20,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Cash dividends and share issues/splits. Use for payout history.

        region: 'vn' (vnstock Company events: DIV cash, ISS bonus/private) or
        'world' (yfinance actions). limit: max events returned.
        """
        area = region.strip().lower()
        if ctx is not None:
            await ctx.log("info", f"dividends_splits {symbol} {area}")
        try:
            if area == "vn":
                rows = await run_blocking(
                    functools.partial(vn_p.corp_events, symbol, max(int(limit), 1)),
                    "dividends_splits",
                    timeout_secs=60.0,
                )
                events = [
                    {
                        "event_code": r.get("event_code"),
                        "title": r.get("event_title_en") or r.get("event_title_vi"),
                        "exright_date": r.get("exright_date"),
                        "record_date": r.get("record_date"),
                        "payout_date": r.get("payout_date"),
                        "value_per_share": r.get("value_per_share"),
                        "exercise_ratio": r.get("exercise_ratio"),
                        "is_cash_dividend": r.get("event_code") == "DIV",
                        "is_share_issue": r.get("event_code") == "ISS",
                    }
                    for r in rows
                ]
            elif area == "world":
                rows = await run_blocking(
                    functools.partial(yf_p.corp_actions, symbol),
                    "dividends_splits",
                    timeout_secs=60.0,
                )
                kept = [
                    r
                    for r in rows
                    if (r.get("dividends") or 0) > 0 or (r.get("splits") or 0) not in (0, 1, 1.0)
                ]
                events = kept[: max(int(limit), 1)]
            else:
                raise ProviderBadData(f"unknown region {region!r} (vn|world)")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "dividends_splits"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(
            {"symbol": symbol.upper(), "region": area, "events": events},
            source="vnstock" if area == "vn" else "yfinance",
        )

    @server.tool(annotations=READ_ONLY)
    async def holders(
        symbol: str,
        region: str = "vn",
        kind: str = "all",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Shareholder and institutional holder tables. Use for ownership reads.

        region: 'vn' (vnstock shareholders) or 'world' (yfinance).
        kind: 'major'|'institutional'|'mutualfund'|'all' (world only;
        vn returns shareholders for any kind).
        """
        area = region.strip().lower()
        want = kind.strip().lower()
        if ctx is not None:
            await ctx.log("info", f"holders {symbol} {area} {want}")
        try:
            if area == "vn":
                info = await run_blocking(
                    functools.partial(vn_p.company_info, symbol, True),
                    "holders",
                    timeout_secs=60.0,
                )
                holders_rows = info.get("shareholders") or []
                src = "vnstock"
            elif area == "world":
                if want not in ("major", "institutional", "mutualfund", "all"):
                    raise ProviderBadData(f"unknown kind {kind!r}")
                holders_rows = await run_blocking(
                    functools.partial(yf_p.stock_holders, symbol, want),
                    "holders",
                    timeout_secs=60.0,
                )
                src = "yfinance"
            else:
                raise ProviderBadData(f"unknown region {region!r} (vn|world)")
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "holders"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(
            {"symbol": symbol.upper(), "region": area, "kind": want, "holders": holders_rows},
            source=src,
        )

    @server.tool(annotations=READ_ONLY)
    async def event_calendar_vn(
        event: str = "dividends",
        symbol: str | None = None,
        limit: int = 20,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Vietstock corporate-action calendar. Use for dividend/meeting/listing dates.

        event: 'dividends' (payouts, bonus, issues), 'listings', 'meetings'.
        symbol: filter one ticker (omit for market-wide). No earnings-report
        dates exist upstream; KQKD dates come from company_events instead.
        """
        if ctx is not None:
            await ctx.log("info", f"event_calendar_vn {event} {symbol}")
        try:
            events = await run_blocking(
                functools.partial(vs_p.event_calendar, event, symbol or "", limit),
                "event_calendar_vn",
                timeout_secs=45.0,
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "event_calendar_vn"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(
            {"event": event, "symbol": (symbol or "").upper(), "events": events},
            source="vietstock",
        )

    @server.tool(annotations=READ_ONLY)
    async def block_trades(
        symbol: str,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 30,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Matched vs negotiated put-through splits per day. Use for dark-pool-style reads.

        from_date/to_date: ISO dates (default last 30d). pt_vol/pt_val are the
        thỏa thuận leg; pt_pct is its share of daily value.
        """
        import datetime

        if ctx is not None:
            await ctx.log("info", f"block_trades {symbol}")

        def _vn(iso: str) -> str:
            return datetime.date.fromisoformat(iso).strftime("%d/%m/%Y")

        today = datetime.date.today()
        try:
            frm = (
                _vn(from_date)
                if from_date
                else (today - datetime.timedelta(days=30)).strftime("%d/%m/%Y")
            )
            to = _vn(to_date) if to_date else today.strftime("%d/%m/%Y")
        except ValueError as exc:
            return make_envelope(
                {"tool": "block_trades"},
                source="unavailable",
                warnings=[f"bad date: {exc}"],
                availability="unavailable",
            )
        try:
            rows = await run_blocking(
                functools.partial(vs_p.negotiated_trades, symbol, frm, to, limit),
                "block_trades",
                timeout_secs=45.0,
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "block_trades"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        days = []
        tot_mt = tot_pt = 0.0
        for row in rows:
            try:
                mt_v = float(row.get("mt_val") or 0)
                pt_v = float(row.get("pt_val") or 0)
            except (TypeError, ValueError):
                continue
            tot_mt += mt_v
            tot_pt += pt_v
            days.append(
                {
                    "date": row.get("date"),
                    "close": row.get("close"),
                    "mt_vol": row.get("mt_vol"),
                    "mt_val": mt_v,
                    "pt_vol": row.get("pt_vol"),
                    "pt_val": pt_v,
                    "pt_pct": round(pt_v / (mt_v + pt_v) * 100, 2) if mt_v + pt_v else 0.0,
                }
            )
        return make_envelope(
            {
                "symbol": symbol.upper(),
                "days": days,
                "totals": {
                    "mt_val": tot_mt,
                    "pt_val": tot_pt,
                    "pt_pct": round(tot_pt / (tot_mt + tot_pt) * 100, 2)
                    if tot_mt + tot_pt
                    else 0.0,
                },
            },
            source="vietstock",
        )

    @server.tool(annotations=READ_ONLY)
    async def analyst_consensus(
        symbol: str | None = None,
        limit: int = 30,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Analyst ratings and price targets parsed from report titles. Use for street views.

        symbol: filter one ticker (omit for latest across market). Ratings come
        from title text (MUA/BÁN/NẮM GIỮ...), not a consensus feed; history per
        symbol shows upgrades/downgrades. vs_reports_search API is dead upstream.
        """
        if ctx is not None:
            await ctx.log("info", f"analyst_consensus {symbol}")
        try:
            reports = await run_blocking(
                functools.partial(pub_p.analyst_reports, max(int(limit) * 2, 10)),
                "analyst_consensus",
                timeout_secs=45.0,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "analyst_consensus"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        rows = [r for r in reports if isinstance(r, dict) and r.get("title")]
        if symbol:
            want = symbol.strip().upper()
            rows = [r for r in rows if (r.get("symbol") or "").upper() == want]
        return make_envelope(
            {"symbol": (symbol or "").upper(), "reports": rows[: max(int(limit), 1)]},
            source="vietstock-scrape",
        )

    @server.tool(annotations=READ_ONLY)
    async def ipo_calendar_vn(
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """HNX auction calendar plus announcement fallback. Use for upcoming supply.

        Calendar is often empty (no scheduled auctions); announcements carry
        the latest auction news with dates.
        """
        if ctx is not None:
            await ctx.log("info", "ipo_calendar_vn")
        try:
            data = await run_blocking(pub_p.hnx_auctions, "ipo_calendar_vn", timeout_secs=45.0)
        except (ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "ipo_calendar_vn"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(data, source="hnx-scrape")

    @server.tool(annotations=READ_ONLY)
    async def futures_basis(
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """VN30F1M price minus VN30 spot. Use for premium/discount reads.

        DNSE exposes no open-interest field, so no OI is reported; basis_bps
        is (futures-spot)/spot in basis points.
        """
        if ctx is not None:
            await ctx.log("info", "futures_basis")
        try:
            trades = await run_blocking(
                functools.partial(dnse_p.latest_trade, ["VN30F1M"]),
                "futures_basis",
                timeout_secs=30.0,
            )
            spot_rows = await run_blocking(
                functools.partial(vn_p.index_ohlcv, "VN30", 5),
                "futures_basis",
                timeout_secs=60.0,
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "futures_basis"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        fut = None
        if trades and isinstance(trades[0], dict):
            for key in ("price", "matchPrice", "match_price", "close", "c", "last"):
                fut = _fnum(trades[0].get(key))
                if fut is not None:
                    break
        spot = None
        closes = [r.get("c") for r in spot_rows if isinstance(r, dict) and r.get("c")]
        if closes:
            spot = _fnum(closes[-1])
        if fut is None or not spot:
            return make_envelope(
                {"futures": fut, "spot": spot},
                source="dnse+vnstock",
                warnings=["missing leg"],
                availability="partial",
            )
        basis = fut - spot
        return make_envelope(
            {
                "futures": fut,
                "spot": spot,
                "basis": round(basis, 2),
                "basis_bps": round(basis / spot * 10000, 1),
            },
            source="dnse+vnstock",
        )

    @server.tool(annotations=READ_ONLY)
    async def financial_detail(
        symbol: str,
        statement: str = "KQKD",
        periods_n: int = 8,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Free detailed statements, every line item per period. Use for deep BCTC reads.

        statement: KQKD (income), CDKT (balance), LCTT (cashflow), TM (notes),
        BCTT. periods_n: recent periods (unit VND billions). Free /data/*
        chain — no paid package; legs fail independently (partial).
        NOTE: upstream currently gates periods+values behind an upgraded
        package (Package_Permission) — until then this reports unavailable;
        norms list still resolves. Mirror (vs_financeinfo) covers summaries.
        """
        if ctx is not None:
            await ctx.log("info", f"financial_detail {symbol} {statement}")
        try:
            data = await run_blocking(
                functools.partial(vs_p.financial_detail, symbol, statement, periods_n),
                "financial_detail",
                timeout_secs=90.0,
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "financial_detail"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(data, source="vietstock")

    return [
        {"name": "dividends_splits"},
        {"name": "holders"},
        {"name": "event_calendar_vn"},
        {"name": "block_trades"},
        {"name": "analyst_consensus"},
        {"name": "ipo_calendar_vn"},
        {"name": "futures_basis"},
        {"name": "financial_detail"},
    ]
