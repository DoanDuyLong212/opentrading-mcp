# Issues 39/44 first-wave independent validation

Status: **locally approved for push and draft PR review**. No outstanding failing local assertion. This is not deployment verification or permission to merge. The user already authorized push/draft PR; this report adds technical review evidence.

## Source state

Worktree: `/home/doanlong/.codex/worktrees/issues-39-44-first-wave/MCP-server`.

- Phase 1: `b18993e9aba59ebb05e94df6c43a1cb9a7fd2911` — preserve zero ratios and reject invalid screening metrics.
- Phase 2: `892e66c7fca2d10a61d9a4ddb698352041316b14` — normalize annual inputs by period and report scope.
- Phase 3 and consumer documentation were uncommitted changes on that base during this verification; subsequently committed unchanged as `b552fb54e1456d7997477ec9237f038a840cb2b5`.

Final verified SHA256 hashes:

| File | SHA256 |
| --- | --- |
| `src/opentrading_mcp/forensic_models.py` | `be0f196756f46502e2966a577ba6175bb9033710c866f2f02710c09e1ec07ca6` |
| `src/opentrading_mcp/providers/forensic.py` | `4bd13cd391f0cd8076d60f5b3439e3bb37d0fed05480aceef63d3993ae2ec944` |
| `src/opentrading_mcp/tools/compute_financial.py` | `fe733dd47e5e753769d684704f0f43031f1da31d0d7a3b3ad9b2545ddbd0d612` |
| `src/opentrading_mcp/prompts.py` | `c6b4c2f4494a4f41f585e78607a51d64b6711377eeb5d53d205c30df74abb9bb` |
| `SKILLS.md` | `2147d1b2d88fe85e442f2df64d017710da698d3b79f950da28c688ef1881f36f` |

## Checks and exact scope

| Run | Result | Scope/caveat |
| --- | --- | --- |
| Full CI-selected baseline | **646 passed, 1 deselected, 1 warning in 269.48s**, exit 0 | Before signed Piotroski gross-margin repair and final consumer documentation. Includes isolated PostgreSQL tests. |
| Repaired model + every directly affected integration file | **127 passed in 15.30s**, exit 0 | Final repaired model; forensic models, annual inputs, forensic inputs, financeinfo alignment, report scope and P5 compute tool parameters. |
| Final prompt/resource consumers | **12 passed in 7.67s**, exit 0 | Final `prompts.py`/`SKILLS.md`; P6 prompt and resource contract suites. |
| Final `ruff check src tests --no-cache` | **PASS**, exit 0 | After final consumer documentation changes. |
| Final `git diff --check` | **PASS**, exit 0 | After final consumer documentation changes. |

The full baseline loaded `forensic_models.py` SHA256 `b08587ef2335a93e3c1efd0f9a33b7dac079b30a66cfb47540430cc0a4f339fa`. Another review then found that a shared negative-margin guard incorrectly suppressed valid signed Piotroski margin changes. The final model confines that restriction to Beneish. Independent signed-margin cases and all affected consumers passed after repair. **Do not describe 646 as a full-suite execution of the final repaired/documented state. Fresh GitHub CI must establish that result.**

Full-suite command matched CI selection:

```sh
python -m pytest -q -p no:cacheprovider --deselect tests/contract/test_verify_matrix.py::test_full_matrix_stdio
```

Clean `env -i` retained only PATH, PYTHONPATH=src, VNSTOCK_TELEMETRY=off, MPLBACKEND=Agg and TEST_DATABASE_URL for the disposable test DB. No original `.env` was loaded. Python 3.12.3; pytest 9.1.1; ruff 0.16.8; vnstock 4.0.2; psycopg 3.3.6. Verified server **PostgreSQL 16.15**, isolated database `issues_39_44_test`, Unix socket only. No production database used. The sole full-suite warning is an existing Starlette/httpx deprecation warning.

An initial focused run under restricted execution stalled at async cache work and was terminated without an assertion failure; the completed 127-test run used the same authorized execution permissions/environment as the full baseline.

## Independent mathematical evidence

`independent_oracle.py` uses Fraction arithmetic and literal coefficients rather than importing production coefficients. Distinct inputs independently verify all eight Beneish components and M-score **-1.7144583333333334**, displayed **-1.7145**. Nine separately expected, mixed true/false Piotroski signals yield **3/9**, preventing an all-true-only oracle from hiding inequality or denominator mistakes.

Additional independent assertions passed:

- Financial industries bank/securities/insurance never receive full standard scores.
- Invalid newest annual observation does not silently fall back to stale complete history.
- Two annual balance dates permit Beneish while Piotroski requires three.
- Missing each of thirteen individual current Beneish input fields prevents a complete score.
- Valid zero inputs remain zero, with positive-income/CFO signals correctly false.
- Six signed gross-margin transitions cover negative-to-less-negative, negative-to-positive, negative-to-zero, worsening, equal negative margins and equal zero margins. Piotroski still evaluates all nine components; Beneish rejects negative gross-margin domain.

The test suites also cover annual company/scope/calendar isolation, zero/missing/invalid numbers, old cache poison bypass and cold/warm model cache behavior.

## Source evidence and limits

Two recorded annual source fixtures are exercised parser-to-public-tool: `financeinfo_fpt_annual_20261024.json` and `financeinfo_vcb_annual_20261024.json`. FPT exposes partial verified annual data, so unavailable CFO/depreciation/issuance inputs remain missing and no complete score is fabricated. VCB is classified as bank and source identity limitations remain visible. These real-source fixtures prove source normalization and honest partial reporting; **full eight-variable/nine-signal numerical proof uses explicit synthetic contracts**, without claiming upstream availability of those extra fields.

Annual depreciation expense, current portion of long-term debt and explicit equity issuance do not have verified source mappings. Unknown revision ordering/conflicting snapshots are rejected; publication-date information is unavailable, so this is not a point-in-time historical dataset. Standard financial-industry models remain unsupported. `periods_n` limits displayed history only, not annual model requirements. Downstream prompts now gate conclusions on applicability/completeness.

No new source network requests were made during this independent verification. No live stdio matrix, deployed behavior, merge, production rollout, or post-deployment observation was verified. Remaining technical signals, valuation/source coverage and cycle changes stay outside this first wave and require the remaining-work plan.

## Logs

Permanent evidence is beside this report: `pytest.log`, `post-repair-focused.log`, `final-docs-prompts.log`, `final-ruff.log`, `final-diff-check.log`, `independent-oracle.log`, `negative-margin-oracle.log`, and the two independent oracle scripts. No credentials are included.

Final prompt wording-only update was independently reverified: 12 passed in 7.67s, exit 0. This final run used no database and retained the same clean environment. Final prompt SHA256 is c6b4c2f4494a4f41f585e78607a51d64b6711377eeb5d53d205c30df74abb9bb. Other production/model files unchanged; final lint/whitespace results above preceded only this tiny prose delta (implementer reran lint/whitespace successfully afterward).
