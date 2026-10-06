# 06 — Quan sát và Trạng thái sạch (L11-L12)

## L11 — Observability Belongs Inside Harness

**Cảnh:** agent 20p sửa đống file báo `done, but 2 tests failing`, hỏi why `not sure timing`, hỏi đổi critical path nào `let me look...`. Không phải capability, thiếu observability. Không có nó: không phân correct vs looks correct (review thấy what written, trace thấy what ran, boundary sai chỉ lộ input đặc thù); evaluation mysticism (cùng output chấm khác nhau); retry blind (sửa sai path đốt tokens); handoff cliff (session mới diagnose 30-50% time, Anthropic long-running).

**Ví dụ dark mode planner-generator-evaluator:** không observability planner vague, generator theo vague, evaluator `doesn't feel right`, retry mù 3-4 vòng 45p. Có full: planner sprint contract (components/standards/exclusions), generator runtime style loading, evaluator rubric evidence `Button 2.1:1 need WCAG AA 4.5:1`. 1 iter 15p chất cao — chênh 3x.

**Hai lớp:**
- Runtime: logs/traces/process/health. Trả lời what system did.
- Process: plans/rubrics/acceptance. Trả lời why accepted.
Agent không tự làm: không biết mình không biết nên log thứ nghĩ quan trọng, format mỗi session một kiểu, contracts/rubrics cần harness support.

**Harness tự thu:** lifecycle (startup/ready/running/shutdown), feature path (entry/checkpoints/exit), data flow, resource bất thường, errors full context.

**Sprint contract trước mỗi task:**
```markdown
# Sprint Contract: Dark Mode
## Scope: toggle, CSS vars, tests
## Verification: visual regression, e2e main, no FOUC
## Exclusions: print, third-party dark
```

**Trace OpenTelemetry:** 1 trace/session, 1 span/task, sub-spans verify, Jaeger/Zipkin. Thực thi `session-trace.sh` JSONL append-only `.harness/traces/`:
```bash
./session-trace.sh --session 2026-09-25-dark-mode --span generator --event "theme-toggle applied" --output .harness/traces/2026-09-25.jsonl
```
Replay decision path như request tracing, tìm bottleneck.

**Evaluator rubric định lượng:**
| Dim | A | B | C | D |
|---|---|---|---|---|
| Correctness | All pass | Main pass | Partial | Build fail |
| Arch | Full | Minor dev | Obvious dev | Serious viol |
| Coverage | Main+edge | Main only | Skeleton | None |

Thí nghiệm Anthropic 03/2026 DAW Web Audio: Planner 4.7m/$0.46, Build1 2h07/$71, QA1 8.8m/$3.24, Build2 1h02/$36.89, QA2 6.8m/$3.09, Build3 10.9m/$5.88, QA3 9.6m/$4.06, total 3h50/$124.7. Planner chỉ scope táo bạo + product context tránh cascade, Generator theo contract, Evaluator Playwright như real user chấm depth/function/visual/code hard threshold, feedback `clips can't drag, no knobs/pads, no EQ` không phải feels wrong. Evaluator ban đầu tự bỏ qua lỗi, phải đọc logs patch QA prompt nhiều vòng mới reliable.

## L12 — Every Session Must Leave Clean State

**Cảnh:** agent cả chiều 20 files commit xong. S2 build broken red tests debug vương feature list chưa update progress mờ → 30p figure out last session did what. OpenAI+Anthropic: long-term reliability = operational discipline, không chỉ single-run.

**Clean 5 chiều (thiếu 1 chưa done):** (1) build passes (CI, không phải my machine), (2) tests pass (cả cũ, không break), (3) progress recorded (machine-readable done+passing criteria/in-progress/not-started, tốt -60-80% startup time), (4) no stale (xóa logs/temp/commented/TODO, giảm cognitive load), (5) startup path (`npm run dev`, init/load/context/select không manual).
```
Work -> Build? -> Tests? -> Record -> Cleanup -> Startup? -> Handoff, fail đâu fix quay Build
```
Ngược lại entropy spiral (Lehman): bẩn → diagnose → sửa trên messy → thêm debug/broken → càng bẩn. OpenAI 5 tháng Codex: agent copy mọi pattern kể cả suboptimal. Common area cốc cà phê. Team từng mất 20% thứ Sáu dọn AI slop — không scale.

Số liệu 12 tuần Electron: không cleanup W1 100%/100%/5m → W4 95%/92%/15m → W8 82%/78%/35m → W12 68%/61%/60m+. Có cleanup W12 97%/95%/9m (chênh 29 build 34 test startup -85%).

**Session Exit Checklist trong CLAUDE.md:**
```markdown
- [ ] Build passes (npm run build)
- [ ] All tests pass
- [ ] Feature list updated
- [ ] No debug (console.log/debugger/TODO)
- [ ] Startup available (npm run dev)
```
**clean-state-check.sh idempotent** (chạy lại cùng kết quả, safe retry):
```bash
rm -f /tmp/debug-*.log
git checkout -- .env.local
npm run build
npm test
npm run dev -- --check-startup
```
```bash
make clean-check
```

**quality-document.md sống:**
```markdown
# Quality
## Auth (A): passing Yes, understandable Yes, stable, compliant, followed
## Payment (C): callback untested, logic 3 files khó, 2 flaky, violations, partial
```
Session mới biết fix thấp nhất, track codebase mạnh/yếu dần.

**Dual-mode:** Immediate mỗi end (refcounting — dọn temp vừa tạo, update list, xanh build/tests, +5p/session nhưng 12 tuần tiết kiệm hàng chục giờ; thực nghiệm 11 vs 103 stale). Periodic hàng tuần (tracing — full scan structural debt, update quality, benchmark drift).

**Simplify harness định kỳ:** component tồn tại vì model chưa tự làm, model tiến bộ giả định lỗi thời. Anthropic bỏ sprint-splitting lên Opus 4.6 (builder 2h không drift mượt hơn), nhưng evaluator vẫn giá trị ở capability boundary. Mỗi tháng disable thử 1 component benchmark, không degrade remove, có restore/lighter. Agent 3.5 PRs/ngày vượt review: fast-merge short-lived, flaky rerun không block — fix cost < waiting cost thì moving fast đúng hơn slow confirm.
