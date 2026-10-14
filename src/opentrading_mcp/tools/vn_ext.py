"""VN extended tools: index/equity/futures/forex/crypto/global OHLCV, reference, company, MSN."""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.cache import TTL_SECONDS
from opentrading_mcp.providers import vnstock as vn_p
from opentrading_mcp.providers.errors import ProviderBadData, ProviderUnavailable
from opentrading_mcp.tools.shared import (
    CLOSE_KEYS,
    HIGH_KEYS,
    LOW_KEYS,
    READ_ONLY,
    cache_lookup,
    cache_store,
    last_bar_time,
    pick_value,
    price_ttl,
    project_rows,
    run_blocking,
    summarize_rows,
)
from opentrading_mcp.tools.vn import _na


async def _call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    return await run_blocking(functools.partial(fn, *args, **kwargs), tool, timeout_secs=60.0)


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


def register_vn_ext_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_ONLY)
    async def vn_index_ohlcv(
        symbol: str = "VNINDEX",
        count: int = 100,
        summary: bool = False,
        columns: list[str] | None = None,
        interval: str = "1D",
    ) -> dict[str, Any]:
        """Index bars for VN tickers. Use for index history and breadth.

        interval: bar size ('1D' daily; intraday like '1m'/'15m' where supported).
        summary/columns: summary returns {count,last,high,low} only; columns keeps named fields.
        """
        fp = f"{symbol}|{count}|{summary}|{columns}|{interval}"
        hit = await cache_lookup("vn_index_ohlcv", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("i", vn_p.index_ohlcv, symbol, count, interval)
            if summary:
                s = _summarize(symbol, rows)
                return await cache_store(
                    "vn_index_ohlcv",
                    f"{symbol}|{count}|{summary}|{columns}|{interval}",
                    price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_index_ohlcv",
                f"{symbol}|{count}|{summary}|{columns}|{interval}",
                price_ttl(),
                {"symbol": symbol.upper(), "bars": _project(rows, columns)},
                source="vnstock",
                data_time=last_bar_time(rows),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_index_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_equity_ohlcv(
        symbol: str,
        count: int = 100,
        summary: bool = False,
        columns: list[str] | None = None,
        interval: str = "1D",
    ) -> dict[str, Any]:
        """Nến qua Market API, thay thế quotes khi cần OHLCV. Dùng khi cần nến phút/intraday hoặc
            nguồn nến thứ hai để đối chiếu.

        Dùng khi: nến '15m'/'1m', đối chiếu chéo với vn_quote_history.
        Không dùng khi: nến ngày/tuần/tháng thông thường (ưu tiên vn_quote_history — có fallback
            VCI→KBS); cần nhiều mã (dùng market_candles_batch).

        interval: cỡ nến ('1D' ngày; intraday như '1m'/'15m' nếu nguồn hỗ trợ).
        summary/columns: summary chỉ trả {count,last,high,low}; columns giữ trường nêu tên.
        """
        fp = f"{symbol}|{count}|{summary}|{columns}|{interval}"
        hit = await cache_lookup("vn_equity_ohlcv", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("e", vn_p.equity_ohlcv, symbol, count, interval)
            if summary:
                s = _summarize(symbol, rows)
                return await cache_store(
                    "vn_equity_ohlcv", fp, price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_equity_ohlcv", fp, price_ttl(),
                {"symbol": symbol.upper(), "bars": _project(rows, columns)},
                source="vnstock",
                data_time=last_bar_time(rows),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_equity_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_futures_ohlcv(
        symbol: str = "VN30F1M",
        count: int = 100,
        summary: bool = False,
        columns: list[str] | None = None,
        interval: str = "1D",
    ) -> dict[str, Any]:
        """Futures bars. Use for derivatives backtest input.

        interval: bar size ('1D' daily; intraday like '1m'/'15m' where supported).
        summary/columns: summary returns {count,last,high,low} only; columns keeps named fields.
        """
        fp = f"{symbol}|{count}|{summary}|{columns}|{interval}"
        hit = await cache_lookup("vn_futures_ohlcv", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("f", vn_p.futures_ohlcv, symbol, count, interval)
            if summary:
                s = _summarize(symbol, rows)
                return await cache_store(
                    "vn_futures_ohlcv", fp, price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_futures_ohlcv", fp, price_ttl(),
                {"symbol": symbol.upper(), "bars": _project(rows, columns)},
                source="vnstock",
                data_time=last_bar_time(rows),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_futures_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_forex_ohlcv(
        pair: str = "USDVND",
        count: int = 30,
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """FX bars. Use for currency context.

        pair like 'USDVND'. summary/columns: summary returns {count,last,high,low}
        only; columns keeps named fields.
        """
        fp = f"{pair}|{count}|{summary}|{columns}"
        hit = await cache_lookup("vn_forex_ohlcv", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("f", vn_p.forex_ohlcv, pair, count)
            if summary:
                s = _summarize(pair, rows)
                return await cache_store(
                    "vn_forex_ohlcv", fp, price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_forex_ohlcv", fp, price_ttl(),
                {"pair": pair.upper(), "bars": _project(rows, columns)},
                source="vnstock",
                data_time=last_bar_time(rows),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_forex_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY, name="vn_crypto_ohlcv")
    async def vn_crypto_ohlcv(
        symbol: str = "BTCUSDT",
        count: int = 30,
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Crypto bars. Use for digital-asset regime reads.

        summary/columns: summary returns {count,last,high,low} only; columns keeps named fields.
        """
        fp = f"{symbol}|{count}|{summary}|{columns}"
        hit = await cache_lookup("vn_crypto_ohlcv", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("c", vn_p.crypto_ohlv, symbol, count)
            if summary:
                s = _summarize(symbol, rows)
                return await cache_store(
                    "vn_crypto_ohlcv", fp, price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_crypto_ohlcv", fp, price_ttl(),
                {"symbol": symbol.upper(), "bars": _project(rows, columns)},
                source="vnstock",
                data_time=last_bar_time(rows),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_crypto_ohlcv", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_global_index(
        symbol: str = "USA30",
        count: int = 30,
        summary: bool = False,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Global index bars. Use as yfinance fallback.

        Symbol spellings are aliased (Yahoo codes and names with spaces work too):
        S&P 500 = INX (SPX/GSPC/SP500), Dow Jones = USA30 (DJI/Dow),
        Nasdaq Composite = COMP (IXIC/NASDAQ),
        CAC 40 = PX1 (CAC/CAC40), FTSE 100 = UKX (FTSE/FTSE100), plus DAX,
        N225 (Nikkei), HSI (Hang Seng), 000001 (Shanghai), SENSEX, VNI.
        Nasdaq-100 (NDX) is NOT in this source — use yf_global_indices.
        summary/columns: summary returns {count,last,high,low} only; columns keeps named fields.
        """
        fp = f"{symbol}|{count}|{summary}|{columns}"
        hit = await cache_lookup("vn_global_index", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("g", vn_p.global_index, symbol, count)
            if summary:
                s = _summarize(symbol, rows)
                return await cache_store(
                    "vn_global_index", fp, price_ttl(),
                    s, source="vnstock", data_time=s.get("last_t"),
                )
            return await cache_store(
                "vn_global_index", fp, price_ttl(),
                {"symbol": symbol.upper(), "bars": _project(rows, columns)},
                source="vnstock",
                data_time=last_bar_time(rows),
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_global_index", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_reference(
        exchange: str = "HOSE", by: str = "exchange", key: str | None = None
    ) -> dict[str, Any]:
        """ICB reference by exchange, group or industry. Use for universe construction.

        by: 'exchange' (use exchange=HOSE/HNX/UPCOM), 'group' or 'industry'
        (use key=group/industry name).
        """
        fp = f"{exchange}|{by}|{key}"
        hit = await cache_lookup("vn_reference", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("r", vn_p.reference_equity, exchange, by, key)
            return await cache_store(
                "vn_reference", fp, TTL_SECONDS["categories"],
                {"exchange": exchange.upper(), "rows": rows}, source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_reference", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_company(symbol: str, detail: bool = False) -> dict[str, Any]:
        """Hồ sơ, cổ đông và ban lãnh đạo công ty. Dùng khi nghiên cứu doanh nghiệp.

        Dùng khi: "FPT làm gì, ai là cổ đông lớn".
        Không dùng khi: chỉ cần giá và bội số nhanh (dùng stock_overview — dossier gọn); cần
            tên/sàn/mô tả ngắn (dùng vs_company_info).

        detail: false chỉ trả hồ sơ; true thêm cổ đông và lãnh đạo (nặng hơn).
        """
        fp = f"{symbol}|{detail}"
        hit = await cache_lookup("vn_company", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("c", vn_p.company_info, symbol, detail)
            return await cache_store(
                "vn_company", fp, TTL_SECONDS["overview"],
                data, source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_company", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_msn_fx_gold(symbols: list[str] | None = None, days: int = 35) -> dict[str, Any]:
        """USDVND and XAUUSD via MSN. Use for gold-basis math.

        symbols: subset to fetch (default both); days: history depth.
        """
        fp = f"{symbols}|{days}"
        hit = await cache_lookup("vn_msn_fx_gold", fp)
        if hit is not None:
            return hit
        try:
            data = await _call("m", vn_p.msn_fx_gold, symbols, days)
            return await cache_store(
                "vn_msn_fx_gold", fp, price_ttl(),
                {"series": data}, source="msn",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_msn_fx_gold", str(exc))

    @server.tool(annotations=READ_ONLY)
    async def vn_trades(
        symbol: str,
        limit: int = 20,
        board: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Tick-level matched trades. Use for microstructure reads.

        board: board filter (default all boards). from_date/to_date: ISO dates
        bounding the trade window.
        """
        fp = f"{symbol}|{limit}|{board}|{from_date}|{to_date}"
        hit = await cache_lookup("vn_trades", fp)
        if hit is not None:
            return hit
        try:
            rows = await _call("t", vn_p.equity_trades, symbol, limit, board, from_date, to_date)
            return await cache_store(
                "vn_trades", fp, price_ttl(),
                {"symbol": symbol.upper(), "trades": rows}, source="vnstock",
            )
        except (ProviderUnavailable, ProviderBadData) as exc:
            return _na("vn_trades", str(exc))

    server.tool(name="vn_crypto_ohlv", annotations=READ_ONLY)(vn_crypto_ohlcv)

    return [
        {"name": "vn_index_ohlcv"},
        {"name": "vn_equity_ohlcv"},
        {"name": "vn_futures_ohlcv"},
        {"name": "vn_forex_ohlcv"},
        {"name": "vn_crypto_ohlcv"},
        {"name": "vn_crypto_ohlv"},
        {"name": "vn_global_index"},
        {"name": "vn_reference"},
        {"name": "vn_company"},
        {"name": "vn_msn_fx_gold"},
        {"name": "vn_trades"},
    ]
