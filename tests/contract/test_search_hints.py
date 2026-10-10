"""Contract: every tool publishes a Vietnamese search hint in ``_meta``.

Harnesses that defer tools behind a search (OpenTrading tool_search, Claude Code
ToolSearch) match ``_meta["anthropic/searchHint"]``; descriptions stay English, so
without the hint a Vietnamese question ("co tuc FPT") matches nothing.
"""

from __future__ import annotations

from opentrading_mcp.hints import HINTS, MAX_HINT_CHARS, SEARCH_HINT_KEY
from opentrading_mcp.server import create_server, register_all


def _server():
    server = create_server()
    register_all(server)
    return server


async def test_every_tool_lists_a_search_hint():
    tools = await _server().list_tools()
    assert len(tools) >= 139
    missing = [t.name for t in tools if not (t.meta or {}).get(SEARCH_HINT_KEY)]
    assert missing == [], f"tools without a search hint: {missing}"


def test_hints_are_short_and_plain_ascii_vietnamese():
    for name, hint in HINTS.items():
        assert len(hint) <= MAX_HINT_CHARS, name
        # Without diacritics, like the harness's folded query; English after " | ".
        assert hint.isascii(), name
        assert " | " in hint, name


async def test_dividend_question_words_reach_the_right_tool():
    tools = {t.name: (t.meta or {}).get(SEARCH_HINT_KEY, "") for t in await _server().list_tools()}
    assert "co tuc" in tools["dividends_splits"]
    assert "khoi ngoai" in tools["vs_nn_flow"]
    assert "bctc" in tools["financial_detail"]


async def test_prompts_are_vietnamese_and_keep_tool_names():
    server = _server()
    prompts = {p.name: p for p in await server.list_prompts()}
    assert "Dùng" in (prompts["ticker_analysis"].description or "")
    out = await server.get_prompt("risk_check", {"symbols": "fpt, vcb"})
    text = out.messages[0].content.text
    assert "FPT, VCB" in text and "quy mô" in text
    for tool in ("quant_risk", "scenario_simulate", "correlation_matrix", "valuation_run"):
        assert tool in text
