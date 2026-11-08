# Kế hoạch: Nâng cấp opentrading-mcp lên vnstock thế hệ 6

Ngày: 2026-11-08 · Hạn chót nguồn cũ: 2026-11-10 (gen 4/5 ngừng xác thực)
Nguồn quyết định: https://vnstocks.com/docs/vnstock/v6/chuyen-doi/tu-the-he-5 (v6.0.0rc4)

## Bối cảnh

- Dự án pin vnstock **4.0.2** trong `.venv` (`uv.lock`); `pyproject.toml` khai `vnstock>=3.0`.
- Gen 6 (`vnstock>=6.0.0rc1,<7` + `vnstock-oapi` + `vnstock_quant>=1.0.0rc1,<2`) cài từ
  `--extra-index-url https://vnstocks.com/api/packages`, vẫn RC, cần venv riêng vì trùng tên gói.
- Lớp gen 4 `Quote/Listing/Company/Finance/Trading/Vnstock` **bị xoá** ở gen 6 (ImportError);
  nguồn ngầm `VCI/KBS/MSN` không còn. Ba lớp chính: `Market`, `Reference`, `Fundamental`.
- Người dùng đã chốt: nguồn **fhsc + ssi**; chụp mốc parity từ v4 ngay; `vn_retail_fx` đổi sang
  `Market().forex`.

## Ràng buộc toàn cục

- Không đụng `main`; toàn bộ sửa trên nhánh `feat/vnstock-gen6`.
- Suite offline (`pytest`) phải xanh ở mọi commit — tests stub vnstock, không gọi live trong CI.
- Không gộp sửa công thức nghiệp vụ vào PR nâng cấp (anti-pattern đã ghi trong `plans/`).
- Giữ unit nến = nghìn đồng, bảng giá = đồng (đúng như gen 6 quy ước; `units.py` đã phản ánh).
- Khoá nguồn KHÔNG commit: chỉ qua `.env`/env vars.

## Task 1 — Chụp mốc parity từ v4.0.2 (khẩn, trước 10/11)

**Làm:** Script `scripts/parity_baseline.py` gọi qua adapter hiện tại: `quote_history`
(FPT, VCB, SSI, VNINDEX), `equity_quote_batch` (5 mã), `listing_symbols`, `equity_ratios`
(FPT, VCB, SSI), `equity_fundamentals` (cash_flow FPT), `reference_equity`, `company_info`
(detail FPT), `insider_trading`, `corp_events`, `msn_fx_gold`, `index/futures/forex/crypto`
OHLCV. Ghi JSON vào `tests/fixtures/parity_v4_<ngày>/` kèm `meta.json` (phiên bản, thời điểm).
Chạy bằng `.venv` hiện tại. Commit script + fixtures.

**Kết quả mong đợi:** thư mục fixture có ≥ 10 tệp JSON; script chạy lại được (idempotent, retry 2 lần).

## Task 2 — Môi trường gen 6 cách ly + thăm dò API

**Làm:** Tạo `~/.venv_6x`; cài như trên; chạy `vnstock version`, `vnstock doctor`,
`vnstock keys` (kỳ vọng: thiếu khoá fhsc/ssi chỉ là cảnh báo). Nội soi API bằng
`vnstock doc`/`show_api()`/`help()` cho: `Market().equity().ohlcv/trades/quote`,
`Market().index/.futures/.forex/.commodity/.crypto`, `Reference().equity.list`,
`Reference("ssi").index("VN30").members()`, `Reference().industry.*`,
`Reference("fhsc").company(...)`, `Fundamental("fhsc").equity(...)` 3 báo cáo.
Ghi chữ ký thật vào `notes-v6-api.md` trong SDD workspace.

**Kết quả mong đợi:** venv tạo được; chữ ký hàm khớp/điều chỉnh bảng ánh xạ trong plan.

## Task 3 — Adapter `providers/vnstock.py`: nguồn + ohlcv + guard thứ tự dòng

**Làm (TDD):**
1. Test mới (RED): `tests/test_vn6_adapter.py` — stub gen-6 classes; khẳng định
   (a) `quote_history` sắp xếp tăng dần theo `time` kể cả khi frame trả về giảm dần,
   (b) mọi lời gọi truyền `source` thuộc {fhsc, ssi, binance, fmp} theo nhóm,
   (c) fallback nguồn bỏ "VCI"/"KBS".
2. Sửa adapter: `Quote(...).history` → `Market(<nguồn>).equity().ohlcv(start, end, interval)`;
   `Listing().all_symbols()` → `Reference(<nguồn>).equity.list(exchange=...)`;
   `Market().index/.futures/.forex/.crypto .ohlcv` giữ cấu trúc, `count/resolution` →
   `interval/count_back` (chuẩn hoá `1D/1W/1M` phân biệt hoa thường);
   `Company(...)` → `Reference("fhsc").company(...)` (bỏ `.officers()` nếu không có — verify Task 2);
   `Finance(...).cash_flow` → `Fundamental("fhsc").equity(...).cash_flow`.
3. `ensure_api_key`/`quota_info`: bỏ `change_api_key` + `vnai.beam.auth` → trạng thái khoá
   nguồn từ env (`FHSC_API_KEY`, `SSI_API_KEY(_SECRET)`).

**Kết quả mong đợi:** test mới RED→GREEN; suite xanh.

## Task 4 — `ratio()` → `vnstock_quant.fa.ratios()`

**Làm (TDD):** test stub `vnstock_quant.fa` khẳng định `equity_ratios` dựng `fa.Dataset`
từ 3 báo cáo (year+quarter) và trả long records (symbol, period, id, value, unit, reason);
xử lý `MISSING_INPUT`/`NOT_APPLICABLE` thành record có `reason`. Cập nhật
`tools/vn.py::vn_fundamentals` (tham số `report_type` không còn — map sang period),
`financial_contracts.py` (chuỗi source), ngưỡng screener đổi định nghĩa:
`RT_LEV_FINANCIAL_LEVERAGE`→`RT_LEV_DE`, `RT_EFF_CASH_CYCLE`, `RT_VALUE_EQUITY` (đổi đơn vị).

**Kết quả mong đợi:** RED→GREEN; suite xanh.

## Task 5 — Bỏ import nội bộ `vnstock.api.quote`

**Làm:** `tools/cycle_stats.py::_fetch_range`, `tools/asset_cycle.py::_vci_close` đổi sang
adapter `vn_p.quote_history`-style fetch (stub được); sort theo `time`.

**Kết quả mong đợi:** `grep -r "vnstock.api" src/` rỗng; suite xanh.

## Task 6 — Retail + MSN

**Làm (TDD):** `msn_fx_gold` → `Market().forex("USDVND").ohlcv()` +
`Market().commodity("GC").ohlcv()` (stub); `vn_retail_gold` bỏ nhánh fallback `Retail`;
`vn_retail_fx` trả chuỗi từ `Market("fhsc").forex("USDVND").ohlcv()` + sửa docstring tool
(không còn bid/ask VCB).

**Kết quả mong đợi:** RED→GREEN; `grep -r "Retail\|explorer.msn" src/` rỗng; suite xanh.

## Task 7 — Cấu hình & đóng gói

**Làm:** `cli.py` warm-up `import vnstock.common` → `import vnstock`; `pyproject.toml`:
`vnstock>=6.0.0rc1,<7`, thêm `vnstock-oapi>=0.1.0rc1,<1`, `vnstock-quant>=1.0.0rc1,<2`,
index `[[tool.uv.index]]` cho vnstocks.com; `uv lock`/`uv sync` (note: v6 thay v4 trong
`.venv` — chấp nhận, v4 mốc đã chụp ở Task 1 và venv `~/.venv_6x` giữ bản tham chiếu);
mypy overrides; Dockerfile bỏ font-cache matplotlib nếu v6 không kéo matplotlib (verify);
README (khoá nguồn, bỏ hạn mức 60 req/phút, ghi chú RC + fhsc 06:00–21:00) + render.yaml env.

**Kết quả mong đợi:** `uv sync` OK; `pytest` xanh; build Docker không bắt buộc trong task này.

## Task 8 — Đối chiếu parity v4 vs v6

**Làm:** Script `scripts/parity_compare.py` so fixture Task 1 với chạy v6 (nếu có khoá nguồn
— thực hiện những phần gọi được; phần thiếu khoá ghi `skipped: no source key`).
Báo cáo vào `plans/vnstock-gen6-parity-report-2026-11-08.md`: khớp / lệch / cần xử lý.

## Task 9 — Review toàn nhánh + kết thúc

`review-package` → code-reviewer subagent; sửa Critical/Important; ledger; tổng kết.

## Ledger

SDD workspace: `.superpowers/sdd/vnstock-gen6-migration-2026-11-08.md/` (do script cấp).
