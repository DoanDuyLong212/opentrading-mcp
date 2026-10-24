# Annual source validation — 2026-10-24 Asia/Bangkok

Read-only `vietstock.financeinfo(symbol, period="year")`, FPT and VCB; existing local provider configuration loaded only into an isolated process with `dotenv_values`. No shell source, auth exports, request dumps or credentials saved. Provider ordinary in-memory session/login behavior permitted; source files unchanged.

Reproducible command (requires existing private local config):
`/home/doanlong/MCP-server/.venv/bin/python /tmp/issue-39-44-live/validate_annual.py`

Initial sandbox call: both ProviderUnavailable (no exception detail printed). Same command after network escalation: both returned public financial payloads. Each symbol bounded by a 100 second process alarm.

Source inspected: worktree `src/opentrading_mcp/providers/vietstock.py` financeinfo, _session_client, _login and seed behavior; `src/opentrading_mcp/providers/forensic.py` normalize_annual, mappings and guards. Upstream endpoint https://finance.vietstock.vn/data/financeinfo, existing provider requests ReportTermType=1, ReportType=BCTQ, Unit=1, Page=1, PageSize=4.

Evidence:
- fpt-annual.json and vcb-annual.json: sanitized public financial payloads.
- *-normalized.json: actual normalization output including diagnostics.
- *-summary.json: header and normalized record summary.
- No branch files or fixtures modified.

FPT: 5 actual annual headers 2021–2025, ReportTermID=1, HN, CompanyID=191, BusinessType=1. All full calendar years accepted, no rejections. Endpoint returns 5 columns despite PageSize=4. Annual public mirror includes 5 KQKD and 6 CDKT rows, plus ratios. Eight canonical values/year: revenue, gross, net_income, current_assets, assets, liabilities, current_liabilities, equity. No LCTT section; no CFO, depreciation, PPE, receivables, long term debt, selling/admin rows. Norm 2212 is total Profit after tax; separate 2214 is parent-company Net profit.

VCB: BusinessType=3, CompanyID=1167, HN. Accepted 2022–2024 as bank records with general mappings deliberately empty. Rejects 2021 PeriodBegin=0/PeriodEnd=0 and 2025 PeriodBegin=202501/PeriodEnd=202612 (24 months). Upstream malformed periods observed live, not synthetic. No LCTT section.

Unit caveat: every KQKD/CDKT row in both responses has blank Unit. VND classification relies on provider request Unit=1 and pre-existing provider contract; response does not explicitly label financial amount rows. Ratio rows separately carry %, Lần, VNĐ. Confidence high in header shapes, source missingness, scope code observation and guard behavior; response alone insufficient for independent VND scaling proof or complete forensic model eligibility. No backfilled/guessed data or repaired upstream boundaries.
