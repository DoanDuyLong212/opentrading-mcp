"""vn_screener: read-only access to the daily P(touch +20% in 20 sessions)
signals written by the mcp-opentrading-sub screener stage into the shared
Postgres (schema `predictions`, table `screener_signals_daily`).

Research-grade probabilities: mean forecast 6.79% vs realized 4.17% on the
chotted run — treat as a ranking screen, not trade triggers.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools import cycle_db as db
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext

TABLE = "predictions.screener_signals_daily"
SOURCE = "vn_screener"


async def _read(tool: str, sql: str, args: tuple, cols: list[str],
                filtered: bool = False) -> dict[str, Any]:
    try:
        return await db.read_rows(tool, SOURCE, sql, args, cols, filtered=filtered)
    except Exception as exc:  # any failure (missing table, unreachable) -> unavailable
        return make_envelope({}, source=SOURCE,
                             warnings=[f"screener store unavailable: {str(exc)[:180]}"])


def register_vn_screener_tools(server: FastMCP) -> list[dict[str, Any]]:
    src = SOURCE

    @server.tool(annotations=READ_ONLY)
    async def vn_screener_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Độ mới của bảng tín hiệu screener (số mã, ngày gần nhất). Dùng trước tiên."""
        sql = (f"SELECT COUNT(*)::int AS rows, COUNT(*) FILTER (WHERE p_touch20 IS NOT NULL)::int AS scored, "
               f"MAX(as_of_date)::text AS latest_as_of FROM {TABLE}")
        return await _read(src, sql, (), ["rows", "scored", "latest_as_of"])

    @server.tool(annotations=READ_ONLY)
    async def vn_screener_top(limit: int = 10,
                              min_probability: float | None = None,
                              ctx: AnyContext | None = None) -> dict[str, Any]:
        """Top mã có xác suất chạm +20% trong 20 phiên cao nhất (ngày gần nhất).

        limit: số mã tối đa (mặc định 10). min_probability: lọc dưới ngưỡng (0-1).
        Xác suất nghiên cứu: trung bình dự báo 6.8% vs thực tế 4.2% — màn hình sàng lọc, không phải khuyến nghị.
        """
        limit = max(1, min(int(limit), 50))
        where, args = ["p_touch20 IS NOT NULL"], []
        if min_probability is not None:
            where.append("p_touch20 >= %s")
            args.append(float(min_probability))
        sql = (f"SELECT symbol, as_of_date::text AS as_of_date, reference_close, p_touch20, "
               f"model_version, status FROM {TABLE} "
               f"WHERE as_of_date = (SELECT MAX(as_of_date) FROM {TABLE}) "
               f"AND {' AND '.join(where)} ORDER BY p_touch20 DESC LIMIT {limit}")
        cols = ["symbol", "as_of_date", "reference_close", "p_touch20", "model_version", "status"]
        return await _read(src, sql, tuple(args), cols, filtered=True)

    @server.tool(annotations=READ_ONLY)
    async def vn_screener_symbol(symbol: str,
                                 ctx: AnyContext | None = None) -> dict[str, Any]:
        """Lịch sử tín hiệu của một mã (toàn bộ ngày đã ghi — sparkline P(touch))."""
        sql = (f"SELECT as_of_date::text AS as_of_date, reference_close, p_touch20, "
               f"model_version, status FROM {TABLE} "
               f"WHERE symbol = %s ORDER BY as_of_date DESC LIMIT 90")
        return await _read(src, sql, (symbol.strip().upper(),),
                           ["as_of_date", "reference_close", "p_touch20", "model_version", "status"],
                           filtered=True)

    return [
        {"name": "vn_screener_check"},
        {"name": "vn_screener_top"},
        {"name": "vn_screener_symbol"},
    ]
