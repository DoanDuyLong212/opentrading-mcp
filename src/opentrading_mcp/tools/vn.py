"""VN-direct tools: quotes, OHLCV, reference, fundamentals, retail gold/FX."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vnstock as vn_p
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
        """Nến 1 mã VN (1D/1W/1M), VCI trước KBS dự phòng. Dùng cho MỌI lịch sử giá của một mã.

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
        fp = f"{symbol}|{days}|{summary}|{columns}|{interval}"
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
                    "vn_quote_history", fp, price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
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
        fp = f"{symbols}|{summary}|{columns}"
        hit = await cache_lookup("vn_equity_quote_batch", fp)
        if hit is not None:
            return hit
        try:
            quotes = await run_blocking(
                functools.partial(vn_p.equity_quote_batch, symbols),
                "vn_equity_quote_batch",
            )
            quotes, missing = vn_p.split_batch(quotes)
            if summary:
                # the `_missing` sentinel row is not a quote
                return await cache_store(
                    "vn_equity_quote_batch", fp, price_ttl(),
                    {"count": len(quotes), "symbols": [q.get("symbol") for q in quotes],
                     **({"missing": missing} if missing else {})},
                    source="vnstock",
                    warnings=(
                        [f"batch partial: {len(missing)} symbols missing"] if missing else None
                    ),
                )
            return await cache_store(
                "vn_equity_quote_batch",
                fp,
                price_ttl(),
                {"quotes": _project(quotes, columns),
                 **({"missing": missing} if missing else {})},
                source="vnstock",
                warnings=[f"batch partial: {len(missing)} symbols missing"] if missing else None,
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
        """Chỉ số và BCTC qua vnstock Fundamental và Finance. Dùng khi định giá nhanh 1 mã.

        Dùng khi: "PE/PB/ROE của FPT", snapshot định giá nhanh.
        Không dùng khi: cần vùng giá trị hợp lý theo ensemble PER/PB (dùng valuation_run); cần đọc
            từng dòng BCTC (dùng financial_detail); cần BCTC không cần JWT (dùng
            financial_statements hoặc vs_financeinfo).

        period: 'year' hoặc 'quarter'. report_type: 'ttm' (12 tháng gần nhất) hoặc 'latest'.
        """
        fp = f"{symbol}|{period}|{report_type}"
        hit = await cache_lookup("vn_fundamentals", fp)
        if hit is not None:
            return hit
        try:
            from vnstock import Fundamental
        except ImportError:
            return _na("vn_fundamentals", "vnstock not installed")
        try:
            data = await run_blocking(
                functools.partial(
                    Fundamental().equity(symbol.upper()).ratio,
                    period=period,
                    report_type=report_type,
                ),
                "vn_fundamentals",
            )
            to_records = getattr(data, "to_dict", None)
            if callable(to_records):
                try:
                    ratios = to_records(orient="records")
                except Exception:
                    try:
                        ratios = to_records()
                    except Exception:
                        ratios = str(data)
            else:
                ratios = data
            return await cache_store(
                "vn_fundamentals",
                fp,
                TTL_SECONDS["financeinfo"],  # quarterly ratios, not prices
                {"symbol": symbol.upper(), "ratios": ratios},
                source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_fundamentals", str(exc))
        except Exception as exc:
            return _na("vn_fundamentals", f"upstream failed: {exc}")

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_gold(source: str = "btmc") -> dict[str, Any]:
        """SJC and ring gold buy/sell from BTMC retail. Use for local gold premium.

        source: retail source id (default 'btmc'). Direct BTMC https fetch
        first (15s); vnstock lib fallback (its http URL hangs without timeout).
        """
        fp = f"{source}"
        hit = await cache_lookup("vn_retail_gold", fp)
        if hit is not None:
            return hit
        if source.strip().lower() == "btmc":
            try:
                from opentrading_mcp.providers import vn_public as pub_p

                rows = await run_blocking(pub_p.btmc_gold, "vn_retail_gold", timeout_secs=20.0)
                keep = [r for r in rows if "SJC" in str(r) or "NHẪN" in str(r)]
                return await cache_store(
                    "vn_retail_gold", fp, TTL_SECONDS["hour"],
                    {"rows": keep or rows}, source="btmc-direct",
                )
            except (ProviderUnavailable, ProviderBadData):
                pass
        try:
            from vnstock import Retail
        except ImportError:
            return _na("vn_retail_gold", "vnstock not installed")
        try:
            frame = await run_blocking(
                functools.partial(Retail().gold, source=source), "vn_retail_gold",
                timeout_secs=30.0,
            )
            rows = frame.to_dict(orient="records")
            keep = [r for r in rows if "SJC" in str(r) or "NHẪN" in str(r)]
            return await cache_store(
                "vn_retail_gold", fp, TTL_SECONDS["hour"],
                {"rows": keep or rows}, source="vnstock-retail",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_retail_gold", str(exc))
        except Exception as exc:
            return _na("vn_retail_gold", f"upstream failed: {exc}")

    @server.tool(annotations=READ_ONLY)
    async def vn_retail_fx() -> dict[str, Any]:
        """VCB USD buy/sell rates. Use for currency conversion context."""
        hit = await cache_lookup("vn_retail_fx", "-")
        if hit is not None:
            return hit
        try:
            from vnstock import Retail
        except ImportError:
            return _na("vn_retail_fx", "vnstock not installed")
        try:
            frame = await run_blocking(Retail().exchange_rate, "vn_retail_fx")
            return await cache_store(
                "vn_retail_fx", "-", TTL_SECONDS["hour"],
                {"rows": frame.to_dict(orient="records")}, source="vnstock-retail",
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
