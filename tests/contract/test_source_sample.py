"""#141 harness: 40 sample slots, tool-side value read, no invented match.

The comparison against HOSE/HNX, IR reports, SBV and GSO happens at a desk with
credentials; these tests only hold the harness to its promises: 40 rows, every
tool registered, unreadable results reported (never guessed), and an empty
`match` column until a person fills it.
"""

from __future__ import annotations

import pytest

from opentrading_mcp.source_sample import (
    SAMPLES,
    Sample,
    _bar_on,
    _detail,
    _fx_leg,
    _last_bar,
    _last_point,
    _sbv,
    _statement,
    collect,
    render_markdown,
)

BY_GROUP = {
    group: [s for s in SAMPLES if s.group == group]
    for group in ("statement", "price", "index", "macro")
}


def test_forty_samples_in_the_issue_groups() -> None:
    assert len(SAMPLES) == 40
    assert {group: len(rows) for group, rows in BY_GROUP.items()} == {
        "statement": 15,
        "price": 10,
        "index": 5,
        "macro": 10,
    }


def test_sample_ids_are_unique() -> None:
    ids = [sample.id for sample in SAMPLES]
    assert len(ids) == len(set(ids))


def test_every_sample_tool_is_registered() -> None:
    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    registered = {tool["name"] for tool in register_all(server)}
    assert sorted({sample.tool for sample in SAMPLES} - registered) == []


def test_statement_reader_takes_the_newest_period() -> None:
    read = _statement("KQKD", "Doanh thu")
    data = {
        "periods": ["Q1/2026", "Q2/2026"],
        "statements": {
            "KQKD": [
                {
                    "name": "Doanh thu thuần",
                    "values": {"Q1/2026": 10, "Q2/2026": 12},
                    "unit": "đồng",
                }
            ]
        },
    }
    assert read(data) == {
        "name": "Doanh thu thuần",
        "period": "Q2/2026",
        "value": 12,
        "unit": "đồng",
    }
    with pytest.raises(LookupError):
        _statement("KQKD", "Lợi nhuận")(data)


def test_detail_reader_aligns_values_with_periods() -> None:
    read = _detail("Lưu chuyển tiền thuần từ hoạt động kinh doanh")
    data = {
        "statement": "LCTT",
        "periods": ["2024", "2025"],
        "rows": [{"name": "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "values": [5, 7]}],
    }
    assert read(data)["value"] == 7
    assert read(data)["period"] == "2025"
    assert read(data)["unit"].startswith("tỷ đồng")


def test_price_readers_report_a_missing_bar() -> None:
    data = {"candles": [{"t": "2026-07-22", "c": 100.0, "v": 10}]}
    assert _last_bar(data)["close"] == 100.0
    with pytest.raises(LookupError):
        _bar_on("2026-07-23")(data)


def test_sbv_and_fx_readers() -> None:
    rates = {
        "policy": [{"name": "Lãi suất tái cấp vốn", "value": "4,5%"}],
        "interbank": [{"name": "Qua đêm", "value": "5,1%"}],
        "as_of": "18/11/2026",
    }
    assert _sbv("policy", "tái cấp vốn")(rates)["value"] == "4,5%"
    assert _sbv("interbank", "")(rates)["name"] == "Qua đêm"
    points = {"points": [{"t": "2025", "v": 8.0}, {"t": "2024", "v": 7.0}, {"t": "2021", "v": 2.5}]}
    assert _last_point(points) == {"t": "2025", "v": 8.0}
    legs = {"series": [{"symbol": "USDVND", "unit": "VND/USD", "last": 26350}]}
    assert _fx_leg("USDVND")(legs)["last"] == 26350
    with pytest.raises(LookupError):
        _fx_leg("GOLD")(legs)


async def test_collect_reports_unavailable_instead_of_a_value() -> None:
    sample = Sample(
        id="x", group="price", tool="t", args={}, read=_last_bar, expect="e"
    )

    async def unavailable(**_: object) -> dict[str, object]:
        return {
            "data": {"tool": "t"},
            "provenance": {"as_of": "2026-11-18T00:00:00Z"},
            "warnings": ["no credentials"],
            "availability": "unavailable",
        }

    rows = await collect((sample,), {"t": unavailable})
    assert rows[0].status == "unavailable"
    assert rows[0].value is None
    assert "no credentials" in rows[0].note


async def test_collect_survives_a_crashing_tool_and_reads_a_real_value() -> None:
    def boom(**_):
        raise RuntimeError("upstream down")

    def ok(**_):
        return {
            "data": {"candles": [{"t": "2026-11-18", "c": 57400.0, "v": 1}]},
            "provenance": {"as_of": "2026-11-18T03:00:00Z"},
            "warnings": [],
            "availability": "available",
        }

    rows = await collect(
        (
            Sample(id="a", group="price", tool="boom", args={}, read=_last_bar, expect="e"),
            Sample(id="b", group="price", tool="ok", args={}, read=_last_bar, expect="e"),
        ),
        {"boom": boom, "ok": ok},
    )
    assert [row.status for row in rows] == ["error", "collected"]
    assert rows[1].value == {"date": "2026-11-18", "close": 57400.0, "volume": 1}


async def test_markdown_keeps_the_match_column_empty() -> None:
    def ok(**_):
        return {
            "data": {"candles": [{"t": "2026-11-18", "c": 1.0, "v": 1}]},
            "provenance": {"as_of": "2026-11-18T03:00:00Z"},
            "warnings": [],
            "availability": "available",
        }

    rows = await collect(
        (Sample(id="a", group="price", tool="ok", args={}, read=_last_bar, expect="e"),),
        {"ok": ok},
    )
    text = render_markdown(rows)
    assert "| primary source (URL + date) | match |" in text
    # Only the header cells exist: no row may claim a source or a match yet.
    row = next(line for line in text.splitlines() if line.startswith("| 1 |"))
    assert row.endswith("|  |  |  |")
