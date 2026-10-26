# Follow-up fixes for merged PR #59

This branch is based on main `565ec6fbd4a2a89b8eed3a289509a1a0fe43efe4`.
It does not require the benchmark or adversarial-test work in PR #60.

## Financial behavior

- Backtest drawdown includes final-close marking and every execution fee.
- `cost_bps` means basis points per side, charged once at each actual entry
  or exit. An open position's final mark is not a liquidation and has no
  fabricated exit fee. A flat-price round trip at 10 bps loses 0.1999%.
- Inferred/invalid observation dates produce `stale=true` and a declared
  `date_basis`; historical observations are not stale merely because a
  backtest intentionally covers past dates. Both strategy and sweep callers
  propagate inference. Changed fingerprints prevent old backtest results
  from being served after deployment.
- Missing aligned condition-asset observations block entry. This fixes the
  actual alignment helper as well as the engine's short-condition behavior.
- Invalid opens (including zero, NaN and infinity) consistently fall back to
  next-bar-close across the whole series. This includes the None/0 fix that
  originally appeared in PR #60 so the production correction is independent.
- UPCoM uses continuous matching 09:00–11:30 and 13:00–15:00, without ATC.
  Source: HNX FAQ, https://hnx.vn/vi-vn/hoi-dap.html.

## Physical-work lifecycle

- Admission follows the concurrent executor Future, not its cancellable
  asyncio wrapper. Running threads remain counted after caller timeout or
  cancellation; cancelled queued jobs and rejected submissions release once.
- vnstock batch admission caps physical legs at three across all batches;
  abandoned queued legs are cancelled, and each batch has one 45-second
  deadline without a per-chunk minimum wait after the deadline.
- Watchlist creation opens, queries and closes PostgreSQL inside one worker.
  Connection cleanup remains with that worker after a caller timeout.
  The file fallback also stays in the worker and does not retry PostgreSQL.

## Validation

- Independent branch checks: 69 passed before the additional five finite-open
  cases; targeted checks for the final additions are recorded in the PR.
- Combined PR #60 candidate: 843 passed, 8 skipped, 1 live-matrix test deselected.
- Ruff and whitespace checks passed. Tests use Event synchronization to prove
  physical threads remain alive after a timeout, rather than sleep-based
  assertions that accepted early admission release.
- The filesystem/network sandbox prevented asyncio thread wakeups; tests were
  rerun outside that sandbox. The earlier local P01 recovery timeout from the
  review is not treated as a separate production failure.
- No PR is merged by this work. Corrected benchmark evidence belongs to PR #60.
