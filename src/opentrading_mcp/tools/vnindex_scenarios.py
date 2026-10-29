"""vnindex_scenarios: read-only access to the VNINDEX probabilistic scenarios
and downside-risk heads written by the mcp-opentrading-sub vnindex stage into
the shared Postgres (schema `predictions`, table `vnindex_scenarios_daily`).

The `scenarios`/`credibility` payloads are stored as-is from the locked
scenario_summary contract v1 — this tool passes them through without reshaping.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools import cycle_db as db
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext

TABLE = "predictions.vnindex_scenarios_daily"
SOURCE = "vnindex_scenarios"


async def _read(tool: str, sql: str, args: tuple, cols: list[str],
                filtered: bool = False) -> dict[str, Any]:
    try:
        return await db.read_rows(tool, SOURCE, sql, args, cols, filtered=filtered)
    except Exception as exc:  # any failure (missing table, unreachable) -> unavailable
        return make_envelope({}, source=SOURCE,
                             warnings=[f"vnindex store unavailable: {str(exc)[:180]}"])


def register_vnindex_scenarios_tools(server: FastMCP) -> list[dict[str, Any]]:
    src = SOURCE

    @server.tool(annotations=READ_ONLY)
    async def vnindex_scenarios_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Độ mới của bảng kịch bản VNINDEX (số khối kỳ hạn, ngày gần nhất). Dùng trước tiên."""
        sql = (f"SELECT COUNT(*)::int AS rows, COUNT(DISTINCT as_of_date)::int AS days, "
               f"MAX(as_of_date)::text AS latest_as_of FROM {TABLE}")
        return await _read(src, sql, (), ["rows", "days", "latest_as_of"])

    @server.tool(annotations=READ_ONLY)
    async def vnindex_scenarios_latest(asof: str | None = None,
                                       horizon: int | None = None,
                                       ctx: AnyContext | None = None) -> dict[str, Any]:
        """Kịch bản VNINDEX mới nhất: tăng/tích lũy/giảm + xác suất + vùng điểm có điều kiện
        + credibility ngoài mẫu. horizon: 10|20|40|60 (mặc định: tất cả)."""
        where, args = [], []
        if asof:
            where.append("as_of_date = %s")
            args.append(asof)
        else:
            where.append("as_of_date = (SELECT MAX(as_of_date) FROM " + TABLE + ")")
        if horizon is not None:
            where.append("horizon = %s")
            args.append(int(horizon))
        sql = (f"SELECT as_of_date::text AS as_of_date, close, horizon, model, scenarios, "
               f"credibility, markdown, selection_changed FROM {TABLE} "
               f"WHERE {' AND '.join(where)} ORDER BY horizon")
        return await _read(src, sql, tuple(args),
                           ["as_of_date", "close", "horizon", "model", "scenarios",
                            "credibility", "markdown", "selection_changed"], filtered=True)

    @server.tool(annotations=READ_ONLY)
    async def vnindex_scenarios_history(horizon: int = 20,
                                        days: int = 30,
                                        ctx: AnyContext | None = None) -> dict[str, Any]:
        """Chuỗi kịch bản theo ngày cho MỘT kỳ hạn (sparkline xác suất tăng/tích lũy/giảm)."""
        days = max(1, min(int(days), 180))
        sql = (f"SELECT as_of_date::text AS as_of_date, close, scenarios FROM {TABLE} "
               f"WHERE horizon = %s ORDER BY as_of_date DESC LIMIT %s")
        return await _read(src, sql, (int(horizon), days),
                           ["as_of_date", "close", "scenarios"], filtered=True)

    @server.tool(annotations=READ_ONLY)
    async def vnindex_risk_heads(asof: str | None = None,
                                 ctx: AnyContext | None = None) -> dict[str, Any]:
        """Cảnh báo rủi ro: P(chạm −5%/−10% sau 10/20 phiên) kèm baseline và credibility."""
        where, args = [], []
        if asof:
            where.append("as_of_date = %s")
            args.append(asof)
        else:
            where.append("as_of_date = (SELECT MAX(as_of_date) FROM " + TABLE + ")")
        sql = (f"SELECT as_of_date::text AS as_of_date, close, horizon, scenarios, credibility "
               f"FROM {TABLE} WHERE {' AND '.join(where)} AND horizon IN (10, 20) ORDER BY horizon")
        cols = ["as_of_date", "close", "horizon", "scenarios", "credibility"]
        return await _read(src, sql, tuple(args), cols, filtered=True)

    return [
        {"name": "vnindex_scenarios_check"},
        {"name": "vnindex_scenarios_latest"},
        {"name": "vnindex_scenarios_history"},
        {"name": "vnindex_risk_heads"},
    ]
