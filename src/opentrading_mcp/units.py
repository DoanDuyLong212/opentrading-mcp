"""Units of the numbers in price results, published as ``units`` in the envelope.

Upstreams disagree: vnstock candles (ssi/dnse history) give VN stock prices in
thousand dong (FPT 64.27 = 64,270 dong), while the vnstock price board gives
dong (56700). A client that puts both in one table without a unit wrote
"62,2 (đ)" for 62.2 thousand dong, a 1000x misreading (OpenTrading
BUG-OT-20261016-004). Each entry below was checked against real results of
that tool; tools whose units were not checked are left out rather than guessed.

``units`` maps field names (comma-separated) to their unit, in Vietnamese for
the model reading it. It is the first key of the envelope so a long result cut
in the middle by a client still shows it.
"""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.fastmcp import FastMCP

UNITS_KEY = "units"

THOUSAND_DONG = "nghìn đồng/cổ phiếu (64,27 = 64.270 đ)"
DONG = "đồng/cổ phiếu (56700 = 56,7 nghìn đồng)"
SHARES = "cổ phiếu"
POINTS = "điểm"

# vnstock quote_history (ssi → dnse; both legs return thousand dong, measured 2026-11-08):
# candles t/o/h/l/c/v; summary last/high/low.
_HISTORY = {"o, h, l, c, last, high, low": THOUSAND_DONG, "v": SHARES}
# vnstock equity_ohlcv / index_ohlcv bars: time/open/high/low/close/volume; summary last/high/low.
_BARS = {"open, high, low, close, last": THOUSAND_DONG, "volume": SHARES}
# vnstock price board rows.
_BOARD = {
    "ceiling_price, floor_price, reference_price, open_price, high_price, low_price, "
    "close_price, average_price, price_change, bid_price_N, ask_price_N": DONG,
    "volume_accumulated, bid_vol_N, ask_vol_N, foreign_buy_volume, foreign_sell_volume, "
    "foreign_room": SHARES,
    "total_value": "đồng",
    "percent_change": "%",
}

# vn_quote_history / market_candles_batch also serve index symbols, whose candles are
# index points, not thousand dong (VNINDEX 1760.63). Explicit list: stock codes such as
# VNM or VND also start with "VN", and VNI is a listed stock (checked against the listing).
INDEX_SYMBOLS = frozenset(
    "VNINDEX VN30 VN100 VNMID VNSML VNALL VNXALL VNX50 VNDIAMOND VNFINLEAD VNFINSELECT "
    "VNFIN VNMAT VNREAL VNUTI VNIT VNSI VNHEAL VNIND VNCONS VNCOND VNENE "
    "HNXINDEX HNX30 HNXUPCOMINDEX UPCOMINDEX".split()
)
_INDEX_HISTORY = {"o, h, l, c, last, high, low": POINTS, "v": SHARES}
_SCENARIO = {
    "last_close, shocked_price": THOUSAND_DONG,
    "pnl_per_1000_shares": "nghìn đồng cho 1000 cổ phiếu (-1062,5 = -1.062.500 đ)",
}
_INDEX_SCENARIO = {
    "last_close, shocked_price": POINTS,
    "pnl_per_1000_shares": "điểm x 1000 (chỉ số, không phải tiền)",
}

UNITS: dict[str, dict[str, str]] = {
    "vn_quote_history": _HISTORY,
    "market_candles_batch": _HISTORY,
    "vn_equity_ohlcv": _BARS,
    "vn_index_ohlcv": {"open, high, low, close, last": POINTS, "volume": SHARES},
    "vn_equity_quote_batch": _BOARD,
    "market_snapshot": _BOARD,
    "market_movers": _BOARD,
    "vn_company": {"target_price": "đồng/cổ phiếu"},
    "scenario_simulate": _SCENARIO,
    # Vietcombank board, checked 2026-11-09 (USD sell 25780; matches the bank's site).
    "vn_retail_fx": {
        "buy_cash, buy_transfer, sell": "đồng cho 1 đơn vị ngoại tệ (USD sell 25780 = 25.780 đ)"
    },
    # Yahoo index bars, checked 2026-11-09 (^GSPC 7376.86).
    "vn_global_index": {"open, high, low, close, last": POINTS},
    # #149: returns are dimensionless; percentages are per session or per window.
    "series_stats": {
        "mean_return_pct, stdev_return_pct": "%/phiên",
        "total_return_pct, relative_strength_pct": "% cả cửa sổ",
        "vol_ann_pct": "%/năm (đã năm hóa 252 phiên)",
        "rank": "hạng trong rổ (1 = tổng lợi nhuận cao nhất)",
    },
    # ---- #138: raw DNSE / Vietstock / board tools -------------------------------
    # DNSE futures/index bars are points and contracts, never dong; stock bars are
    # thousand dong (FPT 2026-11-02 c=50.2 = 50.200 đ, đo 2026-11-18). DNSE raw REST
    # prices are thousand dong + lots of 10 for stocks (dnse_board.PRICE/LOT,
    # measured 2026-11-09, khẳng định lại 2026-11-18); board rows are already dong.
    "dnse_ohlc_history": {
        "o, h, l, c, last, high, low": (
            "điểm chỉ số (futures/index) — không phải đồng; cổ phiếu (bar_type=stock): nghìn đồng"
        ),
        "v": (
            "hợp đồng (bar_type=derivative); cổ phiếu (bar_type=stock, "
            "FPT v=12.293.400 ≈ KLGD ngày)"
        ),
    },
    # Raw /trades/latest body, one instrument class per symbol: mixed by design.
    # Identity re-checked 2026-11-18: FPT lots 939.890 x matchPrice 47.05kđ x 10
    # = 444,945 tỷ đ = grossTradeAmount 444.94512.
    "dnse_latest_trade": {
        "matchPrice, openPrice, highestPrice, lowestPrice, avgPrice": (
            f"{THOUSAND_DONG}; futures: điểm (mixed — theo symbols)"
        ),
        "totalVolumeTraded": "lô 10 cổ phiếu (cổ phiếu); hợp đồng (futures) — mixed",
        "grossTradeAmount": "tỷ đồng (đo 2026-11-09, khẳng định lại 2026-11-18)",
    },
    # order_book() returns dong/shares for stocks and points/contracts for futures,
    # and states which one in `unit`.
    "dnse_orderbook": {
        "bids.price, asks.price, bids.volume, asks.volume": (
            "đồng + cổ phiếu (cổ phiếu); điểm + hợp đồng (futures) — đọc `unit` trong data"
        ),
    },
    "dnse_foreign_flow": {
        "flow.buy, flow.sell, flow.net": (
            "chưa xác minh: giá trị khối ngoại từ WS; REST /foreign trả rỗng 2026-11-18"
        ),
    },
    "dnse_ws_snapshot": {
        "ohlc.*.open, ohlc.*.high, ohlc.*.low, ohlc.*.close": "điểm (VN30F1M/index)",
        "ohlc.*.volume": "hợp đồng",
        "index.*.value, index.*.change, index.*.pct": "điểm chỉ số (pct: %)",
        "foreign.*.buy, foreign.*.sell, foreign.*.net": (
            "chưa xác minh (WS foreign amount; REST thay thế trả rỗng 2026-11-18)"
        ),
    },
    # getmarketprice serves indices/futures (points) and global commodities (USD);
    # no stock rows in any board type (checked 1/2/3, 2026-11-18: VNIndex 1716.44,
    # VN30F1M 1828.0, XAUUSDO 3789.62, CL 85.06).
    "vs_market_price": {
        "Price, Change": (
            "điểm với chỉ số/futures VN (VNIndex 1716.44); USD với XAUUSD/CL — mixed, đọc Code"
        ),
        "PerChange": "%",
    },
    "vs_trading_info": {
        "PriorClosePrice, CeilingPrice, FloorPrice": DONG,
        "EPS, BVPS": "đồng/cổ phiếu",
        "PE, PB": "lần (bội số)",
        "KLCPLH, KLCPNY": SHARES,
        "_note": (
            "giá/MarketCapital/TotalVal đều đồng (FPT 2026-11-18: Ceiling 51.800, "
            "Floor 45.150, Last 47.100, MarketCap 88,82 nghìn tỷ đ)"
        ),
    },
    "vs_overview_trading": {
        "ClosePrice, Change": DONG,
        "PerChange": "%",
        "_note": (
            "TotalVol = cổ phiếu, TotalVal/ForeignBuyVal/ForeignSellVal = đồng "
            "(FPT 2026-11-18: Close 47.100, TotalVal 452,01 tỷ, ForeignBuy 19,74 tỷ); "
            "TotalBuyTrade/SellTrade, BuyAvgTrade = chưa xác minh (trả 0)"
        ),
    },
    "breadth_scan": {
        "advancers, decliners, unchanged, ceiling, floor": "số mã",
        "advancers_pct": "%",
    },
    # ---- #139: derived tools ----------------------------------------------------
    "valuation_run": {
        "price": DONG,
        "eps, bvps": "đồng/cổ phiếu (eps_unit do tool khai báo unverified)",
        "per, pb": "lần (bội số)",
    },
    "stock_overview": {
        "trading.PriorClosePrice, trading.CeilingPrice, trading.FloorPrice": DONG,
        "trading.EPS, trading.BVPS": "đồng/cổ phiếu",
        "trading.PE, trading.PB": "lần (bội số)",
        "company.target_price": "đồng/cổ phiếu",
    },
    # Item ids come from vs_ratios.UNIT_FIELDS, which carries the unit per item.
    "peer_compare": {
        "trailing_eps, book_value_per_share_bvps": "đồng/cổ phiếu",
        "p_e, p_b": "lần (bội số cuối kỳ báo cáo)",
        "roe, roa, net_profit_margin, gross_profit_margin": "%",
    },
    "signals_technical": {
        "last, support, resistance, sma*, ema*, boll_upper, boll_lower": (
            "nghìn đồng/cp với cổ phiếu; điểm với chỉ số — cùng đơn vị nến vào"
        ),
        "rs_vs_bench, pos_52w": "%",
        "_note": "rsi/macd/adx không đơn vị; ichimoku/swings/fib là mức giá cùng đơn vị `last`",
    },
    "stock_screener": {
        "pe": "lần (P/E cuối kỳ báo cáo, không phải hôm nay)",
        "roe": "%",
        "_note": "market_cap: nguồn chưa xác minh đơn vị/thời điểm → không trả",
    },
    # Vietstock foreign chart: BuyVol/SellVol shares; BuyVal/SellVal billion dong
    # (46,533,428 shares / 1813.559809 = 38,970 dong per share, sample 2026-10-06).
    "money_flow": {
        "flow.*.BuyVol, flow.*.SellVol": SHARES,
        "flow.*.BuyVal, flow.*.SellVal": "tỷ đồng (1813.56 = 1.813,56 tỷ)",
        "_note": "nhánh dnse-ws chỉ phủ VN30F1M futures; amount ở nhánh đó chưa xác minh",
    },
    "quant_backtest": {
        "gross_return, net_return, benchmark_return, max_drawdown": "phân số (0.05 = 5%)",
        "equity_curve.*.value": "chỉ số chuẩn hóa (100 = đầu kỳ), không phải đồng",
    },
    "quant_risk": {
        "sharpe_proxy": "tỷ lệ (không đơn vị)",
        "max_drawdown, win_rate": "phân số (0.05 = 5%)",
    },
    "quant_factors": {
        "momentum_20d_pct, vol_20d_ann_pct, max_dd_20d_pct, max_dd_full_pct": "%",
    },
    "block_trades": {
        "close": DONG,
        "mt_val, pt_val": "đồng (50.930.200.000 = 50,93 tỷ)",
        "mt_vol, pt_vol": SHARES,
        "pt_pct": "%",
    },
    "analyst_consensus": {
        "target": "đồng/cổ phiếu (đọc từ tiêu đề 'giá mục tiêu'; chưa xác minh bằng mẫu)",
    },
    "dividends_splits": {
        "value_per_share": "đồng/cổ phiếu (region=vn); USD/cổ phiếu (region=world)",
        "exercise_ratio": "tỷ lệ (0.1 = 10 cp mới/100 cp)",
    },
}


def _units_for(tool: str, result: dict[str, Any]) -> dict[str, str] | None:
    """The tool's units, with index candles labelled as points."""
    units = UNITS.get(tool)
    data = result.get("data")
    if not units or not isinstance(data, dict):
        return units
    if tool in ("vn_quote_history", "scenario_simulate"):
        if str(data.get("symbol", "")).upper() in INDEX_SYMBOLS:
            return _INDEX_HISTORY if tool == "vn_quote_history" else _INDEX_SCENARIO
    elif tool == "market_candles_batch":
        symbols = [
            str(s.get("symbol", "")).upper()
            for s in data.get("series") or []
            if isinstance(s, dict)
        ]
        indices = [s for s in symbols if s in INDEX_SYMBOLS]
        if indices and len(indices) == len(symbols):
            return _INDEX_HISTORY
        if indices:
            price = f"{THOUSAND_DONG}; chỉ số ({', '.join(indices)}): {POINTS}"
            return {**units, "o, h, l, c, last, high, low": price}
    return units


def with_units(tool: str, result: Any) -> Any:
    """`result` with its tool's units first, when it is an envelope and has none yet."""
    if not isinstance(result, dict) or "data" not in result or UNITS_KEY in result:
        return result
    units = _units_for(tool, result)
    if not units:
        return result
    return {UNITS_KEY: dict(units), **result}


def apply_units(server: FastMCP) -> None:
    """Wrap each registered tool listed in UNITS so its envelope carries ``units``.

    Applied after registration, around cached and fresh results alike, so a
    cache entry stored before this change still gets its units.
    """
    for tool in server._tool_manager.list_tools():
        if tool.name not in UNITS:
            continue
        fn = tool.fn
        name = tool.name
        if tool.is_async:

            @functools.wraps(fn)
            async def wrapped_async(
                *args: Any, __fn: Any = fn, __name: str = name, **kwargs: Any
            ) -> Any:
                return with_units(__name, await __fn(*args, **kwargs))

            tool.fn = wrapped_async
        else:

            @functools.wraps(fn)
            def wrapped_sync(*args: Any, __fn: Any = fn, __name: str = name, **kwargs: Any) -> Any:
                return with_units(__name, __fn(*args, **kwargs))

            tool.fn = wrapped_sync
