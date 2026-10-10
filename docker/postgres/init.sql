-- MCP-server canonical schema. Mirrors dbinit.py (source of truth for the
-- live database). Tables ohlcv/financial_values/indicators/reports were
-- removed 2026-10-10: unreferenced by any tool (verified), never created live.
-- Cycle-stats tables live in migrations, not here (see tools/cycle_*).

CREATE TABLE IF NOT EXISTS mcp_auth_tokens (
  user_id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'team',
  quota_day INT NOT NULL DEFAULT 1000,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mcp_tool_usage (
  user_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  day DATE NOT NULL,
  count INT NOT NULL DEFAULT 0,
  total_ms BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, tool, day)
);

-- P4 watchlist/alert persist. Still no MongoDB.
CREATE TABLE IF NOT EXISTS daily_snapshots (
  date DATE NOT NULL,
  kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (date, kind)
);
-- Cycle-stats tables (VN sector rotation; P14 dbinit is source of truth).
CREATE TABLE IF NOT EXISTS cycle_ohlcv (
  symbol TEXT NOT NULL, t DATE NOT NULL,
  o DOUBLE PRECISION, h DOUBLE PRECISION, l DOUBLE PRECISION,
  c DOUBLE PRECISION, v DOUBLE PRECISION,
  PRIMARY KEY (symbol, t)
);
CREATE TABLE IF NOT EXISTS cycle_month_stats (
  basket TEXT NOT NULL, month INT NOT NULL,
  mean_ret DOUBLE PRECISION, hit_rate DOUBLE PRECISION,
  rel_ret DOUBLE PRECISION, n INT,
  PRIMARY KEY (basket, month)
);
CREATE TABLE IF NOT EXISTS cycle_chains (
  pair TEXT PRIMARY KEY, n_up INT,
  rel_mean DOUBLE PRECISION, rel_hit DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS cycle_turning (
  year INT NOT NULL, idx TEXT NOT NULL,
  peak_date DATE, trough_date DATE,
  PRIMARY KEY (year, idx)
);
CREATE TABLE IF NOT EXISTS cycle_tet (
  basket TEXT PRIMARY KEY,
  pre5_mean DOUBLE PRECISION, pre5_hit DOUBLE PRECISION,
  post5_mean DOUBLE PRECISION, post5_hit DOUBLE PRECISION, n INT
);
CREATE TABLE IF NOT EXISTS cycle_yearly (
  basket TEXT NOT NULL, year INT NOT NULL, ret DOUBLE PRECISION,
  PRIMARY KEY (basket, year)
);
CREATE TABLE IF NOT EXISTS cycle_trough_events (
  trough DATE PRIMARY KEY, vnindex_3m DOUBLE PRECISION,
  bank DOUBLE PRECISION, securities DOUBLE PRECISION,
  realestate DOUBLE PRECISION, oilgas DOUBLE PRECISION,
  steel DOUBLE PRECISION, utility DOUBLE PRECISION,
  tech DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS cycle_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cycle_watermark (
  symbol TEXT PRIMARY KEY, last_date DATE, mode TEXT,
  members_version TEXT NOT NULL DEFAULT 'v1'
);
-- VN multi-asset cycle tables.
CREATE TABLE IF NOT EXISTS vn_asset_ohlcv (
  asset TEXT NOT NULL, t DATE NOT NULL, c DOUBLE PRECISION,
  PRIMARY KEY (asset, t)
);
CREATE TABLE IF NOT EXISTS vn_asset_monthly (
  asset TEXT NOT NULL, month INT NOT NULL,
  mean_ret DOUBLE PRECISION, hit_rate DOUBLE PRECISION, n INT,
  PRIMARY KEY (asset, month)
);
CREATE TABLE IF NOT EXISTS vn_asset_anchors (
  id SERIAL PRIMARY KEY, asset TEXT NOT NULL, metric TEXT NOT NULL,
  period TEXT NOT NULL, value DOUBLE PRECISION, unit TEXT,
  source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vn_asset_chains (
  pair TEXT PRIMARY KEY, n_up INT,
  rel_mean DOUBLE PRECISION, rel_hit DOUBLE PRECISION, note TEXT
);
CREATE TABLE IF NOT EXISTS vn_asset_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
-- Global asset cycle tables.
CREATE TABLE IF NOT EXISTS g_ohlcv (
  symbol TEXT NOT NULL, t DATE NOT NULL, c DOUBLE PRECISION,
  PRIMARY KEY (symbol, t)
);
CREATE TABLE IF NOT EXISTS g_asset_monthly (
  asset TEXT NOT NULL, month INT NOT NULL,
  mean_ret DOUBLE PRECISION, hit_rate DOUBLE PRECISION, n INT,
  PRIMARY KEY (asset, month)
);
CREATE TABLE IF NOT EXISTS g_asset_phase (
  asset TEXT NOT NULL, phase TEXT NOT NULL,
  mean_m DOUBLE PRECISION, ann_ret DOUBLE PRECISION, n INT,
  PRIMARY KEY (asset, phase)
);
CREATE TABLE IF NOT EXISTS g_asset_corr (
  a TEXT NOT NULL, b TEXT NOT NULL, corr DOUBLE PRECISION,
  regime TEXT NOT NULL DEFAULT 'full',
  PRIMARY KEY (a, b, regime)
);
CREATE TABLE IF NOT EXISTS g_asset_outlook (
  id SERIAL PRIMARY KEY, house TEXT NOT NULL, quarter TEXT NOT NULL,
  asset TEXT NOT NULL, stance TEXT NOT NULL, detail TEXT
);
CREATE TABLE IF NOT EXISTS g_asset_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlists (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
  watchlist_id INT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  UNIQUE(watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS alert_rules (
  id SERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  metric TEXT NOT NULL DEFAULT 'price',
  op TEXT NOT NULL DEFAULT '>',
  threshold DOUBLE PRECISION NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE
);
