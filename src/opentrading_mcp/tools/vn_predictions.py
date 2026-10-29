"""vn_predictions: read-only access to the daily 12-month distribution
forecasts written by the `mcp-opentrading-sub` pipeline (a separate GitHub
Actions backend) into the shared Postgres (schema `predictions`).

The writer is NOT this service — this module only reads. A missing schema or
table (pipeline not run yet) reads as "not seeded", mirroring cycle_db
semantics for empty tables.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools import cycle_db as db
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext

TABLE = "predictions.predictions_daily"
SOURCE = "vn_predictions"


async def _read(tool: str, sql: str, args: tuple, cols: list[str],
                filtered: bool = False) -> dict[str, Any]:
    try:
        return await db.read_rows(tool, SOURCE, sql, args, cols, filtered=filtered)
    except Exception as exc:  # any failure (missing schema, unreachable) -> unavailable
        return make_envelope({}, source=SOURCE,
                             warnings=[f"predictions store unavailable: {str(exc)[:180]}"])


def register_vn_predictions_tools(server: FastMCP) -> list[dict[str, Any]]:
    src = SOURCE

    @server.tool(annotations=READ_ONLY)
    async def vn_predictions_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Độ mới của bảng dự báo hàng ngày (số tài sản, ngày dự báo gần nhất). Dùng trước tiên."""
        sql = (f"SELECT COUNT(*)::int AS rows, COUNT(DISTINCT asset)::int AS assets, "
               f"MAX(as_of_date)::text AS latest_as_of FROM {TABLE}")
        return await _read(src, sql, (), ["rows", "assets", "latest_as_of"])

    @server.tool(annotations=READ_ONLY)
    async def vn_predictions_latest(asof: str | None = None,
                                    currency: str | None = None,
                                    asset: str | None = None,
                                    ctx: AnyContext | None = None) -> dict[str, Any]:
        """Bảng dự báo 12 tháng mới nhất (43 tài sản VND + đối chiếu USD).

        asof: 'YYYY-MM-DD' (mặc định: ngày gần nhất). currency: VND|USD.
        asset: lọc một tài sản/rổ (ví dụ 'Họ GELEX', 'Bitcoin').
        """
        where, args = [], []
        if asof:
            where.append("as_of_date = %s")
            args.append(asof)
        else:
            where.append("as_of_date = (SELECT MAX(as_of_date) FROM " + TABLE + ")")
        if currency:
            where.append("currency = %s")
            args.append(currency.upper())
        if asset:
            where.append("asset ILIKE %s")
            args.append(f"%{asset}%")
        sql = (f"SELECT asset, currency, as_of_date::text AS as_of_date, origin::text AS origin, "
               f"target::text AS target, p_profit, p_gain15, p_gain30, p_gain150, p_loss20, "
               f"median, q10, q90, name, model_version FROM {TABLE} "
               f"WHERE {' AND '.join(where)} ORDER BY currency, asset LIMIT 120")
        return await _read(src, sql, tuple(args),
                           ["asset", "currency", "as_of_date", "origin", "target", "p_profit",
                            "p_gain15", "p_gain30", "p_gain150", "p_loss20", "median", "q10",
                            "q90", "model_version"], filtered=bool(asset or currency))

    @server.tool(annotations=READ_ONLY)
    async def vn_predictions_sparkline(asset: str,
                                       currency: str = "VND",
                                       days: int = 30,
                                       ctx: AnyContext | None = None) -> dict[str, Any]:
        """Chuỗi biến động dự báo theo ngày cho MỘT tài sản (sparkline N ngày gần nhất).

        asset: tên chính xác như trong bảng (ví dụ 'Họ GELEX', 'Bitcoin', 'VN_banks').
        days: số điểm tối đa (mặc định 30).
        """
        days = max(1, min(int(days), 365))
        sql = (f"SELECT as_of_date::text AS as_of_date, p_profit, p_gain15, p_gain30, "
               f"p_gain150, p_loss20, median, name FROM {TABLE} "
               f"WHERE asset = %s AND currency = %s "
               f"ORDER BY as_of_date DESC LIMIT %s")
        return await _read(src, sql, (asset, currency.upper(), days),
                           ["as_of_date", "p_profit", "p_gain15", "p_gain30", "p_gain150",
                            "p_loss20", "median", "name"], filtered=True)

    return [
        {"name": "vn_predictions_check"},
        {"name": "vn_predictions_latest"},
        {"name": "vn_predictions_sparkline"},
    ]
