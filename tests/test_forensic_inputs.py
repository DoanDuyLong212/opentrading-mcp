"""stock_forensic reads one statement line per input, on both templates.

Fixture: live financial_detail (Q1/2026, Q2/2026, VND bn) for FPT (general
template) and VCB (bank template). The old substring sums gave FPT receivables
25,163 (= 13,501 total + 10,851 + 811 sub-items) and cash 10,098 (many rows
containing "tiền "); on VCB "nợ phải trả" and "vốn chủ sở hữu" both picked up
"TỔNG NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ HỮU". LCTT detail is empty upstream, and TATA
was then computed as NI/TA as if CFO were 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opentrading_mcp.tools import compute_financial as comp_fin

DETAIL = json.loads(
    (Path(__file__).parent / "fixtures" / "financial_detail_fpt_vcb_20261023.json").read_text(
        encoding="utf-8"
    )
)


def test_row_names_are_compared_without_numbering_or_trailer():
    assert comp_fin._row_name("III. Các khoản phải thu ngắn hạn") == "các khoản phải thu ngắn hạn"
    assert comp_fin._row_name("XIII. Lợi nhuận sau thuế (XI-XII)") == "lợi nhuận sau thuế"
    assert comp_fin._row_name("9. Chi phí bán hàng ") == "chi phí bán hàng"


def test_fpt_recorded_quarter_inputs_remain_diagnostics_not_annual_scores():
    detail = DETAIL["FPT"]
    assert comp_fin._fd_line(detail["KQKD"], "revenue") == [12480.0, 13789.0]
    assert comp_fin._fd_line(detail["KQKD"], "net_income") == [2477.0, 2570.0]
    assert comp_fin._fd_line(detail["CDKT"], "receivables") == [12348.0, 13501.0]
    assert comp_fin._fd_line(detail["CDKT"], "cash") == [7994.0, 9065.0]
    assert comp_fin._fd_line(detail["CDKT"], "assets") == [68586.0, 73734.0]


def test_bank_recorded_quarter_total_lines_are_diagnostics():
    assert comp_fin._fd_line(DETAIL["VCB"]["KQKD"], "revenue") == [17651.0, 19142.0]
    assert comp_fin._fd_line(DETAIL["VCB"]["CDKT"], "assets") == [2550963.0, 2657441.0]
    assert comp_fin._fd_line(DETAIL["VCB"]["CDKT"], "receivables") == []


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("SSI", {"revenue": 4590, "gross": 4592, "net_income": 4585, "receivables": 4484,
                 "assets": 4476, "cash": 4774, "current_assets": 4480,
                 "current_liabilities": 4493, "liabilities": 4477, "equity": 4478}),
        ("BVH", {"revenue": 3204, "gross": 3205, "net_income": 3200, "receivables": 3104,
                 "assets": 3095, "cash": 3102, "current_assets": 3099,
                 "current_liabilities": 3113, "liabilities": 3096, "equity": 3097}),
    ],
)
def test_securities_and_insurance_templates_resolve_to_their_total_lines(symbol, expected):
    for line, norm_id in expected.items():
        statement = "KQKD" if line in ("revenue", "gross", "net_income") else "CDKT"
        rows = DETAIL[symbol][statement]["rows"]
        want = next(r["values"] for r in rows if r["norm_id"] == norm_id)
        assert comp_fin._fd_line(DETAIL[symbol][statement], line) == want, line
