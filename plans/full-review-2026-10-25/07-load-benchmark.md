# 07 — Historical ASGI benchmark (superseded)

> Superseded by 09-load-benchmark-http.md. The original harness accepted
> unavailable tool envelopes, included warmup time in RPS and generated
> process-dependent fixtures. Its numbers and causal performance claims below
> are retained as historical context, not valid acceptance evidence.

Harness: `scripts/load_bench.py` — real ASGI app (FastMCP streamable HTTP,
stateless mode), deterministic synthetic upstream (no live network), tool
`signals_technical` on 300-bar synthetic candles, rounds=40 per level,
warmup 5, interleaved-able runs. Host: same machine, sequential paired runs
(+1 reversed-order confirmation round at concurrency 32).

## Results (min-of-runs, 100% success everywhere)

| Concurrency | Metric | Baseline 3932cba | Wave-B fix | Δ |
|---|---|---|---|---|
| 1 | p50 | 14.0 ms | 14.6 ms | +4.3% (par) |
| 1 | p95 | 23.6 ms | 19.1 ms | **−19.1%** |
| 1 | p99 | 167.1 ms | 19.4 ms | **−88.4%** |
| 8 | p50 | 105.3 ms | 80.0 ms | **−24.0%** |
| 8 | p95 | 118.6 ms | 101.2 ms | **−14.7%** |
| 8 | p99 | 162.2 ms | 149.2 ms | −8.0% |
| 8 | RPS | 66.6 | 77.9 | **+17.1%** |
| 32 | p50 | 330.2 / 387.5 ms | 430.3 / 344.4 ms | ~par (round-2 −11%) |
| 32 | p95 | 436.2 / 569.5 ms | 518.9 / 426.1 ms | −6% avg (noise-dominated) |
| 32 | RPS | 75.6 / 58.7 | 63.2 / 73.7 | ~par (avg +1.9%) |

*Conc-32 rows show two runs each (round 1 / round 2, reversed dispatch order);
the two rounds disagree in sign — the difference is within repeat variance.*

## Reading

- **The p99 tail collapse at concurrency 1 (167 ms → 19 ms)** is the direct
  effect of the F02/F03 correctness work: the old CCI's delayed availability
  and ewm-seeded Wilder curve produced different-but-valid-looking values with
  different tail behavior; the corrected implementation is deterministic and
  its first-window availability removes the late-first-value tail.
- **Concurrency 8 is a clear win** (RPS +17%, p50 −24%): same executor, same
  shed limit, less per-call pandas overhead in the vectorized CCI/Wilder.
- **Concurrency 32 is parity within variance** — the executor queue (shed
  limit) dominates, not the indicator math.
- No shed, no failures at any level; correctness rates identical (100%).

## Coverage honesty

- This harness measures the in-process ASGI stack end-to-end (JSON-RPC →
  tool dispatch → cache → run_blocking executor → provider-fixture). It does
  NOT include a real TCP/uvicorn hop (adds typically ~1–3 ms) nor Redis
  (memory store only). k6 was not installed; the pure-python driver plays the
  same role for the measured scenarios.
- RSS and thread-count under load were not captured by this harness; P05's
  thread bound is covered by `tests/test_p05_vnstock_pool.py` instead.
