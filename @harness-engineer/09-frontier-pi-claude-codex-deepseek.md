# 09 — Frontier: Pi / Claude Code / Codex / DeepSeek nhìn qua 5 subsystems

Khung chung: Instructions, Tools, Environment, State, Feedback (+context/observability/handoff/loops).

## Pi — minimal kernel + programmable extensions

Định vị minimal harness, core nhỏ, trả control: Ask Pi to build what you want, or install package does it your way.
4 lớp customizable: Extensions (TS hooks lifecycle), Skills (packages on-demand), Prompt templates (/name expand), Themes (TUI). Core loop reason→tool→observe nhưng mở programmatic (print/JSON/RPC/SDK) để CI drive — tiền đề loop L13.
- Instructions: AGENTS.md tầng global `~/.pi/agent/`→parent→`./AGENTS.md` (+CLAUDE compat) + SYSTEM.md replace/append minimal — tránh giant L04 bằng minimal+split+on-demand.
- State/Context mạnh nhất: programmable compaction (auto overflow/retention, giữ ~20k gần nhất, summarize chain, custom topic/code-aware/model khác), dynamic context (inject/filter/RAG/memory trước mỗi turn `agent/pre-step`), session tree (cây lịch sử 1 file, /tree quay node, export HTML/gist).
- Tools 2 lớp: Skills (standard, progressive disclosure, cache-friendly) + Extensions (intercept dangerous cmd, checkpoint, protect .env, modify output, watcher/webhook/CI; community skill-router/summary/patterns/telemetry).
- Feedback không gate cứng, dựa AGENTS + VISION/PROGRESS/LESSONS/STANDARDS.md community.
Map: Instructions TB (user tự viết), Tools/State rất mạnh programmable, Env/Feedback mở phụ thuộc user.

## Claude Code — complete runtime

While đơn giản nhưng code quanh loop: permission, compaction, extensions, orchestration, storage — harness quyết reliability.
- Instructions layered memory: org `/etc/claude-code/CLAUDE.md`→user `~/.claude/`→project `./CLAUDE.md`→local `CLAUDE.local.md` (gitignore) + subdir on-demand + auto memory (tự ghi từ corrections, share cross-worktree, ≤200 lines/25KB). Specific sau trong context — đáp L04.
- Context 5-layer funnel: lossless pruning tool results → structured distillation → LLM summary lossy + circuit breaker. Storage append `history.jsonl` + /resume/fork, /compact//clear//init (auto gen CLAUDE.md).
- Tools tách trách nhiệm: CLAUDE what, Skills SKILL.md how, MCP JSON-RPC where, Hooks Pre/Post/Stop when enforce, Plugins/Subagents delegate.
- Feedback 2 tracks: permission 7 modes + ML classifier (low allow high confirm/deny) + PostToolUse ép check + Stop chặn premature victory + subagents sidechain isolation không phình parent.
Map: Instructions benchmark, Tools mẫu mực, State reference long-running, Feedback deterministic.

## Codex — repo-as-truth + directory page + worktree

Triết lý cực hạn, đúc từ >1M dòng toàn Codex vài tuần.
- Instructions textbook: AGENTS.md directory page ~100 lines không phải encyclopedia, knowledge trong docs/ structured, AGENTS chỉ point, enforce invariants không micromanage, mechanically checkable coverage/freshness/ownership.
- Context Write-Select-Compress-Isolate: Write persist ra file, Select đọc on-demand theo map, Compress auto/manual /compact + custom prompt, Isolate subagents biên khác, + `build_environment_update_item` chỉ delta CWD/branch/filesystem.
- Tools/Boundaries: mỗi task 1 git worktree + observability (logs/metrics/traces) — boundary bằng môi trường không xin bằng lời (L07). Subagents spawn/wait core tools, inherit AGENTS context riêng, `.codex/agents/*.toml` multi-model.
- Feedback: verify commands trong spec, tests/CI/docs/observability do Codex sinh executable, approval + plan mode giữ human trước high-risk.
Map: Instructions give map not manual, Env signature worktree, Tools boundaries cứng, State convention, Feedback default. Đối lập Claude: Claude cộng (nhét core), Codex trừ (restraint đẩy về convention).

## DeepSeek dsh — everything-plugin + seams + event pipeline

Preview 08/2026, hỏi: harness standalone độc lập model được không? Core Cordis chỉ load/unload/deps/events, zero capability, no privileged core, ngay loop replaceable (mix DeepSeek+Claude subagents+remote sandbox+custom memory/loop/UI).
- Seam 3 lớp Definition→Provider→Consumer (VD FS: Local/E2B/Remote cùng surface, switch không đổi model; Shell/Sandbox/Web/LLM/SubAgent tương tự) — depend interface không phải concrete.
- Event pipeline thay LLM→tool đơn: turn/start→claim→assemble→pre-step→step/start→request→llm/stream→message→tool/call→pre-execute (permission/guard)→execute→post→result→step/end→next, persistent session events vs extension points — perms/memory/logs như listeners không hardcode.
- Constraint Model-visible means logged: gì vào request phải reconstructable từ log, invariant enforce, append-only replayable — observability first-principle L11/L12.
Map: Instructions plugin-injected linh hoạt thiếu convention, Tools seam chuẩn cực hạn, Env pluggable toàn phần, State log-first, Feedback event-based. Tradeoff flexibility cao → config cost cao, OS design.

## Rút ra cho MCP-server

- Học Pi: giữ core nhỏ, extensions/mcp programmable, compaction + session tree.
- Học Claude: layered AGENTS + hooks chặn premature + subagents isolate + permission modes.
- Học Codex: AGENTS ~100 dòng point docs/, mỗi parallel 1 worktree, verify trong spec.
- Học DeepSeek: depend capability interface (Local/E2B/Remote FS, sandbox), event log replayable.
Chi tiết gốc: `upstream/docs/en/harness-designs/{pi,claude-code,codex,deepseek}/index.md`.
