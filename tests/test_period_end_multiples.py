"""P/E, P/B của financial_ratios / peer_compare là bội số cuối kỳ, phải được gắn nhãn rõ.

Demo 24/10/2026: hỏi "P/E hiện tại", model gọi financial_ratios(set="p_e") và báo 15.91
(P/E tại ngày kết thúc FY2025) là P/E hiện tại, trong khi stock_overview trả PE 9.51 theo
giá hôm nay. Fixture: bảng chỉ số vnstock thật của FPT (ghi ngày 23/10/2026).
"""

from __future__ import annotations

from opentrading_mcp.tools import compute_financial as comp_fin
from tests.test_financial_ratios_table import _install, _tool

SUFFIX = comp_fin._PERIOD_END_SUFFIX


async def test_pe_rows_are_labelled_period_end_with_a_leading_note(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", set="p_e", period="year")
    data = env["data"]
    assert next(iter(data)) == "symbol" and list(data)[1:3] == ["period", "note"]
    assert "KHÔNG phải bội số hiện tại" in data["note"] and "stock_overview" in data["note"]
    (pe,) = data["ratios"]
    assert pe["item_id"] == "p_e" and pe["as_of"] == "period_end"
    assert pe["item"] == f"Chỉ số giá thị trường trên thu nhập (P/E){SUFFIX}"
    assert pe["values"]["2025"] == 15.91  # the number itself is unchanged
    assert env["availability"] != "partial"  # the note is not a warning


async def test_non_price_rows_carry_no_label_and_no_note(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", set="roe", period="year")
    assert "note" not in env["data"]
    assert all("as_of" not in r and SUFFIX not in r["item"] for r in env["data"]["ratios"])


async def test_set_filter_still_matches_the_original_item_text(monkeypatch):
    # labelling happens after the set filter, so "p/e" in the item name still selects it
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", set="(p/e)", period="year")
    assert [r["item_id"] for r in env["data"]["ratios"]] == ["p_e"]


async def test_all_price_items_are_labelled_in_the_full_table(monkeypatch):
    _install(monkeypatch, [])
    env = await _tool("financial_ratios")(symbol="FPT", period="year")
    labelled = {r["item_id"] for r in env["data"]["ratios"] if r.get("as_of") == "period_end"}
    assert labelled == {"p_e", "p_b"}  # the price items present in the recorded table


def test_every_price_based_item_is_labelled():
    for item_id in ("p_e", "p_b", "p_s", "ev_ebit", "ev_ebitda", "dividend_yield"):
        row = comp_fin._label_period_end({"item_id": item_id, "item": "X", "values": {}})
        assert row["as_of"] == "period_end" and row["item"] == f"X{SUFFIX}"
    for item_id in ("roe", "beta", "trailing_eps", "book_value_per_share_bvps"):
        row = {"item_id": item_id, "item": "X", "values": {}}
        assert comp_fin._label_period_end(row) is row


async def test_label_survives_a_cache_hit(monkeypatch):
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})
    calls: list[tuple[str, str]] = []
    _install(monkeypatch, calls)
    fn = _tool("financial_ratios")
    await fn(symbol="FPT", set="p_e", period="year")
    env = await fn(symbol="FPT", set="p_e", period="year")
    assert env["provenance"]["cached"] is True and calls == [("FPT", "year")]
    assert env["data"]["ratios"][0]["as_of"] == "period_end" and "note" in env["data"]


async def test_peer_compare_labels_multiples_and_adds_the_note(monkeypatch):
    _install(monkeypatch, [])
    fn = _tool("peer_compare")
    env = await fn(symbol="FPT", peers=["HPG"], metrics=["pe", "pb"])
    assert next(iter(env["data"])) == "note"
    assert all(r["valuation_as_of"] == "cuối kỳ 2025 (không phải hiện tại)"
               for r in env["data"]["rows"])
    env = await fn(symbol="FPT", peers=["HPG"], metrics=["roe"])
    assert "note" not in env["data"]
    assert all("valuation_as_of" not in r for r in env["data"]["rows"])
