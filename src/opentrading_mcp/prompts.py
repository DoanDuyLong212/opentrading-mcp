"""MCP prompts: tool-composition guides (UW/EODHD/Tiingo pattern).

Prompts do not fetch data; they tell the agent which tools to call in
which order for recurring workflows. ai_detect is a heuristic proxy of
the 8010 Breakout/SEPA model (reference-only: no pickle, no ML probability).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(server: FastMCP) -> list[str]:
    @server.prompt(description="Compose the session-open brief. Use at market open.")
    def morning_briefing(scope: str = "vn") -> str:
        return (
            f"Compose a morning brief for scope '{scope}'.\n"
            "1. Call brief_build for the composed brief.\n"
            "2. Call market_overview for quotes, movers, breadth and session.\n"
            "3. Call breadth_scan to judge rally health.\n"
            "4. Call money_flow for foreign smart-money direction.\n"
            "5. Call futures_basis for VN30F1M premium/discount.\n"
            "6. Call world_prediction_odds when macro odds matter.\n"
            "Synthesize in 5 bullets with provenance per line."
        )

    @server.prompt(description="Deep dive on one ticker. Use before recommending a name.")
    def ticker_analysis(symbol: str) -> str:
        sym = symbol.strip().upper()
        return (
            f"Analyze {sym}.\n"
            "1. Call symbol_lookup when unsure of the exact symbol.\n"
            "2. Call stock_overview for the dossier.\n"
            "3. Call signals_technical for timing (RS, 52w position, patterns).\n"
            "4. Call valuation_run for fair-value range.\n"
            "5. Call stock_forensic for earnings-quality flags.\n"
            "6. Call insider_trading and analyst_consensus for flow and street views.\n"
            "7. Call company_events and news_symbol for catalysts.\n"
            "End with bull/bear cases and what would change your mind."
        )

    @server.prompt(description="Reliability grade before earnings. Use when results are near.")
    def pre_earnings(symbol: str) -> str:
        sym = symbol.strip().upper()
        return (
            f"Grade the pre-earnings setup for {sym} (do NOT forecast the result).\n"
            "1. Date certainty: company_events + event_calendar_vn — dated or rumor?\n"
            "2. Trend quality: financial_statements last 4 quarters.\n"
            "3. Manipulation risk: stock_forensic M-Score/Piotroski.\n"
            "4. Expectation anchor: planned_targets (company plan) + analyst_consensus "
            "dispersion + news_symbol heat + sentiment_score hype risk.\n"
            "5. Positioning: insider_trading + money_flow + block_trades abnormal prints.\n"
            "6. Cushion: valuation_run multiple vs history.\n"
            "Output: grade A/B/C with one evidence line per leg, suggested size via "
            "scenario_simulate, and an explicit unknowns list (no EPS consensus exists "
            "in VN, so no numeric surprise level is ever set)."
        )

    @server.prompt(description="Rotate across sectors. Use for allocation reads.")
    def sector_rotation() -> str:
        return (
            "Read sector rotation.\n"
            "1. Call sector_performance for the heatmap.\n"
            "2. Call money_flow for where foreign desks sit.\n"
            "3. Call futures_basis for derivatives positioning.\n"
            "4. Call ipo_calendar_vn for upcoming supply pressure.\n"
            "5. Call compare_equities on the top-2 leaders per hot sector.\n"
            "Name the rotation (e.g. bank->steel) with supporting numbers."
        )

    @server.prompt(
        description="Breakout detect (SEPA-style heuristic). Use to hunt or validate breakouts."
    )
    def ai_detect(symbol: str | None = None) -> str:
        target = (symbol or "").strip().upper()
        header = (
            f"Validate the breakout setup for {target}.\n"
            if target
            else "Hunt breakouts: run signals_scan first, then validate each hit below.\n"
        )
        return (
            header + "Heuristic proxy of the 8010 Breakout/SEPA model (reference-only: "
            "no ML probability, no 0.85 gate — score legs instead).\n"
            "Leg 1 trend template: signals_technical — price above sma50/sma150/sma200, "
            "adx14 >= 20, rs_vs_bench > 0, pos_52w > 0.75.\n"
            "Leg 2 contraction: boll bandwidth narrowing + low atr14 + volume dry-up.\n"
            "Leg 3 breakout confirm: last above resistance(20d); cross-check signals_scan; "
            "pattern_match for historical analogies.\n"
            "Leg 4 fundamentals: vn_fundamentals EPS growth + valuation_run (avoid chasing "
            "extended multiples).\n"
            "Leg 5 flow: money_flow + block_trades confirmation.\n"
            "Verdict: STRONG (>=4 legs) / WATCH (3) / REJECT; entry + invalidation from "
            "support/resistance; state which legs failed."
        )

    @server.prompt(description="Pre-trade risk checklist. Use before sizing any position.")
    def risk_check(symbols: str, side: str = "buy", size_vnd: str = "100000000") -> str:
        names = ", ".join(s.strip().upper() for s in symbols.split(",") if s.strip())
        return (
            f"Pre-trade checklist: {side.upper()} {names} size {size_vnd} VND.\n"
            "1. quant_risk on recent returns (Sharpe, max drawdown, win rate).\n"
            "2. scenario_simulate a -5% shock, scaled to the size above.\n"
            "3. correlation_matrix against current holdings.\n"
            "4. stock_forensic per name (M-Score red halves size or skips).\n"
            "5. company_events + event_calendar_vn blackout check (BCTC/meeting within "
            "10 days halves size).\n"
            "6. valuation_run cushion check.\n"
            "Output: GO / HALF / NO-GO with max size in VND, invalidation price, "
            "and 3 unknowns."
        )

    return [
        "ai_detect",
        "morning_briefing",
        "pre_earnings",
        "risk_check",
        "sector_rotation",
        "ticker_analysis",
    ]
