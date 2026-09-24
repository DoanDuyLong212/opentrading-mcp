-- MCP-server canonical cache. No MongoDB: reports JSONB replaces vietstock_news.
CREATE TABLE IF NOT EXISTS ohlcv (
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  PRIMARY KEY (symbol, interval, observed_at)
);

CREATE TABLE IF NOT EXISTS financial_values (
  symbol TEXT NOT NULL,
  norm_code TEXT NOT NULL,
  year_period INT NOT NULL,
  report_term_id INT NOT NULL,
  value NUMERIC,
  source TEXT NOT NULL DEFAULT 'vietstock',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, norm_code, year_period, report_term_id)
);

CREATE TABLE IF NOT EXISTS indicators (
  category_id INT NOT NULL,
  term_type_id INT NOT NULL,
  period DATE NOT NULL,
  value NUMERIC,
  source TEXT NOT NULL DEFAULT 'vietstock',
  PRIMARY KEY (category_id, term_type_id, period)
);

CREATE TABLE IF NOT EXISTS reports (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT,
  title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'news',
  published_at TIMESTAMPTZ,
  url TEXT,
  payload JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS reports_payload_gin ON reports USING GIN (payload);
CREATE INDEX IF NOT EXISTS reports_symbol_idx ON reports (symbol);

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
