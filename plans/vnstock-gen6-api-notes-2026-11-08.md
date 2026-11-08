# vnstock gen 6 — API thật đo được trên máy (v6.0.0rc4, 2026-11-08)

Môi trường: `~/.venv_6x` — vnstock 6.0.0rc4, vnstock-oapi 0.1.0rc3, vnstock-quant 1.0.0rc2.
Lưu ý cài: **phải ghim `httpx>=0.27,<1`** — cài `--pre` trượt httpx 1.0.dev6 làm mọi call lỗi
`AttributeError: transport` (bug tại vnstock/_unified.py:593).

## Doctor (08/11/2026)
- vnstock 6.0.0rc4 dùng được đến **07/12/2026** (RC expiry).
- Tài khoản Vnstock: free (khoá cũ ~/.vnstock tái sử dụng, tự động).
- binance: không cần khoá ✔ · fhsc/ssi/dnse/tcbs/fmp: chưa có khoá (chờ người dùng đăng ký).

## Top-level exports
`Market, Reference, Fundamental, Retail(keep-import), Analytics, Insights, Macro, account,
compat, errors, sources, telemetry, show_api, show_doc, login, logout, status, cite, provenance`.
- **Đã xoá**: `Quote, Listing, Company, Finance, Trading, Vnstock, change_api_key` (ImportError).
- Không chọn nguồn → `InputError` **code=VNSTOCK_INPUT_SOURCE** (attr `route`).

## Market(source=None, *, profile="default")
Nhóm trên instance: bond, commodity, crypto, equity, etf, forex, fund, futures, **global_index**, index, warrant.
- `equity.ohlcv(start=None, end=None, interval='1D', limit=None, floating=2, *, source=None,
  count_back=None, length=None, compat=None, columns='standard', **legacy)`
  → `**legacy` nhận `count/resolution` (cảnh báo CompatibilityWarning) — chuyển từ từ được.
- `equity.quote(*, source=None, compat=None, columns='standard', floating=2, **options)` (batch).
- `equity.trades(start=None, end=None, limit=100, *, source=None, ...)` — **limit mặc định 100**.
- index: ohlcv/quote/history/price_board/foreign_flow/proprietary_flow/summary/trade_history/stock_influence.
- futures: ohlcv/quote/intraday/order_book/price_depth/summary.
- forex/crypto/commodity/global_index: đều có `ohlcv(start, end, interval, limit, *, source, count_back, length, compat, columns, **legacy)`.
- Live binance (BTCUSDT 1D): **8 dòng tăng dần theo time**, cols `time, open, high, low, close,
  volume, quote_volume, trade_count`; attrs có `profile, schema_changes, source, route, ...`.

## Reference(source=None, *, profile="default")
Nhóm: bond, company, etf, events, fund, futures, index, industry, market, search, warrant, equity.
- `equity`: `list`, `by_exchange`, `by_group`, `list_by_exchange`, `list_by_group`,
  `list_by_industry`, `price_limits`, `status` (tên v4 còn dùng được).
- `index("VN30")`: `members`, `list`, `by_group`, `groups`, `info`, `description`, `list_by_group`.
- `industry`: `list`, `sectors`.
- `Reference("fhsc").company("FPT")`: info, **officers ✔**, shareholders, insider_trading, events,
  overview, ownership, news, subsidiaries, affiliate, capital_history, ratio_summary, reports, trading_stats.

## Fundamental("fhsc").equity("FPT")
`balance_sheet / income_statement / cash_flow (company_type=None, period=None, lang='vi',
drop_empty=False, format='long', *, source=None, compat=None, columns='standard', **options)`.
- `period=None` lấy cả năm+quý; `format` thay `orient`; **không có `dropna`** (v4) —
  v4 từng dùng `dropna`; v6 dùng `drop_empty` (mặc định False).
- Tên `ratio, note, filing, financial_health` còn import nhưng sẽ UnsupportedError.

## vnstock_quant (1.0.0rc2)
- `fa.Dataset.load(symbols, period='both', com_type=None, prices=True, notes=None,
  source=None, price_start='2017-01-01', price_source=None, estimate_shares=False)` —
  **tải thẳng từ vnstock qua `source=`, không cần tự dựng 3 báo cáo**.
- `fa.Dataset.from_frames(statements, prices=None, com_type=None, as_of=None, estimate_shares=False)`.
- `fa.ratios(data, ids=None, period='quarter', profile='vn', overrides=None, format='long')`.
- `vq.entitlement()`, `vq.build_info()`; lỗi: `QuotaExceededError`, `ReleaseExpiredError`...

## vnstock.errors
AccessDeniedError, AuthError, ChallengeRequiredError, ClockSkewError, CompatibilityWarning,
CredentialError, DataSourceBlockedError, EntitlementError, EnvelopeError, InputError,
InternalError, LoginRequiredError, NetworkError, **OtpRequiredError**, PayloadError,
PolicyError, ProviderError, RateLimitError, RateLimitedError, SchemaChangeWarning,
SchemaError, SourceError, UnsupportedError, VnstockError.

## sources
`use(*names, route='*')`, `save()`, `load()`, `which()`, `resolve()`, `show()`, `clear()`,
`default_path`, biến môi trường `VNSTOCK_SOURCES` trỏ sources.json (cho cron/container).
