# Harness Engineering — Giáo trình tiếng Việt chi tiết (0→1)

Thư mục này chứa toàn bộ kiến thức từ `walkinglabs/learn-harness-engineering` đã được dịch/giảng lại tiếng Việt, **không làm xáo trộn code hiện tại**.

- `upstream/` — bản clone `--depth 1` gốc để đối chiếu (không sửa).
- `00-tong-quan.md` — harness là gì, 5 subsystems, lifecycle 16 bước.
- `01-nen-tang-L01-L02.md` — vì sao model mạnh vẫn fail, harness thực sự là gì.
- `02-repo-va-chi-dan-L03-L04.md` — repo là source of truth, tách file hướng dẫn.
- `03-phien-va-khoi-tao-L05-L06.md` — continuity đa session, init phase.
- `04-pham-vi-va-feature-list-L07-L08.md` — WIP=1, VCR, feature_list primitive.
- `05-xac-minh-L09-L10.md` — chống victory sớm, 3-layer + e2e + arch-rules.
- `06-quan-sat-va-trang-thai-sach-L11-L12.md` — observability, clean-state.
- `07-loop-engineering-L13.md` — goal/timer/maker-checker loops.
- `08-graph-engineering-L14.md` — nodes/edges/state/routing.
- `09-frontier-pi-claude-codex-deepseek.md` — 4 harness production.
- `10-du-an-P01-P08.md` — chuỗi 8 projects Electron và cách map sang MCP-server.
- `11-cong-cu-harness-creator-audit.md` — create/validate/benchmark + audit-harness.sh + templates.
- `12-lo-trinh-build-harness-cho-MCP-server.md` — plan build từ đầu cho repo này (Python, PG16+Redis7, MCP presets).

## Cách học đề xuất

1. Đọc `00` → `06` theo thứ tự (mỗi file ~15-25 phút).
2. Đọc `07`, `08` khi muốn tự động hoá.
3. Đọc `09` để thấy production làm thế nào.
4. Làm theo `12` để build harness thật cho `MCP-server`.
5. Đối chiếu `upstream/docs/vi/` khi cần bản dịch gốc, `upstream/docs/en/` khi cần chi tiếtAnh.

## Quy ước

- Giữ nguyên tên file/lệnh tiếng Anh trong code block: `AGENTS.md`, `feature_list.json`, `init.sh`, `PROGRESS.md`, `make check`, `verify-feature.sh`.
- Giải thích tiếng Việt, ví dụ map sang `MCP-server` (preset market/scan/quant/brief/intel, `stdio + POST /mcp + /sse`, `Asia/Ho_Chi_Minh`).
- Definition of Done luôn = runtime evidence, không phải confidence.
