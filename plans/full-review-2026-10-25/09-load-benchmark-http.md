# 09 — Corrected TCP/Redis benchmark and overload evidence

Previous PR descriptions and report 07 are superseded. Application availability
and required data fields are now checked; partial/unavailable responses count
as failures. Warmup requests and time are both excluded from measured RPS.

## Method

- Real uvicorn/TCP, offline deterministic provider fixtures, Redis 7 in an
  isolated container labelled `opentrading-bench=1`. All listeners used
  automatically selected loopback ports; Docker host port stayed fixed across restart.
- Main samples: warmup 5 seconds and measured minimum 15 seconds; 1, 8, 32 clients.
  Steady modes use continuous workers; burst sends synchronized waves with a 0.1s gap.
- Fixed provider latency 20ms, except stall injects 1000ms. Three blocking workers,
  queue shed threshold 50. Unique UUID namespaces prevent cold cross-run cache hits.
- Baseline is current main `565ec6f`, not the original pre-#59 `3932cba`.
  Candidate production is PR #61 `0e4d57a`; the corrected wrapper/driver is used for both.
- Runs are sequential on the same host; no repeated balanced-order campaign.
  These results establish behavior and limits; they do not establish a speedup.
- Smoke rows use 1s samples and 0.2s warmup and are explicitly excluded from
  performance comparison. Error detail fields were added before the overload repeat.

## Measured rows (smoke omitted)

| Run | Mode | Clients | Requests | RPS | p50 ms | p95 ms | p99 ms | App success |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| candidate-main | cold | 1 | 113 | 7.52 | 127.5 | 188.32 | 224.32 | 100.0% |
| candidate-main | cold | 8 | 148 | 9.55 | 754.35 | 1181.68 | 1239.85 | 100.0% |
| candidate-main | cold | 32 | 172 | 10.72 | 2880.89 | 3910.7 | 3931.45 | 100.0% |
| candidate-main | warm | 1 | 951 | 63.38 | 14.41 | 22.91 | 39.37 | 100.0% |
| candidate-main | warm | 8 | 706 | 46.91 | 153.08 | 324.76 | 588.82 | 100.0% |
| candidate-main | warm | 32 | 1174 | 77.51 | 395.88 | 531.95 | 840.47 | 100.0% |
| candidate-main | stall | 1 | 8 | 0.48 | 2069.28 | 2090.46 | 2090.46 | 100.0% |
| candidate-main | stall | 8 | 26 | 1.42 | 5119.52 | 6149.15 | 6190.85 | 100.0% |
| candidate-main | stall | 32 | 42 | 1.47 | 15432.29 | 21481.94 | 22391.39 | 100.0% |
| candidate-main | health-under-load | 1 | 117 | 7.77 | 127.49 | 144.22 | 172.39 | 100.0% |
| candidate-main | health-under-load | 8 | 165 | 10.77 | 727.71 | 1102.73 | 1151.33 | 100.0% |
| candidate-main | health-under-load | 32 | 168 | 10.34 | 3122.02 | 3562.63 | 3569.53 | 100.0% |
| candidate-main | peer | 1 | 274 | 18.25 | 54.49 | 58.32 | 60.91 | 100.0% |
| candidate-main | peer | 8 | 372 | 24.42 | 323.32 | 340.62 | 389.81 | 100.0% |
| candidate-main | peer | 32 | 697 | 44.77 | 681.95 | 1390.53 | 1644.36 | 25.82% |
| candidate-extra | burst | 8 | 632 | 41.68 | 76.9 | 103.97 | 147.31 | 100.0% |
| candidate-extra | mixed | 8 | 210 | 13.35 | 530.32 | 1359.24 | 2191.95 | 100.0% |
| candidate-extra | redis-down | 8 | 157 | 10.25 | 747.97 | 1003.14 | 1149.71 | 100.0% |
| candidate-overload | peer | 32 | 996 | 64.44 | 500.78 | 966.52 | 1007.39 | 11.75% |
| baseline-main | cold | 1 | 95 | 6.29 | 133.4 | 267.58 | 384.23 | 100.0% |
| baseline-main | cold | 8 | 172 | 11.14 | 723.49 | 913.53 | 935.03 | 100.0% |
| baseline-main | cold | 32 | 198 | 11.56 | 2785.45 | 2983.43 | 2988.97 | 100.0% |
| baseline-main | warm | 1 | 1039 | 69.21 | 14.03 | 17.37 | 20.5 | 100.0% |
| baseline-main | warm | 8 | 1149 | 76.19 | 99.58 | 154.28 | 211.87 | 100.0% |
| baseline-main | warm | 32 | 1015 | 66.71 | 458.42 | 612.97 | 775.36 | 100.0% |

## Interpretation and boundaries

- All cold samples had zero cache hits; warm samples were all cache hits.
- Cold/warm, stall, health, burst, mixed and Redis-down rows returned valid tool
  data with 100% application success in these measured runs. Peer at 1/8 clients
  also returned valid six-row comparisons. Every row recovered and pending returned to zero.
- **Peer at 32 clients shed work.** Initial success was 25.82%; the diagnostic
  repeat was 11.75%. Raw errors explicitly report `p shed: server busy (50 calls
  outstanding)`. These are application failures, not transport successes.
  This is a capacity limit protected by the existing admission policy; the
  benchmark deliberately exits nonzero for such a result. No 100%-success claim is made.
- The peer fixture completed six 20ms legs with peak physical provider concurrency
  bounded at three; this is runtime evidence, not evidence of real-provider latency.
- Redis-down stops the labelled disposable container during requests, verifies
  it was active before injection and records client inactive/backoff afterward.
  Tools remained available. The container is restarted in finally; immediate
  tool recovery uses the memory tier while the normal Redis backoff remains.
  Redis reconnection latency after backoff is not claimed as measured.
- Health probes target the wrapper state endpoint, not the production auth/health
  middleware. All probes returned HTTP 200, but latency is retained in the raw
  evidence and is not an SLA or proof of zero event-loop delay.
  - clients=1: 118 probes, p95=44.53ms, max=74.49ms.
  - clients=8: 61 probes, p95=415.89ms, max=502.54ms.
  - clients=32: 22 probes, p95=1784.65ms, max=1927.89ms.
- RSS and thread-count telemetry under load were not collected. Physical-work
  bounds/cancellation paths are covered separately by Event-based regressions.
- PostgreSQL quota stress and live-provider behavior are not exercised by this harness.

## Reproduction

From the repository root, use a separate baseline checkout/archive for
`565ec6fbd4a2a89b8eed3a289509a1a0fe43efe4`. Start a disposable Redis with a
fixed unused loopback host port, then start candidate and baseline wrappers:

```bash
docker run -d --name ot-bench --label opentrading-bench=1 -p 127.0.0.1:16380:6379 redis:7-alpine
REDIS_URL=redis://127.0.0.1:16380/0 MCP_BLOCKING_SLOTS=3 .venv/bin/python scripts/_bench_serve.py --port 8767
# In another terminal, point the same wrapper at the baseline src:
BENCH_SOURCE_ROOT=/path/to/baseline/src REDIS_URL=redis://127.0.0.1:16380/0 MCP_BLOCKING_SLOTS=3 .venv/bin/python scripts/_bench_serve.py --port 8768
# Candidate main selection:
.venv/bin/python scripts/load_bench_http.py --port 8767 --scenarios cold,warm,stall,health-under-load,peer --levels 1,8,32 --output candidate-main.json
# The peer/32 overload result can make that command exit 1; inspect the saved rows.
.venv/bin/python scripts/load_bench_http.py --port 8767 --scenarios burst,mixed,redis-down --levels 8 --redis-container ot-bench --output candidate-extra.json
.venv/bin/python scripts/load_bench_http.py --port 8768 --scenarios cold,warm --levels 1,8,32 --output baseline-main.json
```

Use unused ports. Stop the wrappers and remove only the disposable container after
use. A smoke command can set `--warmup-seconds 0.2 --sample-seconds 1`; its rows
are labelled smoke. The driver validates the disposable label before Docker stop/start.

## Raw artifacts

`benchmark-evidence/summary.json` contains every aggregate row, configuration,
recovery snapshot, health probe and SHA-256 checksums. Full per-request records
are committed as deterministic `.json.gz` files to keep evidence compact. Read with:

```python
import gzip, json
with gzip.open("plans/full-review-2026-10-25/benchmark-evidence/candidate-main.json.gz", "rt") as f:
    report = json.load(f)
```
