# 12 — Lộ trình build harness từ đầu cho MCP-server (thực chiến)

Hiện trạng: Python `pyproject.toml + uv.lock`, `src/ tests/ configs/` 5 clients, `docker-compose.mcp.yml` PG16+Redis7, `render.yaml`, transports `stdio + POST /mcp + /sse`, presets `<50 tools`, TZ `Asia/Ho_Chi_Minh`. Chưa có AGENTS/feature_list/init/PROGRESS → build mới.

## Step 0 — Baseline (read-only, làm ngay trong @harness-engineer)

```bash
bash upstream/tools/audit-harness.sh /home/doanlong/MCP-server
node upstream/skills/harness-creator/scripts/validate-harness.mjs --target /home/doanlong/MCP-server --min-score 70
```
Ghi lại CRITICAL fail để đối chiếu sau. Không sửa root, chỉ đọc.

## Step 1 — Minimal harness (4 files vào root thật, khi bạn cho phép)

1. `AGENTS.md` ~80-120 dòng:
```markdown
# OpenTrading MCP-server — PG16+Redis7, no Mongo, TZ Asia/Ho_Chi_Minh
## Quick Start: pip install -e ".[dev]" + PYTHONPATH=src pytest tests/ -v
## Transports: stdio default + POST /mcp + /sse fallback
## Presets <50 tools: market/scan/quant/brief/intel/all
## Hard Constraints (MUST):
- MUST tz-aware everywhere, MUST NOT naive datetime
- MUST NOT Mongo, reports PG JSONB thay vietstock_news
- MUST preset <50 tools, MUST verify trước done
## Verify: pytest tests/ -v + opentrading-mcp serve --preset market smoke
## Topic Docs: docs/architecture.md (transports/presets), docs/verification.md, docs/constraints.md
## State: PROGRESS.md, DECISIONS.md, feature_list.json — đọc lúc in, update lúc out
## Scope: WIP=1, one feature/session, VCR=passing/activated
## Lifecycle: clock-in đọc PROGRESS+check, clock-out update+clean-check+commit
```
2. `feature_list.json` theo preset:
```json
[
 {"id":"F01","behavior":"serve --preset market stdio smoke pass","verification":"PYTHONPATH=src pytest tests/ -v + serve smoke","state":"not_started","evidence":""},
 {"id":"F02","behavior":"POST /mcp stateless pass","verification":"curl POST /mcp smoke + pytest e2e","state":"not_started","evidence":""},
 {"id":"F03","behavior":"PG JSONB reports thay vietstock_news","verification":"pytest reports + tz-aware check","state":"not_started","evidence":""}
]
```
Mỗi item completable 1 session, có layers/repair khi cần.
3. `init.sh` fail-fast `set -euo pipefail`: `uv sync/pip install -e .[dev]` + `pytest` + `serve --help` smoke, phân INSTALL/VERIFY/START vars.
4. `PROGRESS.md` + `DECISIONS.md` + `session-handoff.md`: Current State (commit+test), In Progress, Next Steps, Blockers, why (sao PG JSONB, sao preset <50).

## Step 2 — Progressive disclosure

- `docs/architecture.md`: transports, presets matrix, PG/Redis, configs 5 clients, render.yaml.
- `docs/verification.md`: L1 ruff+mypy, L2 pytest+startup, L3 e2e MCP (`stdio + HTTP POST /mcp + /sse`), no-skip.
- `docs/constraints.md`: MUST/MUST NOT + source/why + expiry.
- `src/*/ARCHITECTURE.md` proximity: rule cạnh code.
- Audit: entry 50-200 dòng, link docs/, top/bottom cho critical, middle cấm critical (lost-in-middle).

## Step 3 — Verification gates

- `Makefile`: `setup/test/check/e2e/dev/vcr/verify-feature/check-arch/clean-check/session-start-end`.
- `scripts/verify-feature.sh F=F02`: chạy verification, tự chuyển state → passing, agent không tự sửa.
- `.harness/arch-rules.json` WHAT/WHY/FIX: `no-mongo-import`, `preset-under-50`, `tz-aware-required`, `transports-smoke-required`.
- `scripts/check-arch.sh` grep + exit 1 + FIX cụ thể file/function/env.
- Review-to-automation: mỗi bug review thành rule mới.

## Step 4 — Lifecycle + Observability + Clean

- Clock-in/out trong AGENTS, anti-rush `running low → stop update PROGRESS commit checkpoint`, commit why not what.
- `templates/sprint-contract.md` trước feature (scope/DoD/exclusions), `templates/evaluator-rubric.md` A-D (correctness/arch/coverage/evidence), `scripts/session-trace.sh` JSONL `.harness/traces/` (gitignore traces.jsonl).
- `templates/clean-state-checklist.md` 5 chiều + `scripts/clean-state-check.sh` idempotent + `make clean-check` trước commit.
- `docs/quality-document.md` A-D per module (transports/presets/reports/configs), update khi chạm module.
- Dual: immediate mỗi end + periodic weekly scan drift + simplify harness monthly (disable thử 1 component benchmark).

## Step 5 — Loop → Graph demo

- Goal: `goal.md` scan market green 20 turns.
- Timer: `/loop 30m` feed Vietstock ≥2h metrics found/fixed/false/made-worse.
- Maker-checker ≥5 rounds state `loop-state.md`.
- Graph `graph.md`: State – Research(scan) –plan→ Implement(quant) –code→ Verify(pytest/e2e) –failed→ Implement –passed→ Merge, thiếu info→ Research. Fan-out 5 presets worktree riêng fan-in merge standard. Human approval trước render deploy timeout/auto-reject.

## Definition of Done cho harness này

`audit-harness.sh` CRITICAL pass + `validate-harness` ≥70 + `make check` green + fresh session test 5 câu pass + 1 feature e2e evidence commit. Sau đó ablation: gỡ từng component xem drop, giữ cái matter.

Khi bạn OK, tôi sẽ scaffold Step 1 vào root thật (ngoài @harness-engineer), còn hiện tại mọi giảng dạy vẫn cách ly trong `@harness-engineer/`.
