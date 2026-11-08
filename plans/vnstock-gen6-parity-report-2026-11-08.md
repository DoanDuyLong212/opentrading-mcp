# Đối chiếu parity v4 (fixture parity_v4_2026-11-08) vs vnstock 6.0.0rc4

> **ĐÃ THAY THẾ (09/11/2026)** — xem `vnstock-gen6-parity-report-2026-11-09.md`, chạy bằng harness
> so sánh GIÁ TRỊ (#89) với khoá ssi/dnse thật trên bản gộp mọi PR: 17 khớp, 2 lệch đã giải thích (vàng spot → futures;
> crypto VND → USDT), 4 route không còn nguồn (fhsc/fmp ngừng dùng). Đính chính báo cáo dưới đây:
> - "match (shape)" ở đây KHÔNG so giá trị — harness cũ chỉ kiểm danh sách không rỗng.
> - Số test: `test_vn6_adapter.py` có 16 test (không phải 12), `test_vn6_ratios.py` có 13 (không phải 9).
> - "v4 cũng tăng dần nên không đổi consumer" sai cho `equity_trades`: adapter sắp xếp MỚI NHẤT TRƯỚC.
> - 18/19 probe gen 6 bị bỏ qua vì không có khoá, nên báo cáo này không phải bằng chứng parity.

Khoá nguồn có sẵn: không có — probe thiếu khoá bị bỏ qua trước khi gọi.

| Probe | v4 baseline | Trạng thái v6 |
|---|---|---|
| quote_history_FPT | ok | skipped: no source key (fhsc/ssi) |
| quote_history_VNINDEX | ok | skipped: no source key (fhsc/ssi) |
| equity_quote_batch | ok | skipped: no source key (fhsc) |
| equity_ohlcv_FPT | ok | skipped: no source key (fhsc/ssi) |
| index_ohlcv_VNINDEX | ok | skipped: no source key (fhsc/ssi) |
| futures_ohlcv_VN30F1M | ok | skipped: no source key (fhsc) |
| forex_ohlcv_USDVND | ok | skipped: no source key (fhsc) |
| crypto_ohlv_BTCUSDT | ok | match (shape) |
| global_index_USA30 | ok | skipped: no source key (fmp) |
| equity_trades_FPT | ok | skipped: no source key (fhsc/ssi) |
| listing_symbols | ok | skipped: no source key (fhsc/ssi) |
| equity_ratios_FPT | ok | skipped: no source key (fhsc) |
| equity_fundamentals_FPT | ok | skipped: no source key (fhsc) |
| cashflow_FPT_quarter | ok | skipped: no source key (fhsc) |
| reference_equity_HOSE | ok | skipped: no source key (fhsc/ssi) |
| company_info_FPT | ok | skipped: no source key (fhsc) |
| insider_trading_FPT | ok | skipped: no source key (fhsc) |
| corp_events_FPT | ok | skipped: no source key (fhsc) |
| msn_fx_gold | ok | skipped: no source key (fhsc) |

## Ghi chú schema cần biết
- Nến gen 6: `time` mang múi giờ 07:00+07:00, `volume` Int64, đơn vị nghìn đồng (giữ như v4 adapter đã chuẩn hoá).
- `equity_ratios` gen 6 tính bằng vnstock_quant.fa (period labels do fa cấp, không parse từ frame nguồn).
- Thứ tự dòng: adapter sort tăng dần theo ngày sau fetch — v4 cũng tăng dần nên không đổi consumer.
- Bị chặn bởi khoá: probe fhsc/ssi/fmp báo `skipped` TRƯỚC khi gọi (adapter nuốt lỗi auth trong vòng fallback, không tin được thông báo lỗi) — chạy lại script sau khi đăng ký khoá.

## Bằng chứng cấu trúc (offline, không cần khoá)

- `tests/test_vn6_adapter.py` (12 test): mọi adapter call đúng shape gen 6 — `Market(<src>).equity().ohlcv`, `Reference(<src>).equity.list`, `Reference('fhsc').company(...)`, `count_back/interval` (không còn `count/resolution`), sort tăng dần theo ngày, fallback nguồn không còn VCI/KBS, crypto qua binance không cần khoá.
- `tests/test_vn6_ratios.py` (9 test): bảng ratio v4-shape dựng từ fa long frame thật (shape đo live 08/11) — percent scaling, RT→item_id, quality_note cho MISSING_*, cache 6h chống đốt quota 30/ngày.
- Suite offline: 130+ test liên quan adapter/ratios pass (chi tiết trong SDD ledger).
