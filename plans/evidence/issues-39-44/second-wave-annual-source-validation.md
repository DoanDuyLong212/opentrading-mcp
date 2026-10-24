# Annual detail source validation - 2026-10-24

The first-wave `financeinfo(period="year")` mirror supplies only eight FPT
canonical fields. This phase checked the existing Vietstock
`/FinancialStatement/BCTC_LoadReportData_Async` route using the installed
provider request shape (`build_list_params`, annual `ReportTermId=1`, `Unit=1`).
The sanitized public 2024-2025 result is
`tests/fixtures/vietstock_fpt_bctc_annual_20261024.json`. No credential,
cookie, CSRF token, or login response is in the fixture.

The raw endpoint returns VND integer `Value`, `StockCode`, `YearPeriod`,
`ReportTermID`, `UnitedName`, audit label and publication timestamp on each
line. It does **not** return fiscal boundaries, `ReportDataID` or revision
ordering. Its `IsUnited=0` in rows labeled `UnitedName="Hợp nhất"`, so the
numeric flag cannot be used as a scope proof. The adapter requires explicit
consolidated name, annual term, same symbol/year, one consistent row metadata
set, publication after year end and before `as_of`, and exact agreement with
four annual mirror anchors: net sales 2216, total net income 2212, total assets
2996 and total equity 2998. A mismatch rejects that year's enrichment.

The [FPT 2025 annual report](https://bctn2025.fpt.com/wp-content/uploads/2026/04/BCTN-2025.pdf)
is a separate company source. Its consolidated financial statements (printed
pp. 164-170; PDF extraction around lines 8029-8292) match the BCTC annual
2025 values, in raw VND:

| Item | Vietstock norm | 2025 value |
| --- | ---: | ---: |
| Net sales | 2216 | 70,112,825,100,710 |
| Total net income | 2212 | 11,232,339,450,734 |
| Current receivables aggregate | 3005 | 14,402,017,450,105 |
| Tangible fixed assets, net | 3035 | 15,359,168,484,059 |
| Long-term borrowing and finance lease | 3078 | 1,903,789,988,184 |
| Operating cash flow | 2234 | 10,136,043,915,911 |
| Administrative expense | 2224 | 7,337,325,397,804 |

The fixture includes 2024 values that match the same four anchors in the
recorded `financeinfo` annual mirror. The resulting adapter adds CFO,
selling/admin costs, long-term borrowing and tangible/finance-leased PPE for
2024-2025; beginning balance 2023 remains from the mirror. FPT Piotroski
coverage rises from 5 to 7 evaluated signals. Both complete scores remain
`null` because required inputs are unavailable.

Specific gaps preserved:

- The [Beneish, Lee and Nichols 2013 Appendix A](https://cpb-us-w2.wpmucdn.com/sites.udel.edu/dist/a/855/files/2020/07/Earnings-Manipulation-and-Expected-Returns.pdf)
  uses Compustat Receivables Total item [2]. The [Compustat item definition](https://tevgeniou.github.io/EquityRiskFactors/CompustatManualChpt5.pdf)
  excludes some advances on material purchases. FPT's current receivables
  aggregate 3005 includes seller prepayments; customer trade receivables 3022
  is narrower. Neither is silently substituted for item [2]. DSR stays
  missing pending an explicit Vietnam mapping and sensitivity analysis.
- The endpoint's annual list has no verified depreciation expense, current
  portion of long-term debt or explicit parent-company equity-issuance flag.
  Its norm 2242 is labeled `Khấu hao TSCĐ và BĐSĐT`, while FPT's official
  2025 cash-flow statement line 02 combines fixed-asset depreciation **and
  goodwill amortization** (2,914,178,360,732 VND). It is not the pure
  depreciation expense required for DEPI. Norm 2261 is cash from issuing
  shares **and owner capital contributions**; it does not identify the
  parent-company equity issue required by Piotroski. Accumulated
  depreciation, all short-term borrowing, share-count changes and company
  capital changes are not substitutes.
- BCTC publication timestamps are interpreted in Vietnam local time; this
  gate prevents use before a particular report's publication, but today's
  endpoint can restate earlier values and does not create a historical
  point-in-time dataset. Report audit label is preserved, not treated as a
  revision sequence.
- The FPT 2025 report discusses a change in consolidation of FPT Telecom.
  The model's year comparison must be read with this company event in mind;
  no threshold is recalibrated here.
- VCB remains an unsupported bank model with malformed 2025 annual metadata
  from the mirror. No report dates or line values were repaired by inference.

Verification: 100 focused annual/model tests pass; Ruff passes. Fixture
tests reject wrong scope, anchor, publication, duplicate line and unit.
