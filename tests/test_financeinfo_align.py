"""financeinfo values must be tied to their period (Value1 is the NEWEST period).

Fixture: FPT quarterly financeinfo as recorded 2026-10-23, when models read the
raw rows in header order and swapped quarters. financial_detail on the same day
gave net revenue (norm 2216, VND bn) Q3/2025 17205, Q4/2025 20225, Q1/2026
12480, Q2/2026 13789 — the expected values below match it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from opentrading_mcp.providers.errors import ProviderBadData
from opentrading_mcp.providers.vietstock import align_financeinfo

RAW = json.loads(
    (Path(__file__).parent / "fixtures" / "financeinfo_fpt_quarter.json").read_text(
        encoding="utf-8"
    )
)


def _row(data: dict[str, Any], statement: str, norm_id: int) -> dict[str, Any]:
    return next(r for r in data["statements"][statement] if r["norm_id"] == norm_id)


def test_values_follow_header_id_not_list_order():
    data, warnings = align_financeinfo(RAW)
    assert warnings == []
    revenue = _row(data, "Kết quả kinh doanh", 2216)
    assert revenue["name"] == "Doanh thu thuần"
    assert revenue["values"]["Q2/2026"] == 13788503461199.0
    assert revenue["values"]["Q1/2026"] == 12479997206775.0
    assert revenue["values"]["Q4/2025"] == 20225450357409.0
    assert revenue["values"]["Q3/2025"] == 17204521225302.0
    assert revenue["values"]["Q2/2025"] == 16624713040067.0


def test_periods_chronological_across_pages():
    data, _ = align_financeinfo(RAW)
    assert data["periods"] == [
        "Q1/2024", "Q2/2024", "Q3/2024", "Q4/2024", "Q1/2025",
        "Q2/2025", "Q3/2025", "Q4/2025", "Q1/2026", "Q2/2026",
    ]
    revenue = _row(data, "Kết quả kinh doanh", 2216)
    assert list(revenue["values"]) == data["periods"]
    # page 2 IDs restart at 5 (Row continues at 10): Value5 is its oldest, Q1/2024
    assert revenue["values"]["Q1/2024"] == 1005.0
    assert revenue["values"]["Q1/2025"] == 1001.0


def test_statement_alias_and_periods_n():
    data, warnings = align_financeinfo(RAW, statement="CDKT", periods_n=3)
    assert warnings == []
    assert list(data["statements"]) == ["Báo cáo tình hình tài chính"]
    assert data["periods"] == ["Q4/2025", "Q1/2026", "Q2/2026"]
    assets = _row(data, "Báo cáo tình hình tài chính", 2996)
    assert assets["values"] == {
        "Q4/2025": 88089621779862.0,
        "Q1/2026": 68586094785217.0,
        "Q2/2026": 73734163085489.0,
    }


def test_unknown_statement_warns_and_returns_all():
    data, warnings = align_financeinfo(RAW, statement="LCTT")
    assert len(data["statements"]) == 3
    assert warnings and "LCTT" in warnings[0]


def test_page_with_unmappable_headers_is_skipped():
    raw = copy.deepcopy(RAW)
    for h in raw["pages"][1][0]:
        h.pop("ID")
    data, warnings = align_financeinfo(raw)
    assert data["periods"][0] == "Q2/2025"
    assert warnings == ["page 2: period headers without unique IDs, skipped"]


def test_no_mappable_page_raises():
    with pytest.raises(ProviderBadData):
        align_financeinfo({"symbol": "FPT", "pages": [[[], {}]]})
