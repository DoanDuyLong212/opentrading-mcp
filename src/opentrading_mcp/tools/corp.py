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


def _parse_report_date(val: Any) -> Any:
    """Parse a dd/mm/yyyy report date to a date object; None when unparsable."""
    import datetime

    if not val or not isinstance(val, str):
        return None
    try:
        return datetime.datetime.strptime(val.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def register_corp_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def dividends_splits(
        symbol: str,
        region: str = "vn",
        limit: int = 20,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Cổ tức tiền mặt và phát hành/tách cổ phiếu. Dùng khi xem lịch sử trả thưởng của 1 mã.

        Dùng khi: "FPT đã chia cổ tức những năm nào".
        Không dùng khi: cần lịch cổ tức/niêm yết/họp toàn thị trường theo ngày (dùng
            event_calendar_vn); cần feed công bố gốc (dùng corporate_calendar).

        region: 'vn' (sự kiện Company của vnstock: DIV tiền mặt, ISS thưởng/phát hành riêng lẻ) hoặc
        'world' (actions của yfinance). limit: số sự kiện tối đa.
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
        """Lịch sự kiện doanh nghiệp của Vietstock. Dùng khi cần ngày cổ tức/niêm yết/họp theo lịch.

        Dùng khi: "khi nào FPT chia cổ tức", "lịch họp ĐHĐCĐ".
        Không dùng khi: cần feed công bố thô (dùng corporate_calendar); cần sự kiện đã phân loại
            theo loại (dùng company_events); cần ngày BÁO CÁO KQKD — nguồn không có ngày này, dùng
            company_events thay thế.

        event: 'dividends' (trả cổ tức, thưởng, phát hành), 'listings', 'meetings'.
        symbol: lọc 1 mã (bỏ qua để xem toàn thị trường).
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
        """Tách khớp lệnh và thỏa thuận theo ngày. Dùng khi đọc dòng tiền thỏa thuận (dark-pool) của
            1 mã.

        Dùng khi: "thỏa thuận HPG tuần này", kiểm tra tay to gom qua put-through.
        Không dùng khi: cần dòng tiền khối ngoại tổng hợp (dùng money_flow); cần mua/bán ròng khối
            ngoại theo ngày (dùng vs_nn_flow).

        from_date/to_date: ngày ISO (mặc định 30 ngày gần nhất). pt_vol/pt_val là
        chân thỏa thuận; pt_pct là tỷ trọng giá trị thỏa thuận trong ngày.
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
        report_type: str = "equity",
        days: int | None = None,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Khuyến nghị và giá mục tiêu của CTCK, tách từ tiêu đề báo cáo. Dùng khi xem quan điểm phố
            (street views) về 1 mã hoặc toàn thị trường.

        Dùng khi: "CTCK nói gì về FPT", "giá mục tiêu HPG", triển vọng vĩ mô của CTCK
            (report_type='macro').
        Không dùng khi: cần số liệu BCTC (dùng financial_detail); cần tin tức (dùng news_symbol).
            Không có tool nào tên analyst_targets — chính là tool này.
        symbol: lọc 1 mã (bỏ qua để xem mới nhất toàn thị trường). Ratings lấy từ chữ tiêu đề
            (MUA/BÁN/NẮM GIỮ...), không phải feed consensus; lịch sử mỗi mã cho thấy nâng/hạ
            khuyến nghị. report_type: 'equity'
        (báo cáo theo mã) hoặc 'macro' (triển vọng vĩ mô của CTCK: GDP/CPI/lãi suất/FX/Fed;
        bộ lọc symbol không áp dụng).
        days: giữ báo cáo N ngày gần nhất theo ngày dd/mm/yyyy tách được
        (mặc định không lọc). Dòng không tách được ngày vẫn giữ và đánh
        date_uncertain:true — coi ngày của chúng là không chắc.
        Chỉ có trang danh sách mới nhất (nguồn không phân trang).
        Chỉ tiêu đề — không thân bài. url mỗi dòng là trang báo cáo: tóm tắt HTML sau
        'Tải về' (~500-700 ký tự) mang upside, doanh thu, lợi nhuận, EPS, P/E, P/B, cổ tức;
        'Nguồn:' cho biết tên CTCK. File 'edocs/...pdf' thường lỗi khi trích text (font
        Vietstock) — dùng tóm tắt HTML.
        """
        if ctx is not None:
            await ctx.log("info", f"analyst_consensus {symbol} {report_type} d{days}")
        days_n: int | None = None
        if days is not None:
            try:
                days_n = max(int(days), 1)
            except (TypeError, ValueError):
                days_n = None
        kind = (report_type or "equity").strip().lower()
        if kind not in ("equity", "macro"):
            return make_envelope(
                {"tool": "analyst_consensus"},
                source="unavailable",
                warnings=[f"unknown report_type {report_type!r} (equity|macro)"],
                availability="unavailable",
            )
        warn: list[str] = []
        try:
            reports = await run_blocking(
                functools.partial(pub_p.analyst_reports, max(int(limit) * 2, 10), kind),
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
        cutoff: str | None = None
        if days_n is not None:
            import datetime
            from zoneinfo import ZoneInfo

            try:
                today = datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
            except Exception:
                today = datetime.date.today()
            cut = today - datetime.timedelta(days=days_n)
            cutoff = cut.isoformat()
            kept: list[dict[str, Any]] = []
            undated = 0
            for r in rows:
                d = _parse_report_date(r.get("date"))
                if d is None:
                    undated += 1
                    row = dict(r)
                    row["date_uncertain"] = True
                    kept.append(row)
                elif d >= cut:
                    kept.append(r)
            rows = kept
            if undated:
                warn.append(
                    f"{undated} row(s) have no parsed date and are kept with "
                    "date_uncertain:true — treat their dates as uncertain"
                )
        if kind == "macro":
            if symbol:
                warn.append("symbol filter ignored for macro reports (no ticker)")
            if rows and not any(r.get("date") for r in rows):
                warn.append(
                    "no dated CTCK macro reports on listing — section pointers only; "
                    "use vs_indicator_data for hard macro data"
                )
        elif symbol:
            want = symbol.strip().upper()
            rows = [r for r in rows if (r.get("symbol") or "").upper() == want]
        return make_envelope(
            {
                "symbol": (symbol or "").upper(),
                "report_type": kind,
                "reports": rows[: max(int(limit), 1)],
                "days": days_n,
                "cutoff": cutoff,
            },
            source="vietstock-scrape",
            warnings=warn,
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
        is (futures-spot)/spot in basis points. Futures leg prefers the latest
        trade, falling back to the last 15m ohlc bar (trades/latest is often
        empty); spot accepts raw or normalized candle keys.
        """
        import datetime

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
            first = trades[0]
            nested = first.get("trades")
            cand = (
                nested[-1]
                if isinstance(nested, list) and nested and isinstance(nested[-1], dict)
                else first
            )
            for key in (
                "price",
                "matchPrice",
                "match_price",
                "close",
                "Close",
                "c",
                "CLOSE",
                "last",
                "Last",
            ):
                fut = _fnum(cand.get(key))
                if fut is not None:
                    break
        spot = None
        closes = [
            _fnum(r.get(k))
            for r in spot_rows
            if isinstance(r, dict)
            for k in ("close", "Close", "c", "CLOSE")
            if _fnum(r.get(k)) is not None
        ]
        if closes:
            spot = closes[-1]
        if fut is None:
            try:
                week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
                bars = await run_blocking(
                    functools.partial(
                        dnse_p.ohlc_history, "VN30F1M", "derivative", 15, week_ago, 500
                    ),
                    "futures_basis",
                    timeout_secs=60.0,
                )
                if bars and isinstance(bars[-1], dict):
                    fut = _fnum(bars[-1].get("c"))
            except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
                fut = None
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
    async def planned_targets(
        symbol: str, years: int = 3, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Business-plan targets (CTKH: planned revenue/profit by year). Use as expectation anchor.

        years: latest N plan years (unit VND billions). Browser-session replay
        (HAR/env seed); reports unavailable while the gate rejects — mirror +
        analyst_consensus cover expectations meanwhile.
        """
        if ctx is not None:
            await ctx.log("info", f"planned_targets {symbol}")
        try:
            data = await run_blocking(
                functools.partial(vs_p.planned_targets, symbol, max(int(years), 1)),
                "planned_targets",
                timeout_secs=60.0,
            )
        except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as exc:
            return make_envelope(
                {"tool": "planned_targets"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        return make_envelope(data, source="vietstock")

    @server.tool(annotations=READ_ONLY)
    async def financial_detail(
        symbol: str,
        statement: str = "KQKD",
        periods_n: int = 4,
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """BCTC chi tiết đầy đủ, từng dòng mỗi kỳ. Dùng khi đọc sâu BCTC (soi từng chỉ tiêu).

        Dùng khi: phân tích forensic, kiểm tra dòng tiền/thuế/phải thu chi tiết.
        Không dùng khi: chỉ cần đọc nhanh (dùng financial_statements — nhẹ hơn, không cần JWT); cần
            BCTC mirror khi thiếu JWT (dùng vs_financeinfo); cần điểm số gian lận/chất lượng lợi
            nhuận (dùng stock_forensic thay vì tự tính).

        statement: KQKD (kết quả kinh doanh), CDKT (cân đối), LCTT (lưu chuyển tiền —
        Vietstock trống norms phía nguồn nên rơi về vnstock), TM (thuyết minh),
        BCTT. periods_n: các kỳ gần nhất được phép (đơn vị tỷ đồng; chỉ kỳ
        IsShowData_Permission=True). Giá trị thật trên gói Standard qua phát lại
        phiên trình duyệt — dòng {norm_id, name, values[...]}; báo cáo không khả dụng
        khi cổng phiên từ chối.
        """
        if ctx is not None:
            await ctx.log("info", f"financial_detail {symbol} {statement}")
        try:
            data = await run_blocking(
                functools.partial(vs_p.financial_detail, symbol, statement, periods_n),
                "financial_detail",
                timeout_secs=90.0,
            )
        except ProviderBadData as exc:
            # Vietstock LCTT norms are empty upstream for all symbols —
            # route: Vietstock BCTC values first (same source), vnstock fallback
            if statement.strip().upper() == "LCTT" and "no norms" in str(exc):
                try:
                    data = await run_blocking(
                        functools.partial(vs_p.financial_lctt, symbol, 2),
                        "financial_detail_lctt_vs",
                        timeout_secs=90.0,
                    )
                    return make_envelope(data, source="vietstock")
                except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData):
                    pass
                try:
                    from opentrading_mcp.providers import vnstock as vn_p

                    fb = await run_blocking(
                        functools.partial(vn_p.cashflow, symbol, "quarter"),
                        "financial_detail_lctt_fb",
                        timeout_secs=60.0,
                    )
                    return make_envelope(
                        fb, source="vnstock",
                        warnings=["Vietstock LCTT empty upstream — vnstock fallback"],
                    )
                except (ProviderAuthMissing, ProviderUnavailable, ProviderBadData) as fbe:
                    return make_envelope(
                        {"tool": "financial_detail"},
                        source="unavailable",
                        warnings=[str(exc), str(fbe)],
                        availability="unavailable",
                    )
            return make_envelope(
                {"tool": "financial_detail"},
                source="unavailable",
                warnings=[str(exc)],
                availability="unavailable",
            )
        except (ProviderAuthMissing, ProviderUnavailable) as exc:
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
        {"name": "planned_targets"},
        {"name": "financial_detail"},
    ]
