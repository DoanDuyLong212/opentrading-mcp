# 07 — Loop Engineering (L13): Ngừng prompting, thiết kế vòng lặp

**Ý tưởng:** Loop = thay bạn — người gõ từng bước — bằng system tự prompt agent. Từ inside the loop (gõ/kiểm/gõ) sang outside (định goal+stop trước, review inbox sau, chỉnh rule khi lệch). Đòn bẩy từ viết prompt đúng sang thiết kế loop đúng. Harness L01-L12 làm single-run tin, loop làm continuous-run tự hành.

## /goal — loop đơn giản nhất

3 thành phần: goal (end-state), verification (kiểm bằng gì: test/lint/judge độc lập), stopping (dừng khi goal hoặc budget/max-turns). Khác prompt ở loop until achieved, người phán done là judge độc lập không phải bạn/agent. Tiến hóa: prompt đơn → long-prompt nhiều bước → agent tự reflect nhưng tự victory dễ → tách judge → /goal. Claude/Codex ship /goal đầu 2026 là hội tụ.

## Phân loại — đừng nhầm /goal vs /loop

- Turn-based: bạn gõ tay, chat thường.
- Goal-based (/goal): có finish line, marathon.
- Time-based (/loop, Thread automation): alarm clock, polling N phút, mỗi run độc lập không cộng dồn.
- Event-driven (Routines/API webhook): PR/CI/issue kích, standalone + plugins.
Test 1 câu: có đích không? Có → /goal, không chỉ canh → /loop. Lỗi phổ biến nhồi task có đích vào `/loop 10m "làm tiếp payment"` — mỗi lần từ đầu vì không nhớ state.

## 6 primitives (Osmani 5 blocks + 1 spine)

1. Automations-heartbeat: `/loop` (in-session, chết khi đóng terminal, expire 7 ngày), Desktop scheduled, Cloud Routines (máy tắt vẫn chạy, min 1h, scheduled/API/webhook), GH Actions/cron. Codex Thread (giữ context như /loop) vs Standalone (fresh đổ Triage inbox).
2. Worktrees-isolation: mỗi parallel agent 1 worktree/branch/dir riêng chống collision. Trần thực tế là review bandwidth của bạn.
3. Skills: SKILL.md+scripts/references, gọi `/skill`, load on-demand, trả intent debt.
4. Connectors: MCP → tracker/DB/staging/Slack, mở PR/link/ping CI, chạm tool thật.
5. Sub-agents maker/checker: Explorer→Implementer→Verifier, fail quay Implementer.
6. External State-memory: markdown/board/kanban ngoài window, repo không quên dù model quên.

## Generator/Evaluator split

Model là luật sư giỏi nhất cho output chính nó, chấm mình luôn cao. Fix: supervisor độc lập (/goal), verifier model khác, N skeptics vote. Phải có người không tin bạn.

**Ví dụ Karpathy autoresearch:** 630 dòng 3 files 3 vai: `prepare.py` read-only infra, `train.py` playground, `program.md` methodology (goal val_bpb, constraints VRAM/5p budget, explore hướng, never-stop). Ratchet 9 bước chỉ tiến: đọc hướng→survey→hypothesis→sửa→snapshot→train 5p→evaluate→keep/revert+log results.tsv→tiếp. ~12 exp/h, 700 exp/2 ngày → ~20 cải tiến, nhanh 11% (2.02h→1.8h).

## 4 silent costs

1. Verification debt: looks fine ≠ confirmed, stop phải machine-checkable.
2. Comprehension rot: loop ship nhanh hiểu biết rữa, 80% code agent bạn không đọc.
3. Cognitive surrender: dùng loop tránh hiểu thay vì amplify hiểu.
4. Token blowout: context phình bậc hai theo turns nếu không compaction.
Ladder L1 Goal Runner → L2 Scheduled Single → L3 Multi → L4 Self-Feeding (tự discover next từ state) → L5 Fleet.

## Map MCP-server

- Goal loop: `goal.md` — `scan preset market pass pytest + smoke /mcp`, stop khi green hoặc 20 turns.
- Timer loop: `/loop 30m` check feed Vietstock, found/fixed/false-positive/made-worse/followup.
- Maker-checker: Maker implement tool mới, Checker chạy `pytest + mypy + ruff + smoke transports`, state `loop-state.md`, stop N-pass hoặc max-rounds ≥5 rounds ghi feedback/intervention/ceiling.

Templates: `goal-template.md`, `loop-state-template.md`, `maker-prompt.md`, `checker-prompt.md` trong `upstream/projects/project-07/` và `docs/en/resources/templates/`.
