# 11 — Công cụ: harness-creator + audit-harness.sh + Templates

## harness-creator skill

Skill tạo/audit/cải thiện harness cho agent hay quên/drift/claim sớm/khởi đầu inconsistent. Core 5 subsystems bản skill: Instructions (AGENTS/CLAUDE startup/rules/DoD), State (feature_list/progress current/evidence/next), Verification (init.sh/cmds tests trước done), Scope (deps/done chống overreach), Lifecycle (handoff/end restartable). First move: inspect hiện có, chỉ hỏi missing không infer (target agent, filename, tolerance, overwrite?), ưu tiên minimal, thêm memory/safety/multi/benchmark khi cần.

**Create:**
```bash
node upstream/skills/harness-creator/scripts/create-harness.mjs --target /path/to/project \
  --agent-file CLAUDE.md --package-manager npm --commands "cmd one,cmd two" --force
# force chỉ sau confirm overwrite
```
Detect stack/manager, sinh AGENTS/CLAUDE + feature_list.json + progress.md + handoff + init.sh (chmod +x INSTALL/VERIFY/START). Xong replace placeholder features. Rules: root ngắn routing+invariants, facts để docs, verify显式 runnable, evidence trước passing, one active trừ ownership boundaries, append/update state không phải chat history, không giấu destructive.

**Audit/Report:**
```bash
node upstream/skills/harness-creator/scripts/validate-harness.mjs --target /path --json --html report.html --min-score 70
node upstream/skills/harness-creator/scripts/render-assessment-html.mjs --target /path
node upstream/skills/harness-creator/scripts/run-benchmark.mjs --target /path --html report.html
```
Báo 5 scores + lowest bottleneck + 2-3 changes đầu, lowest là candidate không phải causality chắc chắn, exit 1 nếu <min. Benchmark self-check scaffold throwaway chứng minh scripts e2e rồi score target + eval coverage. Structural benchmark, hiệu quả thực cần before/after sessions.

References chỉ load khi cần: `memory-persistence`, `skill-runtime`, `tool-registry-safety`, `context-engineering`, `multi-agent`, `lifecycle-bootstrap`, `gotchas`. Checklist: AGENTS/CLAUDE + feature_list + progress + init.sh + optional handoff + evidence/next. Không tạo file được thì đưa exact contents+cmds.

## audit-harness.sh (zero-dep, không Node)

Bổ sung validate-harness.mjs.
```bash
bash upstream/tools/audit-harness.sh /path/to/repo
curl -fsSL https://raw.githubusercontent.com/walkinglabs/learn-harness-engineering/main/tools/audit-harness.sh | bash -s -- /path
```
Check 5 subsystems L03-L12, exit 0 nếu CRITICAL pass else 1. In màu PASS/WARN/FAIL + counters.
- S1 Instructions: tồn tại AGENTS/CLAUDE, 10 dòng đầu what-is-system, verify cmd, MUST/MUST NOT, state refs, staleness/atomic, 50-200 lines router + link docs/ + source/why.
- S2 Tools: settings/MCP scope.
- S3 Env: lockfile CRITICAL, runtime pin, Makefile setup/dev.
- S4 State: PROGRESS CRITICAL + In Progress/Current hash+test/Next, DECISIONS, feature_list id/behavior/verification/state + evidence.
- S5 Feedback: make check/test, verify documented.
- L05 continuity: clock-in/out, anti-rush, commit why.
- L03 ACID repo-as-record.
- L07 WIP=1 + make vcr + VCR passing/activated.
- L08 verify-feature.sh + state machine + granularity.
- L09 DoD + 3 layers + ordering + layers/repair.
- L10 e2e/check-arch/arch-rules WHAT/WHY/FIX + promotion.
- L11 sprint-contract/evaluator-rubric/session-trace/.harness/traces/session-start-end.
- L12 clean-checklist/script/make clean-check + quality-doc + dual cleanup.
Summary Total/Critical/Recommended + What to fix.

## Templates (`upstream/docs/en/resources/templates/` + `skills/harness-creator/templates/`)

AGENTS.md, CLAUDE.md, init.sh (INSTALL/VERIFY/START vars), claude-progress.md (Current Verified State + Session Record), feature_list.json (id/priority/area/title/behavior/status/verification/evidence/notes WIP=1), session-handoff.md, clean-state-checklist.md (5 dims), evaluator-rubric.md (6 dims 0-2 Correctness/Verification/Scope/Reliability/Maintainability/Handoff → Accept/Revise/Block cần tuning 3-5 rounds), quality-document.md (grades A-D per domain/layer + ablation), sprint-contract.md, goal/loop-state/maker-checker templates P07.
Copy 4 core vào root trước, còn lại thêm khi lớn.

Gốc: `upstream/skills/harness-creator/SKILL.md`, `upstream/skills/harness-creator/references/`, `upstream/tools/audit-harness.sh`.
