"""P8 contract: ai_detect + risk_check + pre_earnings_v2 + refreshed prompts (TDD RED)."""

from __future__ import annotations

from opentrading_mcp.server import create_server, register_preset


def _prompts():
    from opentrading_mcp.prompts import register_prompts

    server = create_server("market")
    register_preset(server, "market")
    names = register_prompts(server)
    return server, names


async def test_prompt_roster_p8():
    _, names = _prompts()
    assert sorted(names) == [
        "ai_detect",
        "morning_briefing",
        "pre_earnings",
        "risk_check",
        "sector_rotation",
        "ticker_analysis",
    ]


async def test_ai_detect_with_symbol():
    server, _ = _prompts()
    out = await server.get_prompt("ai_detect", {"symbol": "VCB"})
    text = out.messages[0].content.text
    assert "VCB" in text
    for token in ("signals_technical", "signals_scan", "STRONG", "REJECT",
                  "no ML probability", "rs_vs_bench", "pos_52w"):
        assert token in text, token


async def test_ai_detect_without_symbol_scans_universe():
    server, _ = _prompts()
    out = await server.get_prompt("ai_detect", {})
    text = out.messages[0].content.text
    assert "signals_scan" in text


async def test_risk_check_verdict_format():
    server, _ = _prompts()
    out = await server.get_prompt(
        "risk_check", {"symbols": "VCB,HPG", "side": "buy", "size_vnd": "100000000"}
    )
    text = out.messages[0].content.text
    for token in ("quant_risk", "scenario_simulate", "correlation_matrix",
                  "stock_forensic", "GO", "HALF", "NO-GO"):
        assert token in text, token


async def test_pre_earnings_is_reliability_graded():
    server, _ = _prompts()
    out = await server.get_prompt("pre_earnings", {"symbol": "VCB"})
    text = out.messages[0].content.text
    for token in ("grade", "stock_forensic", "unknowns", "analyst_consensus"):
        assert token in text, token
    assert "surprise threshold" not in text


async def test_morning_briefing_uses_overview():
    server, _ = _prompts()
    out = await server.get_prompt("morning_briefing", {"scope": "vn"})
    text = out.messages[0].content.text
    assert "market_overview" in text
    assert "futures_basis" in text


async def test_ticker_analysis_covers_forensics():
    server, _ = _prompts()
    out = await server.get_prompt("ticker_analysis", {"symbol": "HPG"})
    text = out.messages[0].content.text
    for token in ("stock_forensic", "insider_trading", "analyst_consensus"):
        assert token in text, token
