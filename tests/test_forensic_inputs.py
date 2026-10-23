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
from typing import Any

import pytest

from opentrading_mcp.providers.errors import ProviderBadData
from opentrading_mcp.server import create_server, register_preset
from opentrading_mcp.tools import compute_financial as comp_fin

DETAIL = json.loads(
    (Path(__file__).parent / "fixtures" / "financial_detail_fpt_vcb_20261023.json").read_text(
        encoding="utf-8"
    )
)


def _install(monkeypatch, symbol: str) -> None:
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        statement = args[1]
        if statement == "LCTT":  # live: "vietstock no norms for FPT LCTT"
            raise ProviderBadData(f"vietstock no norms for {symbol} LCTT")
        return DETAIL[symbol][statement]

    monkeypatch.setattr(comp_fin, "_call", fake_call)


async def _forensic(symbol: str) -> dict[str, Any]:
    server = create_server("scan")
    register_preset(server, "scan")
    return await server._tool_manager.get_tool("stock_forensic").fn(symbol=symbol, detail=True)


def test_row_names_are_compared_without_numbering_or_trailer():
    assert comp_fin._row_name("III. Các khoản phải thu ngắn hạn") == "các khoản phải thu ngắn hạn"
    assert comp_fin._row_name("XIII. Lợi nhuận sau thuế (XI-XII)") == "lợi nhuận sau thuế"
    assert comp_fin._row_name("9. Chi phí bán hàng ") == "chi phí bán hàng"


async def test_fpt_inputs_are_single_lines(monkeypatch):
    _install(monkeypatch, "FPT")
    env = await _forensic("FPT")
    series = env["data"]["series"]
    assert series["revenue"] == [12480.0, 13789.0]
    assert series["net_income"] == [2477.0, 2570.0]
    assert series["receivables"] == [12348.0, 13501.0]  # not 25,163
    assert series["cash"] == [7994.0, 9065.0]  # not 10,098
    assert series["assets"] == [68586.0, 73734.0]


async def test_missing_cfo_leaves_tata_and_m_score_out(monkeypatch):
    _install(monkeypatch, "FPT")
    data = (await _forensic("FPT"))["data"]
    assert data["series"]["cfo"] == []
    assert data["tata"] is None
    assert data["m_score"] is None
    assert data["m_partial"] == ["tata"]
    assert data["f_score"].endswith("/6")  # the CFO items are not counted


async def test_bank_template_uses_bank_lines(monkeypatch):
    _install(monkeypatch, "VCB")
    data = (await _forensic("VCB"))["data"]
    series = data["series"]
    assert series["revenue"] == [17651.0, 19142.0]  # I. Thu nhập lãi thuần
    assert series["net_income"] == [9462.0, 14551.0]  # XIII. Lợi nhuận sau thuế
    assert series["assets"] == [2550963.0, 2657441.0]
    # debt / equity = TỔNG NỢ PHẢI TRẢ / VIII. Vốn và các quỹ, not the grand total
    debt_t, debt_p, eq_t, eq_p = 2408950.0, 2316932.0, 248491.0, 234031.0
    assert data["lvgi"] == pytest.approx(round((debt_t / eq_t) / (debt_p / eq_p), 4))
    # a bank has no receivables / current-asset lines: those ratios are missing, not 1.0
    assert series["receivables"] == []
    assert data["dsri"] is None and data["aqi"] is None
    assert set(data["m_partial"]) >= {"dsri", "aqi", "tata"}
    # "current ratio up" cannot be computed without current assets/liabilities:
    # left out of the F-Score, not counted as failed
    assert data["f_missing"] == ["current ratio up"]
    assert data["f_score"].endswith("/5")


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
