# 00 — Tổng quan: Model giỏi ≠ Chạy ổn, Harness làm cho Reliable

## 1. Câu chuyện gốc

Anthropic làm thí nghiệm kiểm soát: cùng model `Opus 4.5`, cùng prompt `build a 2D retro game editor`:
- Không harness: 20 phút, `$9`, game không chơi được.
- Full harness (`planner + generator + evaluator`): 6 giờ, `$200`, game chơi được thật.

OpenAI với Codex: cùng model trong repo harness tốt đi từ `unreliable` → `reliable`. Không phải cải tiến biên, mà nhảy về chất.

Kết luận: **model quyết định viết code gì, harness quyết định khi nào/ở đâu/viết thế nào và khi nào được coi là xong.**

## 2. Harness Pattern

```
You --> task --> Agent đọc harness files --> Agent execute
  harness govern mọi bước:
  + Instructions: làm gì, thứ tự nào
  + Scope: một feature một lúc, no overreach
  + State: progress log, feature list, git history
  + Verification: tests, lint, type-check, smoke/e2e
  + Lifecycle: init lúc đầu, clean-state lúc cuối
  --> Agent chỉ dừng khi verification pass
```

## 3. Năm subsystems

| Subsystem | File tối thiểu | Việc duy nhất |
|---|---|---|
| Instructions | `AGENTS.md` hoặc `CLAUDE.md` | Startup path, working rules, definition of done. Ngắn 50-200 dòng, router không phải encyclopedia. |
| State | `feature_list.json`, `PROGRESS.md` (`claude-progress.md` bản cũ) | Feature nào, trạng thái nào, evidence nào, next step nào. |
| Verification | `init.sh` + lệnh docs | Tests/checks agent phải chạy trước khi claim done. |
| Scope | dependencies + done criteria | Chống overreach, half-finished. |
| Lifecycle | `session-handoff.md`, clock-in/out routine | Session sau restart được. |

Thiếu 1 trong 5 là harness incomplete.

```
┌────────────────────────────────────────────────┐
│ HARNESS: Instructions | State | Verification   │
│          Scope | Session Lifecycle             │
│ MODEL viết code. HARNESS govern reliability.   │
└────────────────────────────────────────────────┘
```

## 4. Agent Session Lifecycle 16 bước (học thuộc)

```
START:
1. Đọc AGENTS.md / CLAUDE.md
2. Chạy init.sh (install, verify, health)
3. Đọc PROGRESS.md (lần trước xảy ra gì)
4. Đọc feature_list.json (gì done, gì next)
5. Check git log (changes gần nhất)
SELECT:
6. Pick đúng ONE unfinished feature
7. Chỉ làm feature đó
EXECUTE:
8. Implement
9. Chạy verification (tests, lint, type-check)
10. Fail: fix + rerun. Pass: record evidence
WRAP UP:
11. Update PROGRESS.md
12. Update feature_list.json
13. Ghi rõ gì còn broken/unverified
14. Commit (chỉ khi safe to resume)
15. Để lại clean restart path
```

Không harness, bước 9 thành `agent thấy ổn`. Có harness, bước 9 là `tests pass, lint clean, types check`.

## 5. Không harness vs Có harness (multi-session)

- Không: S1 viết code → break tests → claim done → bạn fix tay. S2 quên hết → redo/sai hướng → bạn fix tiếp. Bạn tốn thời gian hơn tự làm.
- Có: S1 đọc instructions → init → 1 feature → verify → log → commit clean. S2 đọc log → pickup đúng chỗ → tiếp tục. Bạn review, không rescue.

## 6. Map nhanh sang MCP-server

```
MCP-server/
├── AGENTS.md (sẽ tạo: overview PG16+Redis7, transports stdio/HTTP/sse, presets <50 tools, TZ Asia/Ho_Chi_Minh)
├── init.sh (uv sync + pytest + serve smoke)
├── feature_list.json (theo preset market/scan/quant/brief/intel)
├── PROGRESS.md + DECISIONS.md + session-handoff.md
└── src/ (code thật)
```

Bốn file là session đã ổn hơn hẳn prompt-only. Chi tiết ở `12-lo-trinh-build-harness-cho-MCP-server.md`.

## 7. Thuật ngữ phải nhớ

- `Capability Gap`: benchmark 50-60% SWE-bench Verified ≠ task thật mơ hồ.
- `Verification Gap`: confidence ≠ correctness.
- `Harness-Induced Failure`: model đủ sức nhưng harness thiếu.
- `Definition of Done`: điều kiện verify bằng lệnh.
- `Diagnostic Loop`: Execute → observe → attribute to layer → fix layer → re-execute.
