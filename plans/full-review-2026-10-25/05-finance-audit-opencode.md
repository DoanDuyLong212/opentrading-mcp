# 05 — Independent financial audit (opencode takeover, 25/10/2026)

Auditor: opencode (coordinator takeover after AGY quota exhaustion and coordinator
ChatGPT quota exhaustion). **Disclosed reduced independence:** this audit shares the
GLM model family with worker OC-A (nvidia/z-ai/glm-5.3). Every verdict below is
grounded in direct source reading at the cited file:line on commit `3932cba3`
(baseline), cross-checked against coordinator repros in `evidence/coordinator-repros.jsonl`.

## Verdict summary

| Finding | Verdict | Severity | Evidence (independent) |
|---|---|---|---|
| F01 equal allocation falls into max_sharpe branch | **CONFIRMED [bắt buộc]** | correctness | quant_stats.py:322-339 |
| F02 CCI wrong deviation basis + delayed availability | **CONFIRMED [bắt buộc]** | correctness | technicals.py:111-117 |
| F03 Wilder seed is first-delta, not SMA-14 (RSI; ATR same pattern) | **CONFIRMED [bắt buộc]** | correctness | technicals.py:87-93, 122 |
| F06 M-score classified on rounded value | **CONFIRMED [bắt buộc]** | correctness | forensic_models.py:226,334 |
| F15 buy_hold ignores months/quarters/cond_ok | **CONFIRMED [bắt buộc]** | correctness | quant_shared.py:199-200 |
| F14 HNX "no ATO/ATC", UPCoM "no price limits" | **CONFIRMED [bắt buộc]** | metadata truthfulness | resources.py:55-56 |
| F07/F08 duplicate-period headers decide fact | CONFIRMED (coordinator repro) | correctness | coordinator-repros.jsonl |
| F09 crypto USDT/USDC identity lost | CONFIRMED (coordinator repro) | data identity | coordinator-repros.jsonl |
| F10 yields silently zero-filled on empty legs | CONFIRMED (coordinator repro) | correctness | yf.py yield path |
| F12 VN trading-date boundary | Design decision locked (S04): Asia/Ho_Chi_Minh day | — | tools/shared.py:90 |
| F05 fill policy (pos[i-1] lookahead) | **NEEDS USER POLICY DECISION** — deferred, not silently patched | semantics | 02-execution-plan.md §3 |

## Independent code-reading detail

### F01 — quant_stats.py (portfolio_optimize)
`raw = np.ones(len(universe))` is the equal placeholder, but the branch structure is
`if objective == "inv_vol": ... else: # max_sharpe closed form` — the `else` also
catches `objective == "equal"`, so equal requests are served max_sharpe weights
(mu/cov/`np.linalg.solve`). The only paths back to equal are singular-covariance and
non-positive-return fallbacks. Matches the archived repro
(`evidence/equal-portfolio-fixture.json`: AAA 0.939935 / BBB 0.060065 for `equal`).
**Fix:** `elif objective == "max_sharpe":` — equal keeps `raw = ones`. One-line change;
add distinct-series oracle asserting each weight = 1/n (not just the sum).

### F02 — technicals.py:111-117 (CCI20)
`md = (tp - sma_tp).abs().rolling(20, min_periods=20).mean()` averages each bar's
deviation from **its own** window mean. Lambert/TradingView CCI requires, at bar *i*,
the mean of |tp[j] − SMA_i| for all j in the *same* window — every deviation measured
against one constant SMA_i. Two consequences, both reproduced by the coordinator:
expected 108.91/actual 57.89 at 40 bars, and **availability delayed to bar 39**
(the deviation series is NaN before bar 20, so its 20-window mean first exists at
bar 39 instead of bar 20). **Fix:** compute `md` with a rolling apply against the
window's own mean (or a vectorized equivalent), min_periods=20 so CCI exists from
bar 20. Zero-deviation behavior (currently 0.0) is reasonable and is kept, now
documented.

### F03 — technicals.py:87-93 (RSI) and :122 (ATR)
`ewm(alpha=1/14, adjust=False, min_periods=14)` seeds the recursion with the first
delta, not Wilder's SMA-of-first-14. Wilder: seed = SMA(deltas[1..14]), then
`avg = (prev*13 + x)/14`. The ewm recursion coincides with Wilder only *after* a
correct seed; seeding at x₀ shifts the whole curve (coordinator repro 65.43 vs
60.76). Same construction at line 122 for ATR14 (and the ADX smoothing chain built
on it). **Fix:** SMA-seeded Wilder recurrence for RSI, ATR (and ADX components per
the existing convention note — do not change the ADX *convention*, only the seed
correctness where the Wilder definition is claimed). Warmup indices and flat-series
policy must be stated in the tool docstring.

### F06 — forensic_models.py:226 + 334
`m_score = round(raw_score, 4)` (line 226) then classification at line 334 tests
`m_score > -1.78` on the **rounded** value. Raw −1.77999 rounds to −1.78 and loses
the "further review" flag; raw −1.78001 stays below either way — i.e., display
rounding flips a decision. **Fix:** classify on `raw_score`; round only for
emission. Keep `cutoff: -1.78` in the payload.

### F15 — quant_shared.py:199-200 (buy_hold)
`if strategy == "buy_hold": pos = [1] * n` — the docstring promises "entries only
allowed on matching bars; off-window bars force flat", and the gate machinery
(`month_set`/`quarter_set`/`cond_ok` via `_allowed`) exists, but buy_hold never
consults it. Public output claims `month_filtered=true` while every bar trades
(coordinator repro: months=[2], January trades execute, net_return 0.3301).
**Fix:** route buy_hold through `_allowed` for entries (keep exits always allowed),
and emit `month_filtered` truthfully (false when nothing was filtered).

### F14 — resources.py:55-56
`"HNX": {..., "auction": "continuous, no ATO/ATC"}` and
`"UPCOM": {..., "auction": "continuous, no price limits"}` contradict the HNX
official FAQ (closing auction 14:30–14:45 for listed shares; UPCoM ±15% band).
Coordinator condition: worker must confirm current official venue rules and preserve
documented exceptions (first trading day). **Fix:** correct both metadata statements
only to the extent official sources confirm; keep the valuation-hint concern as a
separate recommendation.

## Items I could not upgrade beyond coordinator status

- F05: a semantic patch requires a *policy* (decision timestamp + fill convention).
  Neither the code nor the plan fixes one; this is a user/business decision. Options
  recorded in 02 §3. Not silently patched.
- F09/F10/F12: coordinator repros accepted; repairs belong to the data-contract wave
  (identity/completeness metadata) — larger than formula fixes, scheduled after the
  formula wave so cache-fingerprint changes land once.
- F13 (pricing basis) remains [khuyến nghị] pending primary-source evidence.

## New observations from this audit (not in prior list)

- N1 [khuyến nghị]: CCI zero-deviation policy currently maps md==0 → 0.0; standard
  references leave CCI undefined/0 for flat windows by convention choice — fine, but
  the emitted contract should say which.
- N2 [khuyến nghị]: `rsi = rsi.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))`
  applies the flat-policy to *all* bars including warm-up NaNs before clipping —
  verify no warm-up bar can surface as 50.0 instead of None.
- N3 [khuyến nghị]: portfolio cache key `fp = f"{symbols}|{objective}|{days}"` does not
  include the data window end date; a cached plan served later spans a different
  common-date range. Not a correctness bug in the weights math, but a freshness
  contract gap consistent with the S05 fingerprint finding.

## Coverage and honesty notes

- Verified by reading: F01, F02, F03, F06, F15, F14 (source lines above).
- Accepted on archived synthetic repro (not re-run here): F07, F09, F10.
- Deferred to user policy: F05.
- No live market calls were made during this audit; no files outside `plans/` touched.
- Reduced-independence disclosure stands: same model family as OC-A; mitigated by
  grounding every verdict in quoted source lines and the coordinator's archived repros.
