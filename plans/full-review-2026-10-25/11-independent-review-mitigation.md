# 11 — Review mitigation and regression evidence

The previous review was not an independent human audit. This follow-up also
makes no claim of independent personnel or model review. Its confidence comes
from executable counterexamples and independent reference calculations.

## Financial/reference checks

- CCI uses a window's one constant mean and hand-computed absolute deviations.
- RSI/ATR compare to SMA-seeded Wilder definitions.
- Wave 5 compares every smoothed value to a scalar recurrence initialized from
  the first 14 actual inputs. The earlier self-equality OR assertion was removed.
- F10 same-date and mismatched-date checks now call the registered yield-curve
  tool with patched upstreams; they do not just recompute a local conditional.
- PR #61 adds a final-close loss with an exact 50% drawdown, a constant-price
  fee-only round trip, invalid-open fallbacks, and missing-condition alignment.
- Strategy/sweep date inference is verified through the actual registered tool.

## Runtime checks

PR #61 admission tests synchronize with thread Events, explicitly assert a
running worker is still counted after caller timeout/cancellation, and verify
queued cancellation, submission rejection, shedding and recovery. The vnstock
provider test saturates all three workers, issues repeated expired requests,
asserts no backlog, and proves old work does not replay after recovery.
Watchlist tests verify connection/query/close thread ownership and a responsive
caller event loop while connect is blocked.

The corrected TCP harness validates application availability/data shape, not
just HTTP 200 or MCP isError. Its tests cover malformed envelopes, progress
notifications, unavailable/partial data, timer boundaries, fresh namespaces,
stall/health/peer/burst execution and disposable-container outage orchestration.

## Verification boundaries

- Combined suite before five extra invalid-open cases: 843 passed, 8 skipped,
  1 live-provider matrix deselected. Final invalid-open/FRED selection: 17 passed.
- Production branch independent of PR #60: 69 passed before those five additions.
- Ruff src/tests and the three benchmark scripts passed.
- PostgreSQL-dependent skips and live external-provider behavior are not claimed
  as verified by offline fixtures. TCP/Redis measured evidence is in report 09.
- A future independent reviewer should rerun these counterexamples and inspect
  the accounting definitions and queue lifecycle, not rely on passing test counts.
- No unvalidated Vietnam-specific Beneish threshold or predictive pricing claim
  is introduced. The source memo in 10 remains research context, not calibration.
