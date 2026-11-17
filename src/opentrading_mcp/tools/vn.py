"""VN-direct tools: quotes, OHLCV, reference, fundamentals, retail gold/FX."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vn_public as vn_pub
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers import vs_ratios
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    CLOSE_KEYS,
    HIGH_KEYS,
    LOW_KEYS,
    READ_ONLY,
    AnyContext,
    cache_lookup,
    cache_store,
    last_bar_time,
    pick_value,
    price_ttl,
    project_rows,
    run_blocking,
    summarize_rows,
)


def _na(tool: str, reason: str) -> dict[str, Any]:
    return make_envelope(
        {"tool": tool}, source="unavailable", warnings=[reason], availability="unavailable"
    )


# Backward-compat aliases: logic lives in shared.py, names kept for imports.
_CLOSE_KEYS = CLOSE_KEYS
_HIGH_KEYS = HIGH_KEYS
_LOW_KEYS = LOW_KEYS


def _project(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    return project_rows(rows, columns)


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    return pick_value(row, keys)


def _summarize(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_rows(symbol, rows, uppercase=True)


def register_vn_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_quote_history(
        symbol: str,
        days: int = 365,
        summary: bool = False,
        columns: list[str] | None = None,
        interval: str = "1D",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Nến 1 mã VN (1D/1W/1M), ssi trước dnse dự phòng. Dùng cho MỌI lịch sử giá của một mã.

        Dùng khi: "lịch sử giá FPT", "HPG có vượt đỉnh 20 phiên không", mọi tính toán cần chuỗi giá
            1 mã.
        Không dùng khi: cần nhiều mã cùng lúc (dùng market_candles_batch); cần nến phút/intraday
            (dùng vn_equity_ohlcv); cần giá khớp hiện tại (dùng vn_equity_quote_batch). Không có
            tool nào tên stock_history — chính là tool này.

        days: số nến yêu cầu (tối đa 365 nến; nến tuần/tháng bao phủ dài hơn theo hệ số).
        interval: '1D' (mặc định), '1W', '1M'. Nến 1W/1M mang ngày cuối kỳ (Chủ nhật cuối tuần,
        ngày cuối tháng) nên nến của kỳ hiện tại có thể ghi một ngày chưa tới; kỳ không có phiên
        (tuần Tết) bị bỏ. summary/columns: summary chỉ trả {count,last,high,low}; columns giữ
        trường nêu tên.
        """
        # v2: all units.INDEX_SYMBOLS codes ride the index group (#77).
        fp = f"v2|{symbol}|{days}|{summary}|{columns}|{interval}"
        hit = await cache_lookup("vn_quote_history", fp)
        if hit is not None:
            return hit
        if ctx is not None:
            await ctx.log("info", f"vn_quote_history {symbol} {days}d {interval}")
        try:
            candles = await run_blocking(
                functools.partial(vn_p.quote_history, symbol, days, interval),
                "vn_quote_history",
            )
            if summary:
                s = _summarize(symbol, candles)
                return await cache_store(
                    "vn_quote_history",
                    fp,
                    price_ttl(),
                    s,
                    source="vnstock",
                    data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_quote_history",
                fp,
                price_ttl(),
                {"symbol": symbol.upper(), "candles": _project(candles, columns)},
                source="vnstock",
                data_time=last_bar_time(candles),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_quote_history", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_equity_quote_batch(
        symbols: list[str],
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Bảng giá một lần cho NHIỀU mã. Dùng khi chụp nhanh giá khớp nhiều mã hoặc làm movers thủ
            công.

        Dùng khi: "giá 5 mã FPT HPG VCB MBB SSI", snapshot danh mục.
        Không dùng khi: cần lịch sử nến (dùng vn_quote_history cho 1 mã, market_candles_batch cho
            nhiều mã); cần top tăng/giảm đã xếp (dùng market_movers).

        summary/columns: summary chỉ trả {count,symbols}; columns giữ
        trường nêu tên từng báo giá.
        """
        # v2: rows from the project DNSE client (#84), ISO times, closed-market notes.
        fp = f"v2|{symbols}|{summary}|{columns}"
        hit = await cache_lookup("vn_equity_quote_batch", fp)
        if hit is not None:
            return hit
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols),
                "vn_equity_quote_batch",
            )
            quotes, missing = vn_p.split_batch(quotes)
            board_src, board_note = vn_p.board_source(quotes)
            notes = [f"batch partial: {len(missing)} symbols missing"] if missing else []
            if board_note:
                notes.append(board_note)
            if summary:
                # the `_missing` sentinel row is not a quote
                return await cache_store(
                    "vn_equity_quote_batch",
                    fp,
                    price_ttl(),
                    {
                        "count": len(quotes),
                        "symbols": [q.get("symbol") for q in quotes],
                        **({"missing": missing} if missing else {}),
                    },
                    source=board_src,
                    warnings=notes or None,
                )
            return await cache_store(
                "vn_equity_quote_batch",
                fp,
                price_ttl(),
                {"quotes": _project(quotes, columns), **({"missing": missing} if missing else {})},
                source=board_src,
                warnings=notes or None,
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_equity_quote_batch", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_listing(limit: int = 500) -> dict[str, Any]:
        """Full symbol list with company names. Use for universe and lookup.

        limit: max symbols returned (universe ~1500).
        """
        fp = f"{limit}"
        hit = await cache_lookup("vn_listing", fp)
        if hit is not None:
            return hit
        try:
            rows = await run_blocking(vn_p.listing_symbols, "vn_listing")
            return await cache_store(
                "vn_listing",
                fp,
                TTL_SECONDS["documents"],  # 24h: a just-listed symbol must resolve tomorrow
                {"count": len(rows), "symbols": rows[: max(int(limit), 1)]},
                source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_listing", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_fundamentals(
        symbol: str, period: str = "year", report_type: str = "ttm"
    ) -> dict[str, Any]:
        """Bảng chỉ số tài chính của 1 mã từ Vietstock financeinfo (P/E, P/B, EPS, BVPS, ROE,
            ROA, biên lợi nhuận). Định giá nhanh 1 mã.

        Dùng khi: "PE/PB/ROE của FPT", snapshot định giá nhanh.
        Không dùng khi: cần vùng giá trị hợp lý theo ensemble PER/PB (dùng valuation_run); cần đọc
            từng dòng BCTC (dùng financial_detail); cần BCTC không cần JWT (dùng
            financial_statements hoặc vs_financeinfo).

        period: 'year' hoặc 'quarter'. P/E, P/B tính theo giá ngày kết thúc kỳ, không phải hôm nay.
        periods trả theo thứ tự cũ→mới; cần kỳ mới nhất thì đọc latest_period, đừng lấy periods[0].
        report_type: giữ để tương thích, KHÔNG đổi số liệu (nguồn chỉ có một bảng; EPS là 4 quý
            gần nhất ở cả hai period) — giá trị khác 'ttm' chỉ kèm cảnh báo.
        """
        # v4: report_type left the cache key; it never changed the numbers (#85).
        # v5: periods run oldest→newest and latest_period is published (#140).
        fp = f"v5|{symbol}|{period}"
        warnings = (
            []
            if (report_type or "ttm").strip().lower() == "ttm"
            else [
                f"report_type={report_type!r} is ignored: the source has one ratio table "
                "(EPS is trailing four quarters in both periods)"
            ]
        )
        hit = await cache_lookup("vn_fundamentals", fp)
        if hit is not None:
            if warnings:
                hit = {**hit, "warnings": [*hit.get("warnings", []), *warnings]}
            return hit
        try:
            data = await run_blocking(
                functools.partial(vs_ratios.equity_ratios, symbol.upper(), period),
                "vn_fundamentals",
            )
            stored = await cache_store(
                "vn_fundamentals",
                fp,
                TTL_SECONDS["financeinfo"],  # quarterly ratios, not prices
                {
                    "symbol": symbol.upper(),
                    "period": period,
                    "periods": data.get("periods", []),
                    "latest_period": data.get("latest_period"),
                    "period_order": data.get("period_order", vs_ratios.PERIOD_ORDER),
                    "ratios": data.get("ratios", []),
                    "source": data.get("source", vs_ratios.SOURCE),
                },
                source="vietstock",
            )
            if warnings:
                stored = {**stored, "warnings": [*stored.get("warnings", []), *warnings]}
            return stored
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_fundamentals", str(exc))
        except Exception as exc:
            return _na("vn_fundamentals", f"upstream failed: {exc}")

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_gold(source: str = "auto") -> dict[str, Any]:
        """Giá vàng bán lẻ trong nước: vàng miếng SJC và nhẫn trơn, mua vào / bán ra. Dùng để tính
            chênh lệch vàng trong nước so với thế giới.

        source: 'auto' (mặc định: PNJ, lỗi thì BTMC), 'pnj' hoặc 'btmc'. Giá trị khác được coi
            là 'auto' và kèm cảnh báo.
        rows: {name, buy_price, sell_price, time} — ĐỒNG MỖI CHỈ (1 lượng = 10 chỉ; SJC bán
            13.750.000 đ/chỉ = 137,5 triệu đ/lượng). time: giờ niêm yết (PNJ không có).
        Không dùng khi: cần giá vàng thế giới (dùng vn_msn_fx_gold).
        """
        from opentrading_mcp.providers import vn_public as pub_p

        want = (source or "auto").strip().lower()
        warnings: list[str] = []
        if want not in ("auto", "pnj", "btmc"):
            warnings.append(f"source={source!r} is not served (auto|pnj|btmc): used auto")
            want = "auto"
        # v2: rows in dong per chi from PNJ or BTMC, newest quote per product (#126, #85)
        fp = f"v2|{want}"
        hit = await cache_lookup("vn_retail_gold", fp)
        if hit is not None:
            if warnings:
                hit = {**hit, "warnings": [*hit.get("warnings", []), *warnings]}
            return hit
        fetchers = {"pnj": (pub_p.pnj_gold, 12.0), "btmc": (pub_p.btmc_retail, 20.0)}
        order = ("pnj", "btmc") if want == "auto" else (want,)
        failed: list[str] = []
        for name in order:
            fetch, secs = fetchers[name]
            try:
                rows = await run_blocking(fetch, f"vn_retail_gold_{name}", timeout_secs=secs)
            except (ProviderUnavailable, ProviderBadData) as exc:
                failed.append(f"{name}: {exc}")
                continue
            except Exception as exc:
                failed.append(f"{name}: upstream failed: {exc}")
                continue
            if failed:
                warnings.append(f"served by {name}; failed first: " + "; ".join(failed))
            return await cache_store(
                "vn_retail_gold",
                fp,
                TTL_SECONDS["hour"],
                {"unit": "đồng/chỉ (1 lượng = 10 chỉ)", "source": name, "rows": rows},
                source=f"{name}-direct",
                warnings=warnings or None,
            )
        return _na("vn_retail_gold", "; ".join(failed))

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_fx() -> dict[str, Any]:
        """Tỷ giá Vietcombank mua/bán hôm nay. Dùng khi cần giá ngân hàng mua vào/bán ra ngoại tệ.

        Không dùng khi: cần chuỗi tỷ giá theo ngày (dùng vn_forex_ohlcv — tỷ giá liên ngân hàng).

        rows: mỗi ngoại tệ {currency_code, currency_name, buy_cash, buy_transfer, sell} — đồng
            cho 1 đơn vị ngoại tệ (USD sell 25780 = 25.780 đ); None khi ngân hàng không yết giá
            chiều đó. updated_at: thời điểm Vietcombank cập nhật bảng.
        """
        # v2: Vietcombank's public board replaces the gen-6 fhsc forex candles (#85).
        hit = await cache_lookup("vn_retail_fx", "v2")
        if hit is not None:
            return hit
        try:
            # Vietcombank asks for at most one request per 5 minutes: cache for an hour.
            data = await run_blocking(vn_pub.vcb_exchange_rates, "vn_retail_fx")
            return await cache_store(
                "vn_retail_fx",
                "v2",
                TTL_SECONDS["hour"],
                data,
                source="vietcombank",
                data_time=data.get("updated_at"),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_retail_fx", str(exc))
        except Exception as exc:
            return _na("vn_retail_fx", f"upstream failed: {exc}")

    return [
        {"name": "vn_quote_history"},
        {"name": "vn_equity_quote_batch"},
        {"name": "vn_listing"},
        {"name": "vn_fundamentals"},
        {"name": "vn_retail_gold"},
        {"name": "vn_retail_fx"},
    ]
