"""Units of the numbers in price results, published as ``units`` in the envelope.

Upstreams disagree: vnstock candles (VCI/KBS history) give VN stock prices in
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

# vnstock quote_history (VCI → KBS; both legs return thousand dong, checked 22/10/2026):
# candles t/o/h/l/c/v; summary last/high/low.
_HISTORY = {"o, h, l, c, last, high, low": THOUSAND_DONG, "v": SHARES}
# vnstock equity_ohlcv / index_ohlcv bars: time/open/high/low/close/volume; summary last/high/low.
_BARS = {"open, high, low, close, last": THOUSAND_DONG, "volume": SHARES}
# vnstock price board rows.
_BOARD = {
    "ceiling_price, floor_price, reference_price, open_price, high_price, low_price, "
    "close_price, average_price, price_change, bid_price_N, ask_price_N": DONG,
    "volume_accumulated, bid_vol_N, ask_vol_N, foreign_buy_volume, foreign_sell_volume": SHARES,
    "total_value": "đồng",
    "percent_change": "%",
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
}


def with_units(tool: str, result: Any) -> Any:
    """`result` with its tool's units first, when it is an envelope and has none yet."""
    units = UNITS.get(tool)
    if not units or not isinstance(result, dict) or "data" not in result or UNITS_KEY in result:
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
