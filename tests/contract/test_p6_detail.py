"""P15 contract: financial_detail chain with browser-shaped object-array keys."""

from __future__ import annotations

from typing import Any


def test_financial_detail_chains_object_array(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    calls: list[str] = []

    def fake_post(path: str, data: dict[str, Any]) -> Any:
        calls.append(path)
        if "Norm" in path:
            return {"data": [{"ReportNormId": 2216, "ReportNormName": "DT thuần"}]}
        if "GetListReportData" in path:
            return {
                "data": [
                    {"ReportDataID": 11, "YearPeriod": 2026, "ReportTermID": 2,
                     "IsShowData_Permission": True},
                    {"ReportDataID": 12, "YearPeriod": 2026, "ReportTermID": 3,
                     "IsShowData_Permission": True},
                    {"ReportDataID": 13, "YearPeriod": 2026, "ReportTermID": 4,
                     "IsShowData_Permission": False},
                ]
            }
        if "DetailValue" in path:
            assert data["listReportDataIds[0][ReportDataID]"] == "11"
            assert data["listReportDataIds[1][YearPeriod]"] == "2026"
            return {"data": [{"ReportNormId": 2216, "Value1": 100.0, "Value2": 110.0}]}
        raise AssertionError(path)

    monkeypatch.setattr(vs_p, "_detail_session_post", fake_post)
    out = vs_p.financial_detail("FPT", statement="KQKD", periods_n=3)
    assert [c.split("/")[-1] for c in calls] == [
        "GetListReportNorm_KQKD_ByStockCode",
        "KQKD_GetListReportData",
        "GetReportDataDetailValue_KQKD_ByReportDataIds",
    ]
    assert out["periods"] == ["Q1/2026", "Q2/2026"]
    assert out["rows"][0]["values"] == [100.0, 110.0]
    assert out["rows"][0]["name"] == "DT thuần"
