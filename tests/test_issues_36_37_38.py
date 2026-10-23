"""Regression tests for GitHub issues #36, #37, #38.

#36 financial_detail trộn báo cáo hợp nhất / công ty mẹ giữa các kỳ.
#37 financial_lctt thiếu kỳ full-year (term 1) và 9 tháng (term 12); label
    term 9 sai ("NAM" thay vì "6T"); sort theo term id không theo thời gian.
#38 DNSE WS foreign flow (chỉ VN30F1M) bị gắn vào mọi index snapshot nên
    dnse_foreign_flow / money_flow trình bày flow futures như flow toàn thị trường.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Issue #37 — LCTT full terms, đúng label, đúng thứ tự thời gian
# ---------------------------------------------------------------------------


def test_build_list_params_full_includes_terms_1_and_12():
    from opentrading_mcp.providers import vietstock as vs_p

    params = vs_p.build_list_params("FPT", years=1, full=True)
    tids = {p["ReportTermId"] for p in params}
    assert tids == {1, 2, 3, 4, 5, 9, 12}


def test_lctt_requests_full_terms_and_orders_chronologically(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    captured: dict[str, Any] = {}

    def fake_norms(_statement: int) -> list[dict[str, Any]]:
        return [
            {"ReportNormID": -1, "Name": "I. Lưu chuyển tiền tệ hoạt động - Phương pháp gián tiếp"},
            {"ReportNormID": 101, "Name": "Dòng tiền thuần từ hoạt động kinh doanh"},
        ]

    def fake_post_json(path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
        captured["path"] = path
        captured["params"] = payload["ListParams"]
        rows = []
        # Thứ tự trả về cố tình xáo trộn để bắt lỗi sort theo term id.
        for yr, tid, val in [(2026, 5, 4.0), (2026, 2, 1.0), (2026, 12, 3.0), (2026, 9, 2.0)]:
            rows.append(
                {"ReportNormId": 101, "YearPeriod": yr, "ReportTermID": tid, "Value": val * 1e9}
            )
        return {"data": rows}

    monkeypatch.setattr(vs_p, "financial_norms", fake_norms)
    monkeypatch.setattr(vs_p, "_post_json", fake_post_json)
    out = vs_p.financial_lctt("FPT", years=2)

    # 1) Request đủ 7 term (1 = full year, 12 = 9 tháng).
    tids = {p["ReportTermId"] for p in captured["params"]}
    assert tids == {1, 2, 3, 4, 5, 9, 12}

    # 2) Label đúng + thứ tự thời gian: Q1 (Mar) → 6T (Jun) → 9T (Sep) → Q4 (Dec).
    assert out["periods"] == ["Q1/2026", "6T/2026", "9T/2026", "Q4/2026"]

    # 3) Values khớp đúng kỳ theo thứ tự đã sắp.
    assert out["rows"][0]["values"] == [1.0, 2.0, 3.0, 4.0]


def test_lctt_full_year_term_labelled_nam_and_sorted_last(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    def fake_norms(_statement: int) -> list[dict[str, Any]]:
        return [
            {"ReportNormID": -1, "Name": "I. Lưu chuyển tiền tệ hoạt động - Phương pháp gián tiếp"},
            {"ReportNormID": 101, "Name": "Dòng tiền thuần từ hoạt động kinh doanh"},
        ]

    def fake_post_json(path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
        rows = [
            {"ReportNormId": 101, "YearPeriod": 2025, "ReportTermID": 1, "Value": 9.0 * 1e9},
            {"ReportNormId": 101, "YearPeriod": 2026, "ReportTermID": 2, "Value": 1.0 * 1e9},
        ]
        return {"data": rows}

    monkeypatch.setattr(vs_p, "financial_norms", fake_norms)
    monkeypatch.setattr(vs_p, "_post_json", fake_post_json)
    out = vs_p.financial_lctt("FPT", years=2)
    assert out["periods"] == ["NAM/2025", "Q1/2026"]
    assert out["rows"][0]["values"] == [9.0, 1.0]


# ---------------------------------------------------------------------------
# Issue #36 — financial_detail giữ một report type duy nhất
# ---------------------------------------------------------------------------


def _detail_env(monkeypatch, periods: list[dict[str, Any]], n_kept: int):
    from opentrading_mcp.providers import vietstock as vs_p

    def fake_post(path: str, data: dict[str, Any]) -> Any:
        if "Norm" in path:
            return {"data": [{"ReportNormId": 2216, "ReportNormName": "DT thuần"}]}
        if "GetListReportData" in path:
            return {"data": periods}
        if "DetailValue" in path:
            rows = []
            for i in range(1, n_kept + 1):
                rows.append({"ReportNormId": 2216, f"Value{i}": 100.0 + i})
            return {"data": rows}
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(vs_p, "_detail_session_post", fake_post)
    return vs_p.financial_detail("BVH", statement="KQKD", periods_n=4)


def test_detail_prefers_consolidated_when_named(monkeypatch):
    periods = [
        {"ReportDataID": 11, "YearPeriod": 2026, "ReportTermID": 2,
         "UnitedId": 2, "UnitedName": "BCTC hợp nhất kiểm toán", "IsShowData_Permission": True},
        {"ReportDataID": 12, "YearPeriod": 2026, "ReportTermID": 2,
         "UnitedId": 1, "UnitedName": "BCTC công ty mẹ", "IsShowData_Permission": True},
        {"ReportDataID": 13, "YearPeriod": 2026, "ReportTermID": 3,
         "UnitedId": 1, "UnitedName": "BCTC công ty mẹ", "IsShowData_Permission": True},
    ]
    out = _detail_env(monkeypatch, periods, n_kept=1)
    # Chỉ giữ loại hợp nhất; Q2 (chỉ có công ty mẹ) bị loại, không trộn.
    assert out["periods"] == ["Q1/2026"]
    assert out["report_type"]["UnitedId"] == 2
    assert out["report_type"]["consolidated"] is True
    # Kỳ bị loại phải được báo rõ, không im lặng.
    assert any("Q2/2026" in w for w in out.get("warnings", []))


def test_detail_without_names_falls_back_to_newest_type(monkeypatch):
    periods = [
        {"ReportDataID": 11, "YearPeriod": 2026, "ReportTermID": 2,
         "UnitedId": 2, "IsShowData_Permission": True},
        {"ReportDataID": 12, "YearPeriod": 2026, "ReportTermID": 2,
         "UnitedId": 1, "IsShowData_Permission": True},
        {"ReportDataID": 13, "YearPeriod": 2026, "ReportTermID": 3,
         "UnitedId": 1, "IsShowData_Permission": True},
    ]
    out = _detail_env(monkeypatch, periods, n_kept=2)
    # Không biết tên → dùng loại của kỳ mới nhất (Q2 → UnitedId 1), chuỗi liền mạch.
    assert out["periods"] == ["Q1/2026", "Q2/2026"]
    assert out["report_type"]["UnitedId"] == 1
    assert any("report type" in w.lower() or "unitedid" in w.lower()
               for w in out.get("warnings", []))


def test_detail_single_type_has_no_warning(monkeypatch):
    periods = [
        {"ReportDataID": 11, "YearPeriod": 2026, "ReportTermID": 2,
         "UnitedId": 1, "IsShowData_Permission": True},
        {"ReportDataID": 13, "YearPeriod": 2026, "ReportTermID": 3,
         "UnitedId": 1, "IsShowData_Permission": True},
    ]
    out = _detail_env(monkeypatch, periods, n_kept=2)
    assert out["periods"] == ["Q1/2026", "Q2/2026"]
    assert out.get("warnings") in (None, [])


# ---------------------------------------------------------------------------
# Issue #38 — DNSE foreign flow phải nói rõ scope, không假冒 market-wide
# ---------------------------------------------------------------------------


def test_publish_dnse_snapshot_labels_foreign_scope_and_dedicated_key():
    from opentrading_mcp import loops
    from opentrading_mcp.providers import store

    state = {
        "ohlc": {"VN30F1M": {"symbol": "VN30F1M", "time": 1000.0}},
        "index": {"VNINDEX": {"indexName": "VNINDEX"}},
        "foreign": {"VN30F1M": {"buy": 5.0, "sell": 3.0, "net": 2.0}},
    }
    loops._publish_dnse_snapshot(state, 1000.0)

    idx = json.loads(store.cache_get("mcp:market:dnse_ws_snapshot:VNINDEX") or "{}")
    assert idx["foreign_scope"] == ["VN30F1M"]

    foreign = json.loads(store.cache_get("mcp:market:dnse_ws_foreign") or "{}")
    assert foreign["scope"] == ["VN30F1M"]
    assert foreign["flow"]["VN30F1M"]["net"] == 2.0


def test_ws_foreign_snapshot_reads_dedicated_key():
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers import store

    store.cache_set(
        "mcp:market:dnse_ws_foreign",
        {"scope": ["VN30F1M"], "flow": {"VN30F1M": {"net": 2.0}}},
        30,
    )
    out = dnse_p.ws_foreign_snapshot()
    assert out["flow"]["VN30F1M"]["net"] == 2.0
    assert out["scope"] == ["VN30F1M"]


async def test_dnse_foreign_flow_labels_scope_not_market_wide(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.server import register_all

    monkeypatch.setattr(
        dnse_p,
        "ws_foreign_snapshot",
        lambda: {"scope": ["VN30F1M"], "flow": {"VN30F1M": {"net": 2.0}}},
    )
    from opentrading_mcp.server import create_server

    server = create_server("all")
    register_all(server)
    tool = server._tool_manager.get_tool("dnse_foreign_flow")
    assert tool is not None
    env = await tool.fn()
    assert env["availability"] == "available"
    assert env["data"]["scope"] == ["VN30F1M"]
    assert env["data"]["flow"]["VN30F1M"]["net"] == 2.0
    # Không được ngụ ý toàn thị trường.
    assert "VN30F1M" in json.dumps(env["data"].get("note", "")) or \
        "market" not in json.dumps(env["data"]).lower()


async def test_money_flow_passes_through_foreign_scope(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_mod
    from opentrading_mcp.server import create_server, register_all

    def fake_snap(symbols):
        return {
            "VNINDEX": {
                "index": {"indexName": "VNINDEX"},
                "foreign": {"VN30F1M": {"net": 2.0}},
                "foreign_scope": ["VN30F1M"],
            }
        }

    monkeypatch.setattr(dnse_mod, "ws_snapshot", fake_snap)
    server = create_server("all")
    register_all(server)
    tool = server._tool_manager.get_tool("money_flow")
    assert tool is not None
    env = await tool.fn(symbols=["VNINDEX"])
    assert env["availability"] == "available"
    assert env["data"]["primary"] == "dnse-ws"
    # Snapshot phải mang nhãn scope để không bị đọc nhầm là flow toàn thị trường.
    assert env["data"]["snapshot"]["VNINDEX"]["foreign_scope"] == ["VN30F1M"]
