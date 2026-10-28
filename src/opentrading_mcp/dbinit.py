"""Idempotent schema for MCP-server storage (P14).

User decision 2026-10-01: 8010 retired — MCP-server owns its own database
`opentrading_mcp` inside the existing PG instance; nothing of the old
`trading_agents` db is touched. Tables auto-ensure on first use.
"""

from __future__ import annotations

import os
import threading
from typing import Any

_ensured = False

TABLES = (
    "watchlists",
    "watchlist_items",
    "alert_rules",
    "mcp_auth_tokens",
    "mcp_tool_usage",
    "daily_snapshots",
    "cycle_ohlcv",
    "cycle_month_stats",
    "cycle_chains",
    "cycle_turning",
    "cycle_tet",
    "cycle_yearly",
    "cycle_trough_events",
    "cycle_meta",
    "cycle_watermark",
    "vn_asset_ohlcv",
    "vn_asset_monthly",
    "vn_asset_anchors",
    "vn_asset_chains",
    "vn_asset_meta",
    "g_ohlcv",
    "g_asset_monthly",
    "g_asset_phase",
    "g_asset_corr",
    "g_asset_outlook",
    "g_asset_meta",
)

_DDL = {
    "watchlists": (
        "CREATE TABLE IF NOT EXISTS watchlists ( id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL)"
    ),
    "watchlist_items": (
        "CREATE TABLE IF NOT EXISTS watchlist_items ("
        " id SERIAL PRIMARY KEY,"
        " watchlist_id INT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,"
        " symbol TEXT NOT NULL, UNIQUE (watchlist_id, symbol))"
    ),
    "alert_rules": (
        "CREATE TABLE IF NOT EXISTS alert_rules ("
        " id SERIAL PRIMARY KEY, symbol TEXT NOT NULL, op TEXT NOT NULL,"
        " threshold DOUBLE PRECISION NOT NULL,"
        " metric TEXT NOT NULL DEFAULT 'price', active BOOLEAN NOT NULL DEFAULT TRUE)"
    ),
    "mcp_auth_tokens": (
        "CREATE TABLE IF NOT EXISTS mcp_auth_tokens ("
        " user_id TEXT PRIMARY KEY, quota_day INT NOT NULL DEFAULT 1000)"
    ),
    "mcp_tool_usage": (
        "CREATE TABLE IF NOT EXISTS mcp_tool_usage ("
        " user_id TEXT NOT NULL, tool TEXT NOT NULL, day DATE NOT NULL,"
        " count INT NOT NULL DEFAULT 0, total_ms DOUBLE PRECISION NOT NULL DEFAULT 0,"
        " PRIMARY KEY (user_id, tool, day))"
    ),
    "daily_snapshots": (
        "CREATE TABLE IF NOT EXISTS daily_snapshots ("
        " date DATE NOT NULL, kind TEXT NOT NULL, payload JSONB NOT NULL,"
        " PRIMARY KEY (date, kind))"
    ),
    "cycle_ohlcv": (
        "CREATE TABLE IF NOT EXISTS cycle_ohlcv ("
        " symbol TEXT NOT NULL, t DATE NOT NULL,"
        " o DOUBLE PRECISION, h DOUBLE PRECISION, l DOUBLE PRECISION,"
        " c DOUBLE PRECISION, v DOUBLE PRECISION,"
        " PRIMARY KEY (symbol, t))"
    ),
    "cycle_month_stats": (
        "CREATE TABLE IF NOT EXISTS cycle_month_stats ("
        " basket TEXT NOT NULL, month INT NOT NULL,"
        " mean_ret DOUBLE PRECISION, hit_rate DOUBLE PRECISION,"
        " rel_ret DOUBLE PRECISION, n INT,"
        " PRIMARY KEY (basket, month))"
    ),
    "cycle_chains": (
        "CREATE TABLE IF NOT EXISTS cycle_chains ("
        " pair TEXT PRIMARY KEY, n_up INT,"
        " rel_mean DOUBLE PRECISION, rel_hit DOUBLE PRECISION)"
    ),
    "cycle_turning": (
        "CREATE TABLE IF NOT EXISTS cycle_turning ("
        " year INT NOT NULL, idx TEXT NOT NULL,"
        " peak_date DATE, trough_date DATE,"
        " PRIMARY KEY (year, idx))"
    ),
    "cycle_tet": (
        "CREATE TABLE IF NOT EXISTS cycle_tet ("
        " basket TEXT PRIMARY KEY,"
        " pre5_mean DOUBLE PRECISION, pre5_hit DOUBLE PRECISION,"
        " post5_mean DOUBLE PRECISION, post5_hit DOUBLE PRECISION, n INT)"
    ),
    "cycle_yearly": (
        "CREATE TABLE IF NOT EXISTS cycle_yearly ("
        " basket TEXT NOT NULL, year INT NOT NULL, ret DOUBLE PRECISION,"
        " PRIMARY KEY (basket, year))"
    ),
    "cycle_trough_events": (
        "CREATE TABLE IF NOT EXISTS cycle_trough_events ("
        " trough DATE PRIMARY KEY, vnindex_3m DOUBLE PRECISION,"
        " bank DOUBLE PRECISION, securities DOUBLE PRECISION,"
        " realestate DOUBLE PRECISION, oilgas DOUBLE PRECISION,"
        " steel DOUBLE PRECISION, utility DOUBLE PRECISION,"
        " tech DOUBLE PRECISION, vin DOUBLE PRECISION)"
    ),
    "cycle_meta": (
        "CREATE TABLE IF NOT EXISTS cycle_meta ("
        " key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    ),
    "cycle_watermark": (
        "CREATE TABLE IF NOT EXISTS cycle_watermark ("
        " symbol TEXT PRIMARY KEY, last_date DATE, mode TEXT,"
        " members_version TEXT NOT NULL DEFAULT 'v1')"
    ),
    "vn_asset_monthly": (
        "CREATE TABLE IF NOT EXISTS vn_asset_monthly ("
        " asset TEXT NOT NULL, month INT NOT NULL,"
        " mean_ret DOUBLE PRECISION, hit_rate DOUBLE PRECISION, n INT,"
        " PRIMARY KEY (asset, month))"
    ),
    "vn_asset_ohlcv": (
        "CREATE TABLE IF NOT EXISTS vn_asset_ohlcv ("
        " asset TEXT NOT NULL, t DATE NOT NULL, c DOUBLE PRECISION,"
        " PRIMARY KEY (asset, t))"
    ),
    "vn_asset_anchors": (
        "CREATE TABLE IF NOT EXISTS vn_asset_anchors ("
        " id SERIAL PRIMARY KEY, asset TEXT NOT NULL, metric TEXT NOT NULL,"
        " period TEXT NOT NULL, value DOUBLE PRECISION, unit TEXT,"
        " source TEXT NOT NULL)"
    ),
    "vn_asset_chains": (
        "CREATE TABLE IF NOT EXISTS vn_asset_chains ("
        " pair TEXT PRIMARY KEY, n_up INT,"
        " rel_mean DOUBLE PRECISION, rel_hit DOUBLE PRECISION, note TEXT)"
    ),
    "vn_asset_meta": (
        "CREATE TABLE IF NOT EXISTS vn_asset_meta ("
        " key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    ),
    "g_asset_monthly": (
        "CREATE TABLE IF NOT EXISTS g_asset_monthly ("
        " asset TEXT NOT NULL, month INT NOT NULL,"
        " mean_ret DOUBLE PRECISION, hit_rate DOUBLE PRECISION, n INT,"
        " PRIMARY KEY (asset, month))"
    ),
    "g_ohlcv": (
        "CREATE TABLE IF NOT EXISTS g_ohlcv ("
        " symbol TEXT NOT NULL, t DATE NOT NULL, c DOUBLE PRECISION,"
        " PRIMARY KEY (symbol, t))"
    ),
    "g_asset_phase": (
        "CREATE TABLE IF NOT EXISTS g_asset_phase ("
        " asset TEXT NOT NULL, phase TEXT NOT NULL,"
        " mean_m DOUBLE PRECISION, ann_ret DOUBLE PRECISION, n INT,"
        " PRIMARY KEY (asset, phase))"
    ),
    "g_asset_corr": (
        "CREATE TABLE IF NOT EXISTS g_asset_corr ("
        " a TEXT NOT NULL, b TEXT NOT NULL, corr DOUBLE PRECISION,"
        " regime TEXT NOT NULL DEFAULT 'full',"
        " PRIMARY KEY (a, b, regime))"
    ),
    "g_asset_outlook": (
        "CREATE TABLE IF NOT EXISTS g_asset_outlook ("
        " id SERIAL PRIMARY KEY, house TEXT NOT NULL, quarter TEXT NOT NULL,"
        " asset TEXT NOT NULL, stance TEXT NOT NULL, detail TEXT)"
    ),
    "g_asset_meta": (
        "CREATE TABLE IF NOT EXISTS g_asset_meta ("
        " key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    ),
}


# CREATE TABLE IF NOT EXISTS never alters an existing table: new columns ride here.
_MIGRATIONS = (
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS vin DOUBLE PRECISION",
    # trough provenance (issues #39/#44): when the event became knowable and how
    # much of the 3M forward window actually existed when the table was built.
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS confirmation DATE",
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS window_start DATE",
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS window_end DATE",
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS window_days INT",
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS window_observations INT",
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS window_complete BOOLEAN",
    "ALTER TABLE cycle_trough_events ADD COLUMN IF NOT EXISTS basket_observations TEXT",
    "ALTER TABLE cycle_yearly ADD COLUMN IF NOT EXISTS is_partial_year BOOLEAN",
    "ALTER TABLE cycle_yearly ADD COLUMN IF NOT EXISTS data_through DATE",
    "ALTER TABLE cycle_yearly ADD COLUMN IF NOT EXISTS period_basis TEXT",
    # Watchlists and alert rules belong to the caller (team bearer = 'team', JWT = sub).
    # Existing rows were all made with the team token: the default backfills them.
    "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'team'",
    "ALTER TABLE watchlists DROP CONSTRAINT IF EXISTS watchlists_name_key",
    "CREATE UNIQUE INDEX IF NOT EXISTS watchlists_owner_name ON watchlists (owner, name)",
    "ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'team'",
)


def db_url() -> str:
    raw = os.environ.get("MCP_DB_URL") or os.environ.get("DATABASE_URL") or ""
    return raw.strip()


def connect(**kwargs: Any) -> Any:
    """PG connection or None when unconfigured (fail-open like store.py)."""
    url = db_url()
    if not url:
        return None
    try:
        import psycopg

        return psycopg.connect(url, **kwargs)
    except Exception:
        return None


_ensure_lock = threading.Lock()


def ensure_tables() -> bool:
    """CREATE TABLE IF NOT EXISTS for every table; once per process. True on success.

    S01 fix: the connection is always closed (success, failure, concurrent
    waiters), initialization is serialized by a process lock (one DDL pass),
    and connect uses an explicit timeout."""
    global _ensured
    if _ensured:
        return True
    with _ensure_lock:
        if _ensured:  # another thread finished while we waited
            return True
        conn = connect(connect_timeout=10)
        if conn is None:
            return False
        try:
            with conn.cursor() as cur:
                for ddl in _DDL.values():
                    cur.execute(ddl)
                for migration in _MIGRATIONS:
                    cur.execute(migration)
            conn.commit()
            _ensured = True
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass


def create_database() -> str:
    """Create the opentrading_mcp database from admin creds (local bootstrap).

    Reads POSTGRES_USER/POSTGRES_PASSWORD/PGHOST/PGPORT; no-op when the db
    already exists. Returns a status string.
    """
    import psycopg

    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "15432")
    user = os.environ.get("POSTGRES_USER", "")
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    if not user or not pw:
        return "missing POSTGRES_USER/POSTGRES_PASSWORD"
    name = os.environ.get("MCP_DB_NAME", "opentrading_mcp")
    admin = psycopg.connect(
        f"host={host} port={port} dbname=postgres user={user} password={pw}", autocommit=True
    )
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        exists = cur.fetchone()
        if not exists:
            cur.execute(f'CREATE DATABASE "{name}"')
    admin.close()
    return f"{name} ready"


def main() -> int:
    print(create_database())
    url = db_url()
    if not url:
        user = os.environ.get("POSTGRES_USER", "")
        pw = os.environ.get("POSTGRES_PASSWORD", "")
        os.environ["MCP_DB_URL"] = (
            f"postgresql://{user}:{pw}@{os.environ.get('PGHOST', 'localhost')}"
            f":{os.environ.get('PGPORT', '15432')}"
            f"/{os.environ.get('MCP_DB_NAME', 'opentrading_mcp')}"
        )
    ok = ensure_tables()
    print("tables ensured" if ok else "ensure failed (db unreachable)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
