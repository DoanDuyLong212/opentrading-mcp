"""financial_detail giữ MỘT loại báo cáo khi kỳ chỉ có UnitedName (sửa lại #36).

Dữ liệu thật 24/10/2026 (server đã deploy #40): BVH CDKT trả tổng tài sản
[272801, 291911, 307488, 19367] với report_type {"UnitedId": null,
"consolidated": true}. Kỳ có UnitedName nhưng không có khóa UnitedId, nên bộ lọc
theo id của #40 không loại kỳ nào mà vẫn khẳng định "hợp nhất".
"""

from __future__ import annotations

from typing import Any

from opentrading_mcp.providers import vietstock as vs_p

# Tổng tài sản BVH theo kỳ (tỷ đồng), lấy từ kết quả live ở trên.
BVH_ASSETS = {(2025, 4): 272801.0, (2025, 5): 291911.0, (2026, 2): 307488.0, (2026, 3): 19367.0}


def _period(rid: int, year: int, term: int, name: str | None) -> dict[str, Any]:
    p = {"ReportDataID": rid, "YearPeriod": year, "ReportTermID": term,
         "IsShowData_Permission": True}
    if name is not None:
        p["UnitedName"] = name
    return p


def _detail(monkeypatch, periods: list[dict[str, Any]], statement: str = "CDKT"):
    seen: dict[str, Any] = {}

    def fake_post(path: str, data: dict[str, Any]) -> Any:
        if "Norm" in path:
            return {"data": [{"ReportNormId": 3095, "ReportNormName": "TỔNG CỘNG TÀI SẢN"}]}
        if "GetListReportData" in path:
            return {"data": periods}
        n = sum(1 for k in data if k.endswith("[ReportDataID]"))
        kept = [(data[f"listReportDataIds[{i}][YearPeriod]"],
                 data[f"listReportDataIds[{i}][ReportTermID]"]) for i in range(n)]
        seen["kept"] = kept
        row = {"ReportNormId": 3095}
        for i, (y, t) in enumerate(kept, start=1):
            row[f"Value{i}"] = BVH_ASSETS.get((int(y), int(t)), 100.0)
        return {"data": [row]}

    monkeypatch.setattr(vs_p, "_detail_session_post", fake_post)
    return vs_p.financial_detail("BVH", statement=statement, periods_n=4), seen


HN, ME = "BCTC hợp nhất soát xét", "BCTC công ty mẹ"


def test_name_only_periods_keep_consolidated_and_drop_parent(monkeypatch):
    periods = [_period(1, 2025, 4, HN), _period(2, 2025, 5, HN), _period(3, 2026, 2, HN),
               _period(4, 2026, 3, ME)]
    out, _ = _detail(monkeypatch, periods)
    assert out["periods"] == ["Q3/2025", "Q4/2025", "Q1/2026"]
    assert out["rows"][0]["values"] == [272801.0, 291911.0, 307488.0]
    assert out["report_type"]["consolidated"] is True
    assert out["report_type"]["basis"] == "UnitedName"
    assert out["report_type"]["periods"]["Q1/2026"] == HN
    assert any("Q2/2026" in w for w in out["warnings"])


def test_unknown_report_type_is_never_claimed_consolidated(monkeypatch):
    periods = [_period(i, y, t, None) for i, (y, t) in enumerate(BVH_ASSETS, start=1)]
    out, _ = _detail(monkeypatch, periods)
    assert out["report_type"]["consolidated"] is None
    assert out["report_type"]["basis"] is None
    joined = " ".join(out["warnings"])
    assert "no report type" in joined
    # phòng thủ theo dữ liệu: 307,488 -> 19,367 là x15.9 giữa hai quý liền kề
    assert "x15.9 between Q1/2026 and Q2/2026" in joined


def test_period_without_a_name_is_dropped_when_others_are_named(monkeypatch):
    periods = [_period(1, 2026, 2, HN), _period(2, 2026, 3, None)]
    out, _ = _detail(monkeypatch, periods)
    assert out["periods"] == ["Q1/2026"]
    assert any("dropped 1 period(s): Q2/2026" in w for w in out["warnings"])


def test_parent_only_symbol_is_labelled_parent(monkeypatch):
    periods = [_period(1, 2026, 2, ME), _period(2, 2026, 3, "Báo cáo tài chính riêng")]
    out, _ = _detail(monkeypatch, periods)
    assert out["periods"] == ["Q1/2026", "Q2/2026"]
    assert out["report_type"]["consolidated"] is False


def test_duplicate_period_keeps_the_last_listed(monkeypatch):
    periods = [_period(1, 2026, 2, "BCTC hợp nhất soát xét"),
               _period(2, 2026, 2, "BCTC hợp nhất kiểm toán")]
    out, seen = _detail(monkeypatch, periods)
    assert out["periods"] == ["Q1/2026"] and seen["kept"] == [("2026", "2")]
    assert out["report_type"]["periods"]["Q1/2026"] == "BCTC hợp nhất kiểm toán"
    assert any("duplicate period" in w for w in out["warnings"])


def test_same_period_in_two_report_types_keeps_consolidated(monkeypatch):
    # scope by type BEFORE dedupe: a parent entry listed last must not win the period
    periods = [_period(1, 2026, 2, HN), _period(2, 2026, 2, ME)]
    out, seen = _detail(monkeypatch, periods)
    assert seen["kept"] == [("2026", "2")]
    assert out["report_type"]["periods"]["Q1/2026"] == HN
    assert out["report_type"]["consolidated"] is True


def test_periods_n_counts_after_dropping_other_report_types(monkeypatch):
    # upstream lists every period (UnitedId -1, Time_ASC): truncating after the scope
    # drop still returns periods_n comparable periods when older ones exist
    periods = [_period(i, 2025, t, HN) for i, t in enumerate((2, 3, 4, 5), start=1)]
    periods += [_period(5, 2026, 2, HN), _period(6, 2026, 3, ME)]
    out, _ = _detail(monkeypatch, periods)
    assert out["periods"] == ["Q2/2025", "Q3/2025", "Q4/2025", "Q1/2026"]


async def test_stock_forensic_forwards_annual_scope_diagnostics(monkeypatch):
    from opentrading_mcp.server import create_server, register_preset
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool, fn, *args, **kwargs):
        return {"symbol": "BVH", "records": [], "diagnostics": [{"scope": "unknown"}],
                "rejected": [{"reason": "unknown report scope"}]}

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    env = await server._tool_manager.get_tool("stock_forensic").fn(symbol="BVH", detail=True)
    assert "unknown report scope" in env["warnings"]
    assert env["availability"] == "partial"
    assert env["data"]["diagnostics"] == [{"scope": "unknown"}]
