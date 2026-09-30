"""MCP prompts: tool-composition guides (UW/EODHD/Tiingo pattern).

Prompts do not fetch data; they tell the agent which tools to call in
which order for recurring workflows.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(server: FastMCP) -> list[str]:
    @server.prompt(description="Compose the session-open brief. Use at market open.")
    def morning_briefing(scope: str = "vn") -> str:
        return (
            f"Compose a morning brief for scope '{scope}'.\n"
            "1. Call brief_build for the composed brief.\n"
            "2. Call market_snapshot for index levels and breadth.\n"
            "3. Call breadth_scan to judge rally health.\n"
            "4. Call money_flow for foreign smart-money direction.\n"
            "5. Call world_prediction_odds when macro odds matter.\n"
            "Synthesize in 5 bullets with provenance per line."
        )

    @server.prompt(description="Deep dive on one ticker. Use before recommending a name.")
    def ticker_analysis(symbol: str) -> str:
        sym = symbol.strip().upper()
        return (
            f"Analyze {sym}.\n"
            "1. Call symbol_lookup when unsure of the exact symbol.\n"
            "2. Call stock_overview for the dossier.\n"
            "3. Call signals_technical for timing.\n"
            "4. Call valuation_run for fair-value range.\n"
            "5. Call company_events and news_symbol for catalysts.\n"
            "End with bull/bear cases and what would change your mind."
        )

    @server.prompt(description="Position into earnings. Use when results are near.")
    def pre_earnings(symbol: str) -> str:
        sym = symbol.strip().upper()
        return (
            f"Prepare for {sym} earnings.\n"
            "1. Call company_events for the reporting date and guidance.\n"
            "2. Call financial_statements for the last 4 quarters trend.\n"
            "3. Call valuation_run for the current multiple vs history.\n"
            "4. Call news_symbol for expectations and rumors.\n"
            "State the base/bull/bear EPS scenarios and the surprise threshold."
        )

    @server.prompt(description="Rotate across sectors. Use for allocation reads.")
    def sector_rotation() -> str:
        return (
            "Read sector rotation.\n"
            "1. Call sector_performance for the heatmap.\n"
            "2. Call money_flow for where foreign desks sit.\n"
            "3. Call compare_equities on the top-2 leaders per hot sector.\n"
            "Name the rotation (e.g. bank->steel) with supporting numbers."
        )

    return ["morning_briefing", "pre_earnings", "sector_rotation", "ticker_analysis"]
