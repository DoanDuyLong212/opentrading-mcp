# 05 — Xác minh (L09-L10): Chống victory sớm, e2e thay đổi kết quả

## L09 — Why Agents Declare Victory Too Early

**Case password-reset:** agent sửa schema+viết API+email template, unit xanh báo done. Thực tế: email config thiếu, migration nửa chừng inconsistent, e2e chưa chạy lần nào.

**Gốc khoa học:** Guo et al. ICML 2017 — modern nets systematically overconfident. Agent cảm thấy xong nhưng còn xa. Harness thay cảm giác bằng execution-based verification.

- `Premature Completion`: khẳng xong nhưng spec chưa thỏa. Agent đánh local confidence, system cần global verification.
- `Calibration Bias`: task đa-file bias dương mạnh.
- **Unit pass ≠ done:** isolation+mock nên mù system:
  - Interface Mismatch: renderer relative vs preload absolute, mock riêng pass, e2e lộ.
  - State Propagation: migration đổi schema ORM cache cũ, mock fresh không thấy.
  - Env Dependency: test mock xanh, real thiếu config/latency/down đỏ.
- `Refactor while we're at it` (Claude Code pattern): chưa verify core đã refactor/optimize/style → dịch verified boundary, phá code đúng. Knuth: premature optimization root of evil.
- Self-eval bias (Anthropic 2026): agent tự chấm luôn lạc quan, nhất task chủ quan `polished`. Fix: separate worker/checker, evaluator độc lập nitpicky. Opus 4.5 bare 20m/$9 unresponsive vs planner+generator+evaluator Playwright 6h/$200 playable.

**Three-layer, đúng thứ tự, no shortcut:**
```markdown
## Definition of Done
- Feature complete = e2e passed, not code written
- 1 Unit pass, 2 Integration pass, 3 e2e pass
- Fail L1 không sang L2, fail L2 không sang L3
```
- L1 Syntax/Static: lint/typecheck. Rẻ nhất, ít info nhất, phải pass.
- L2 Runtime: tests+startup, app tới ready, critical path chạy. Không chỉ written mà runnable.
- L3 System: full user flow, integration, scenario. Không chỉ runnable mà correct.
- Priority: correctness → performance → style. Cấm refactor khi core chưa verified.

**Repair instructions (OpenAI Codex):** error cho agent phải kèm cách sửa:
```text
Test failed POST /api/reset-password 500. Check email env vars. Template at templates/reset-email.html.
```
Capture runtime signals: ready? critical path? DB/file side effects đúng? temp cleaned? Case trên harness bắt start full app + execute flow + verify DB consistency → phát hiện trong session, rẻ hơn 5-10x hậu kỳ.

## L10 — Why E2E Changes Results

**Case export Electron:** renderer+preload+service unit pass báo done. Click thử path sai, progress không respond, file lớn leak. 5 boundary defects unit miss hết.

Blind spots isolation: interface mismatch, state propagation, resource lifecycle (handles/connections/sockets, unit tạo/hủy riêng không thấy leak), env packaged permission/config khác.

| Defect | Unit | E2E |
|---|---|---|
| Path format | Miss | Caught |
| IPC progress | Miss | Caught |
| Handle leak | Miss | Caught |
| Packaged perms | Miss | Caught |
| Service err to UI | Miss | Caught |
Trade 2s→15s, chấp nhận được. Sâu hơn: biết bị e2e validate, agent hỏi upstream interface, tôn boundaries, xử error paths.

**Điều kiện e2e là boundaries rõ.** Agent copy mọi pattern kể cả inconsistent → drift mỗi session. OpenAI Layered: `Types->Config->Repo->Service->Runtime->UI`, forward only, cross-domain qua Providers, enforce lint. `Enforce invariants; don't micromanage`.

**Executable checks:**
```bash
grep -r "require('fs')" src/renderer/ && exit 1 || echo "OK"
```
```json
{"id":"no-direct-fs-in-renderer","scope":["src/renderer/"],"WHAT":"Found fs in App.tsx:12","WHY":"Renderer no Node APIs","FIX":"Move to src/preload/file-ops.ts via window.api.readFile()"}
```
```markdown
## Validation Hierarchy
- L1 Unit Must pass
- L2 Integration Must pass
- L3 e2e Must pass when cross-component
- Skip required = Not Complete
```

**Review-to-automation promotion:** mỗi category lỗi lặp (renderer import fs) → (1) thêm check, (2) message bảo move to preload, (3) vào harness fail ngay lần sau. Một tháng harness mạnh hẳn. Mỗi defect thành phòng tuyến vĩnh viễn. Error phải WHAT/WHY/FIX để self-correct không human.
