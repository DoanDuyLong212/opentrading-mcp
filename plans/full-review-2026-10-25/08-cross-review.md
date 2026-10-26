# 08 — Cross-review (AGY replacement, opencode, 26/10/2026)

Adversarial pass over the Wave-B patches (commits 1c056ef…a059aac) and the
coordinator's own evidence. **Disclosed reduced independence:** same model
family (GLM) reviewed the GLM-written patches; mitigation = every check below
re-derives expected values from primary definitions and executes them, rather
than re-reading the patches.

## Cross-review results

| # | Check | Kết quả |
|---|---|---|
| CR1 | CCI flat prices → md=0 → CCI 0.0 (convention) | ✅ PASS (0.0) |
| CR2 | CCI < 20 bars → None (không điền) | ✅ PASS (None) |
| CR3 | Wilder flat series → RSI 50.0 (avg_gain=avg_loss=0) | ✅ PASS (50.0) |
| CR4 | Wilder seed + recurrence đối chiếu tay 20 bước | ✅ PASS (seed 5.2, step5 4.56 khớp chính xác) |
| CR5 | F15 buy_hold month gate với **string dates** | 🔴 **FAIL → CR6** |
| CR6 | `_bar_month` bỏ qua ISO date strings (gate thành no-op) | 🔴 **FOUND & FIXED** |

## CR6 — new mandatory finding from the cross-review

`_bar_month` read `getattr(d, "month", None)` only. The real backtest path
(`quant_backtest.py`) passes parsed date objects, but any caller passing ISO
date **strings** — the most common representation — made month/quarter gates
silently no-op: `_run_strategy(closes, "buy_hold", …, dates=[…], months=[2])`
entered on every January bar (net 57.4% instead of the gated ~20.5%).

**Fix:** `_bar_month` now parses ISO strings via `date.fromisoformat(d[:10])`
before falling back to "undated". Verified: gated entry from February only
(net 0.2045, trades 1); all prior oracles still pass (10/10 → 12/12 with the
S04/P05 additions).

## Post-fix verification

- Unit suite: **378 passed, 0 failed** (includes the updated
  `test_yield_curve_fred_fallback_takes_the_newest_point`, which now asserts
  the F10 date-disclosure contract: `as_of_10y`/`as_of_2y` in the payload).
- F05 oracles: 4/4; full-review oracles: 6/6; S04: 2/2; P05 pool: 2/2;
  P01 lifecycle: 5/5.

## Residual risks (disclosed, not silently accepted)

- Same-model review: a GLM-family reviewer can share blind spots with the
  GLM-implemented patches. Primary-definition oracles mitigate but do not
  eliminate this; AGY cross-review should be re-run when quota resets.
- P06 concurrency (semaphore 3) increases vietstock burst rate 3× vs
  sequential — monitored via the quota subsystem (S04); reduce to 2 if 429s
  appear in production logs.
- The load benchmark measures the in-process ASGI stack; a TCP/uvicorn hop
  and Redis are not covered (typically +1–3 ms and negligible respectively).
