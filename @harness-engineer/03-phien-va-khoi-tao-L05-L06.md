# 03 — Phiên và Khởi tạo (L05-L06)

## L05 — Long-Running Tasks Lose Continuity

**Kịch bản:** S1 30 phút gần xong thì cạn context, S2 quên chọn A hay B, file nào sửa, test nào đỏ → mất 15 phút đọc lại, thậm chí lệch hướng.

**Gốc:** context window hữu hạn (128K/200K/1M vẫn cạn). Agent phải hiểu codebase + lưu quyết định + xử output + hội thoại → phình nhanh. Nguy hiểm: suy luận trung gian chứa `why` (sao chọn Redis không phải materialized view), output cuối chỉ còn `what` là code. Compaction giữ `what` mất `why`, session sau thấy code không hiểu ý đồ, optimize mất quyết định có chủ ý.

Không persistence: `S1 half-done → S2 fresh → re-read/rerun/guess → drift`. Có persistence: `S1 → PROGRESS+DECISIONS+notes+commit → S2 rebuild → resume nhanh`.

**Bộ 4 món chuẩn:**
1. `PROGRESS.md`: latest commit, test status `42/43 passing`, lint, `Completed/In Progress/Known Issues/Next Steps`.
2. `DECISIONS.md`: `what/why/when`, ví dụ `2024-01-15: Use Redis caching - high read - Rejected PG matview - TTL 5m`.
3. Git commit checkpoint: mỗi atomic unit xong là commit, message giải why.
4. Clock-in/out trong `AGENTS.md`:
   - In: `Read PROGRESS`, `Read DECISIONS`, `Run make check`, tiếp từ Next Steps.
   - Out: `Update PROGRESS`, `Run make check`, `Commit completed`.

Mẫu: `code/session-handoff.md` (Completed/Broken-Next Best Step), `continuity-checklist.md` (fresh agent <5 phút hiểu recent work?), `session-simulator.ts` (No handoff S-B làm lại step 1-6, With handoff start từ step 4).

**Context anxiety (Anthropic 03/2026, Sonnet 4.5):** gần đầy window agent `rushed finish` — bỏ verify, chọn easy thay vì optimal. Compaction giữ what mất why, không hết anxiety. Reset mở session mới sạch tâm lý nhưng phụ thuộc handoff. Sonnet 4.5 phải reset, Opus 4.5 compaction có thể đủ → harness phải theo model.

Số liệu blog 12 points/5 sessions: không persistence 7/12 xong, defect ẩn 43%, rebuild 15p; có persistence 12/12, defect 8%, rebuild 3p (-78%).

## L06 — Initialization Needs Own Phase

**Anti-pattern:** mở session bảo `add search` luôn, 20p mới biết test framework chưa config, 10p sửa, migration sai format. Thời gian vào figuring out, không phải feature.

**Triết lý:** init và implement tối ưu khác nhau. Init maximize reliability cho mọi session sau, implement maximize feature verified. Trộn thành đa mục tiêu, agent thiên viết code (hữu hình) bỏ hạ tầng (giá trị ở session sau) → hạ tầng nửa vời, test có mà chưa pass, lint lỏng, không progress file, S1 nhớ mang máng thấy ổn, S2 sụp.

**4 hệ lụy trộn:** hạ tầng không chắc; `unverified accumulation` (code trước test, sau đập đi); waste context (init ăn budget, S1 nửa feature nửa init); `assumption landmines` (S1 chọn Vitest không ghi, S2 mang Jest, 2 frameworks, maintenance x2). Anthropic: init riêng completion multi-session +31%, thu hồi trong 3-4 sessions. Codex: `repository as operational record`.

**Dedicated phase — S1 chỉ hạ tầng, không business:**
1. Runnable env: `npm install` xong, app chạy.
2. Verifiable test framework: ít nhất 1 example test pass.
3. Readiness checklist: `make setup/dev/test/check`, Current State, Structure `src/... tests/...`.
4. Task breakdown có thứ tự + acceptance (`Task1 JWT middleware - Acceptance: pytest tests/test_auth.py pass`).
5. Git checkpoint sạch.

**Thực thi fail-fast:**
```bash
set -euo pipefail
echo "[init] installing"
npm install
# startup optional, project-specific here
```
Nâng cao `init-check.ts` theo Runtime/Config/Deps/Toolchain/Structure/VC: Node>=18, package.json, node_modules, tsc, tsconfig, src/, tests/, git. Mỗi check kèm `impactIfMissing`. Demo `simulateWithoutInit` lỗi muộn 200ms/lỗi + fail, `simulateWithInit` chặn upfront 0 waste.

**Acceptance init (không phải bao nhiêu code):** `make setup from scratch ok`, `make test ≥1 pass`, session mới đọc repo biết run/test, breakdown ≥3 tasks, everything committed. Case React+Vitest: trộn S2 mất 20p suy luận (+60% rebuild), init riêng rebuild <3p.
