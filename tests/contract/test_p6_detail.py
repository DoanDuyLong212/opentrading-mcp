"""P11 contract: financial_detail provider chain (tool removed P12; provider dormant)."""

from __future__ import annotations

from typing import Any


def test_financial_detail_chains_three_calls(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    calls: list[str] = []

    def fake_post(path: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        calls.append(path)
        if "Norm" in path:
            return {"data": [{"ReportNormId": 2206, "ReportNormName": "DTBH"}]}
        if "GetListReportData" in path:
            return {"data": [{"ReportDataID": 11}, {"ReportDataID": 12}]}
        if "DetailValue" in path:
            assert payload["listReportDataIds"] == [11, 12]
            return {"data": [{"Name": "DTBH", "V1": 1.0, "V2": 2.0}]}
        raise AssertionError(path)

    monkeypatch.setattr(vs_p, "_post", fake_post)
    out = vs_p.financial_detail("FPT", statement="KQKD", periods_n=2)
    assert [c.split("/")[-1] for c in calls] == [
        "GetListReportNorm_KQKD_ByStockCode",
        "KQKD_GetListReportData",
        "GetReportDataDetailValue_KQKD_ByReportDataIds",
    ]
    assert out["periods"] == [11, 12]
    assert out["rows"][0]["Name"] == "DTBH"
