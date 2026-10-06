# 02 — Repo và Chỉ dẫn (L03-L04)

## L03 — Repository Must Become System of Record

**Câu hỏi:** Kiến trúc nằm ở Confluence/Slack/Jira/đầu senior — agent xoay sao? Không xoay được. Agent chỉ có 3 inputs: system prompts+task, file contents trong repo, tool output. Ngoài repo, nó không biết gì.

> `Information that doesn't exist in the repo, doesn't exist for the agent.` — OpenAI, repo as spec.

Không phải `write more docs`, mà `put decision info in right place`. `ARCHITECTURE.md` 50 dòng trong `src/api/` hữu ích hơn 500 trang Confluence stale. Proximity > length.

**Fresh Session Test (test map đủ tốt không):** mở session mới chỉ cho repo, hỏi:
- Q1 What is this system? → `AGENTS.md/README`
- Q2 How organized? → `ARCHITECTURE.md/module docs`
- Q3 How run? → `Makefile/init.sh/package scripts`
- Q4 How verify? → test/lint/check cmds
- Q5 Where are we? → `PROGRESS.md/feature_list/git history`
Trả lời đủ 5 → new session làm ngay không hỏi human. Blank ở đâu agent đoán ở đó, đoán sai thành bug, mỗi session đoán lại, cost of guessing > cost of drawing map.

**Khái niệm:**
- `Knowledge Visibility Gap`: % knowledge không nằm trong repo. Gap lớn → fail cao.
- `Discovery Cost`: context budget đốt để tìm 1 info. Critical info phải ở nơi thấy đầu tiên, không chôn 10 levels.
- `Knowledge Decay`: docs drift khỏi code. Out-of-date docs nguy hiểm hơn no docs.
- ACID cho agent state:
  - Atomicity: 1 logical op (endpoint+tests) commit as a whole khi verified, fail thì discard.
  - Consistency: predicate `make check exits 0`, inconsistent không commit.
  - Isolation: multi-agent thì file riêng/branch riêng, tránh race cùng file.
  - Durability: critical knowledge trong git-tracked files, memory chỉ là temp.

**Vẽ map tốt (4 principles):**
1. Knowledge lives next to code: rule auth nằm cạnh API code, mỗi module dir có short doc responsibilities/interfaces/constraints.
2. Standardized entry: `AGENTS.md` 50-100 dòng trả lời What/How run/How verify.
3. Minimal but complete: rule nào remove mà decision quality không đổi thì bỏ. Nhưng 5 câu fresh test phải có answer.
4. Update with code: docs trong module dir, sửa code tự thấy doc, CI remind check docs.

```
project/
├── AGENTS.md
├── src/api/ARCHITECTURE.md
├── src/db/CONSTRAINTS.md
├── PROGRESS.md
└── Makefile (setup/test/lint/check)
```

**Case e-commerce 30 microservices:** decisions rải Confluence stale/Slack/đầu senior/comments sporadic → agent 70% cần human vì violate implicit constraint. Fix: root `AGENTS.md` + mỗi service `ARCHITECTURE.md` + `CONSTRAINTS.md` MUST/MUST NOT + `PROGRESS.md` → fresh session answer được, quality lên rõ.

Tool chấm: `upstream/.../lecture-03-.../code/repo-reader.ts` — 8 criteria 100 điểm (AGENTS 15, docs 10, arch 15, feature_list 15, handoff 15, tests 10, config 10, README 10). Chạy `npx tsx repo-reader.ts [path]`.

## L04 — Why One Giant Instruction File Fails

**Câu hỏi:** `AGENTS.md` 50→300→600 dòng, sao agent càng tệ? Vicious cycle: lỗi → add rule → tạm ổn → lỗi khác → add tiếp.

**5 thứ hỏng:**
- Context budget eaten: window 200K, file 10-20K tokens, cộng source files + tool output + history → cạn khi cần hiểu code.
- Lost in the Middle (Liu et al. 2023): LLM dùng info giữa long text kém đầu/cuối. Rule `parameterized queries` ở dòng 300/600 gần như bị ignore.
- Priority conflicts: hard (`never eval()`), guideline (`prefer functional`), lesson (`fixed WebSocket leak last week`) trông identical, agent không phân red line vs suggestion.
- Maintenance decay: chỉ grow never shrink, xóa sợ break, thêm thấy free → SNR decline như tech debt.
- Contradiction: `strict mode` vs `legacy allowed any`, agent pick random.

**Khái niệm:** `Instruction Bloat` (10-15% window là crowd out), `SNR` (relevant/total), `Entry File` 50-200 dòng, `Reveal on Demand/Progressive Disclosure` (overview trước, detail khi cần, như good UI).

**How to Split — router, not encyclopedia:**
- Frequently-needed ở tay, occasionally cất, never-use bỏ.
- Entry giữ: overview 1-2 câu, first-run (`make setup/test/check`), global hard ≤15 rules, links topic docs + applicability condition.

```markdown
# AGENTS.md
## Overview: Python 3.11 FastAPI, PG15
## Quick Start: make setup/test/check
## Hard Constraints: OAuth2, SQLAlchemy2, pytest+mypy+ruff
## Topic Docs:
- docs/api-patterns.md — Required when adding endpoints
- docs/database-rules.md — Required when modifying DB
- docs/testing-standards.md — Reference when writing tests
```

- Mỗi topic 50-150 dòng trong `docs/` hoặc cạnh module. Info nào code tự nói (types, comments, config) thì đừng duplicate.
- Mỗi instruction ghi source/why, when needed, when remove. Audit xóa outdated/contradictory như deps.
- Bắt buộc ở entry thì để top/bottom, never middle. OpenAI: `short and routing-oriented`, Anthropic: `concise and high-priority`.

**Case SaaS 50→600 dòng:** fix bug đốt context vào deploy irrelevant, security rule line 300 ignored (compliance 60%), 3 style rules contradictory. Split về 80 dòng + 3 topic docs → success 45%→72%, compliance 60%→95%.

`Add a rule` là pain relief ngắn hạn, poison dài hạn. Hỏi trước: có nên vào topic doc không?

Đối chiếu: `AGENTS-short.md` (15 dòng tốt), `anti-patterns.md` (xấu), `split-vs-monolithic.ts` (monolithic scan 72-175 lines vs split 22-35 lines, savings rõ).
