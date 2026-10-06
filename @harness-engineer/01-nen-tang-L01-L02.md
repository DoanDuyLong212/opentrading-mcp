# 01 — Nền tảng (L01-L02): Vì sao agent mạnh vẫn fail, Harness thực sự là gì

## L01 — Why Capable Agents Still Fail

**Câu hỏi:** Đổi model đắt hơn có xong không? Không, hãy nghi harness trước.

**5 failure modes:**
1. `Vague requirements`: `Add search feature` — search gì? full-text? paginate? highlight? Không rõ agent đoán, đoán sai rework gấp nhiều lần.
2. `Implicit conventions`: team dùng `SQLAlchemy 2.0`, `OAuth 2.0` nhưng rule nằm trong đầu/Slack cũ. Agent chưa từng thấy thì không tuân được.
3. `Incomplete env`: thiếu dep, sai version, agent đốt context vào `pip install`/Node version.
4. `No verification`: không test/lint hoặc có mà không nói. Agent ngó thấy ổn rồi claim done. Thêm `context anxiety`: gần cạn context agent vội kết thúc, bỏ verify.
5. `Cross-session loss`: session trước mất hết, session mới explore lại, task >30 phút fail vọt.

**Ví dụ FastAPI 15k LOC:** prompt `add user preferences endpoints under /api/v2/users` → agent đốt 40% context explore, sai error-handling, SQLAlchemy cũ, runtime error vẫn claim done. Thêm `AGENTS.md` + `pytest tests/api/v2/ && mypy src/` + ADR → cùng model pass 3/3 runs, context hiệu quả hơn ~60%.

**Million-Line Experiment (OpenAI 2025):** 3 engineers, chỉ Codex viết, 5 tháng ~1M LOC, 1500 PRs (3.5 PR/người/ngày). Chậm lúc đầu vì thiếu tools/structures, không phải Codex dở. Pattern: chẻ mục tiêu lớn thành `design/code/review/test` blocks nhỏ cho agent lắp.

**Thực hành ngay:**
```text
Completion criteria:
- GET /api/search?q=xxx, paginate default 20
- Include highlighted snippets
- pytest pass, mypy --strict pass
```
+ `AGENTS.md` ở root ghi stack/conventions/verify commands. ROI cao hơn nâng model. Sau đó log failure theo layer: spec/context/env/verify/state để tìm bottleneck.

Code đối chiếu: `upstream/docs/en/lectures/lecture-01-why-capable-agents-still-fail/code/` — `failure-pattern-demo.ts`, `underspecified-task.md`, `failure-signals-checklist.md`.

## L02 — What a Harness Actually Is

**Câu hỏi:** Harness có phải 1 file prompt? Không. Harness = mọi hạ tầng ngoài model weights.

**Analogy nhân viên mới:** ném vào project zero docs, bạn tốn thời gian figuring out thay vì solving. Agent tệ hơn: không hỏi đồng nghiệp được. Nguyên tắc OpenAI: `the repo IS the spec`. Anthropic: persistent state + recovery paths + progress tracking.

**Soi 4 tools:**
- `Claude Code`: đọc `CLAUDE.md`, chạy shell/tests, giữ history. Không nói cách test thì không verify được.
- `Cursor`: `.cursorrules` + terminal + lint, nhưng state yếu, đóng IDE là mất.
- `Codex`: `git worktrees` isolate + logs/metrics/traces, vượt trội trong repo có `AGENTS.md` + verify rõ.
- `AutoGPT`: thiếu state → context phình vô hạn, thiếu feedback → loop. Không phải model dở, harness dở.

**5 subsystems chi tiết:**
- Instruction: `AGENTS.md` gồm overview, stack+versions, first-run cmds, hard constraints, links docs.
- Tool: đủ tool access, `least privilege`. Cấm shell thì agent không `pip install` được.
- Environment: self-describing — `pyproject.toml` lock deps, `.python-version`, Docker/devcontainers reproducible.
- State: `PROGRESS.md` ghi done/in-progress/blocked, update cuối session, đọc đầu session.
- Feedback (ROI cao nhất):
```
Verification:
- Tests: pytest tests/ -x
- Type: mypy src/ --strict
- Lint: ruff check src/
- Full: make check
```

**Nguyên tắc vận hành:**
- `Give a map, not a manual`: ~100 dòng đủ.
- `Constrain, don't micromanage`: `enforce invariants, don't micromanage implementation`. Tách người làm khỏi người check.
- `Remove one at a time and observe` (ablation): giữ model cố định, gỡ từng subsystem xem drop lớn nhất ở đâu. Nhưng ablation chỉ nói valuable nhất right now, muốn locate bottleneck phải xem failure records. Component ~zero impact đừng vội vứt: có thể redundant/poorly-designed/chưa được exercise.
- `Harness rots like code`: audit regularly, trả harness debt như tech debt.

**Story GPT-4o + TS+React 20k LOC:** S1 chỉ README → 20% pass (sai npm/yarn, naming, test). S2 thêm `AGENTS.md` stack/conventions/ADR → 60%. S3 thêm `yarn test && lint && build` → 80%. S4 thêm progress templates → 80-100%. Model không đổi.

Code: `upstream/.../lecture-02-.../code/` — `harness-components.md`, `minimal-harness-loop.ts` (loop messages→tool→messages), `harness-vs-no-harness.ts` (không harness task nào cũng pass dù không nên pass).
