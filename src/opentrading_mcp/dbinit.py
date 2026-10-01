"""Idempotent schema for MCP-server storage (P14).

User decision 2026-10-01: 8010 retired — MCP-server owns its own database
`opentrading_mcp` inside the existing PG instance; nothing of the old
`trading_agents` db is touched. Tables auto-ensure on first use.
"""

from __future__ import annotations

import os
from typing import Any

_ensured = False

TABLES = (
    "watchlists",
    "watchlist_items",
    "alert_rules",
    "mcp_auth_tokens",
    "mcp_tool_usage",
    "daily_snapshots",
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
}


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


def ensure_tables() -> bool:
    """CREATE TABLE IF NOT EXISTS for every table; once per process. True on success."""
    global _ensured
    if _ensured:
        return True
    conn = connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            for ddl in _DDL.values():
                cur.execute(ddl)
        conn.commit()
        _ensured = True
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


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
