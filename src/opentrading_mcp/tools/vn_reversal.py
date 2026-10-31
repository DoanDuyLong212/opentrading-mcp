"""vn_reversal: read-only access to the daily DAY/DINH reversal signals
written by the `mcp-opentrading-sub` Stage D (reversal-signals v1) into the
shared Postgres (schema `predictions`, tables `reversal_signals_daily` /
`reversal_sector_daily`).

Model 4 — frozen configs audited 2026-10-30:
- DINH: barrier SELL rf/S1 tau=0.80  -> audit econ20 69.3%, 3/3 nam duong (PASS)
- DAY:  barrier BUY  logit/S2 tau=0.90 -> audit econ20 59.1% (WEAK_PASS — secondary)
- swing detector: chi dung cho dashboard nganh, khong phai lenh.

The writer is NOT this service — this module only reads. Missing schema/table
(pipeline not run yet) reads as "not seeded".
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools import cycle_db as db
from opentrading_mcp.tools.shared import READ_ONLY, AnyContext

SIG_TABLE = "predictions.reversal_signals_daily"
SEC_TABLE = "predictions.reversal_sector_daily"
SOURCE = "vn_reversal"


async def _read(tool: str, sql: str, args: tuple, cols: list[str],
                filtered: bool = False) -> dict[str, Any]:
    try:
        return await db.read_rows(tool, SOURCE, sql, args, cols, filtered=filtered)
    except Exception as exc:  # missing schema/table, unreachable -> unavailable
        return make_envelope({}, source=SOURCE,
                             warnings=[f"reversal store unavailable: {str(exc)[:180]}"])


def register_vn_reversal_tools(server: FastMCP) -> list[dict[str, Any]]:
    src = SOURCE

    @server.tool(annotations=READ_ONLY)
    async def vn_reversal_check(ctx: AnyContext | None = None) -> dict[str, Any]:
        """Độ mới của bảng tín hiệu ĐÁY/ĐỈNH (số mã, ngày gần nhất,
        model_version). Dùng trước tiên."""
        sql = (f"SELECT COUNT(*)::int AS rows, "
               f"COUNT(DISTINCT symbol)::int AS symbols, "
               f"MAX(as_of_date)::text AS latest_as_of, "
               f"COUNT(*) FILTER (WHERE signal = 'DINH')::int AS n_dinh, "
               f"COUNT(*) FILTER (WHERE signal = 'DAY')::int AS n_day, "
               f"MIN(model_version) AS model_version FROM {SIG_TABLE}")
        return await _read(src, sql, (),
                           ["rows", "symbols", "latest_as_of", "n_dinh", "n_day", "model_version"])

    @server.tool(annotations=READ_ONLY)
    async def vn_reversal_signals(asof: str | None = None,
                                  action: str | None = None,
                                  include_neutral: bool = False,
                                  ctx: AnyContext | None = None) -> dict[str, Any]:
        """Danh sách tín hiệu ĐÁY/ĐỈNH mới nhất cho từng cổ phiếu (+ VNINDEX).

        action: 'DINH' | 'DAY' | bỏ trống = cả hai.
        include_neutral: true để gồm cả mã trung tính (mặc định chỉ tín hiệu).
        Độ tin cậy: ĐỈNH đã audit (econ20 69%); ĐÁY là secondary (~59%, dùng quy mô nhỏ).
        Xem theo ngành: dùng vn_reversal_dashboard.
        """
        where, args = [], []
        if asof:
            where.append("as_of_date = %s")
            args.append(asof)
        else:
            where.append("as_of_date = (SELECT MAX(as_of_date) FROM " + SIG_TABLE + ")")
        if action:
            where.append("signal = %s")
            args.append(action.upper())
        elif not include_neutral:
            where.append("signal <> 'NEUTRAL'")
        sql = (f"SELECT symbol, signal, as_of_date::text AS as_of_date, close, "
               f"p_dinh_barrier, p_day_barrier, p_swing_day, p_swing_dinh, "
               f"rsi14, dist_sma50, dd20, ret5, model_version FROM {SIG_TABLE} "
               f"WHERE {' AND '.join(where)} "
               f"ORDER BY CASE signal WHEN 'DINH' THEN 0 WHEN 'DAY' THEN 1 ELSE 2 END, "
               f"p_dinh_barrier DESC LIMIT 200")
        cols = ["symbol", "signal", "as_of_date", "close", "p_dinh_barrier", "p_day_barrier",
                "p_swing_day", "p_swing_dinh", "rsi14", "dist_sma50", "dd20", "ret5", "model_version"]
        return await _read(src, sql, tuple(args), cols, filtered=bool(action))

    @server.tool(annotations=READ_ONLY)
    async def vn_reversal_dashboard(asof: str | None = None,
                                    ctx: AnyContext | None = None) -> dict[str, Any]:
        """Dashboard ngành: 15 rổ (theo cycle_stats: bank, securities, ..., vin) + 4 Họ
        (Vin/GELEX/FPT/Viettel) — số mã xác nhận đáy/đỉnh W5 gần nhất, số tín hiệu,
        ret5, breadth trên SMA50, leader mỗi rổ."""
        where, args = [], []
        if asof:
            where.append("as_of_date = %s")
            args.append(asof)
        else:
            where.append("as_of_date = (SELECT MAX(as_of_date) FROM " + SEC_TABLE + ")")
        sql = (f"SELECT basket, kind, as_of_date::text AS as_of_date, n_ma, "
               f"n_xn_day_5p, n_xn_dinh_5p, n_sig_dinh, n_sig_day, ret5_mean, "
               f"breadth_ma50, leader_symbol, model_version FROM {SEC_TABLE} "
               f"WHERE {' AND '.join(where)} "
               f"ORDER BY kind, n_xn_dinh_5p DESC, n_xn_day_5p DESC LIMIT 40")
        return await _read(src, sql, tuple(args),
                           ["basket", "kind", "as_of_date", "n_ma", "n_xn_day_5p", "n_xn_dinh_5p",
                            "n_sig_dinh", "n_sig_day", "ret5_mean", "breadth_ma50", "leader_symbol",
                            "model_version"])

    @server.tool(annotations=READ_ONLY)
    async def vn_reversal_history(symbol: str, days: int = 30,
                                  ctx: AnyContext | None = None) -> dict[str, Any]:
        """Chuỗi xác suất/tín hiệu theo ngày cho MỘT mã (sparkline N ngày gần nhất).

        symbol: mã cổ phiếu hoặc 'VNINDEX'. days: số điểm tối đa (mặc định 30, tối đa 365).
        """
        days = max(1, min(int(days), 365))
        sql = (f"SELECT symbol, as_of_date::text AS as_of_date, close, signal, "
               f"p_dinh_barrier, p_day_barrier, p_swing_day, p_swing_dinh FROM {SIG_TABLE} "
               f"WHERE symbol = %s ORDER BY as_of_date DESC LIMIT %s")
        return await _read(src, sql, (symbol, days),
                           ["symbol", "as_of_date", "close", "signal", "p_dinh_barrier",
                            "p_day_barrier", "p_swing_day", "p_swing_dinh"], filtered=True)

    return [
        {"name": "vn_reversal_check"},
        {"name": "vn_reversal_signals"},
        {"name": "vn_reversal_dashboard"},
        {"name": "vn_reversal_history"},
    ]
