"""P4 watchlist + alert persist: Postgres via psycopg, JSON file fallback.

Storage decision (user chose PG): tables `watchlists`/`watchlist_items`/
`alert_rules` in docker/postgres/init.sql. When DATABASE_URL is unset or the
server is unreachable, every read/write falls back to data/watchlists.json +
data/alert_rules.json (atomic tmp + os.replace dumps; per-call load/dump, no
locking — same-envelope writers are expected to be rare). Alert cross-op state
goes through providers/store.cache_get/set (Redis `mcp:scan:alert_state`,
TTL 3600s) with the process-memory fallback.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from opentrading_mcp.schemas import make_envelope
from opentrading_mcp.tools.shared import (
    READ_ONLY,
    READ_WRITE_CREATE,
    READ_WRITE_DELETE,
    AnyContext,
    run_blocking,
)

logger = logging.getLogger(__name__)

VALID_ALERT_OPS = (">", ">=", "<", "<=", "cross_up", "cross_down")
_OP_ALIASES = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}

_data_dir = Path(os.environ.get("OT_DATA_DIR", "data"))


def _pg_configured() -> bool:
    """True when DATABASE_URL is set. Env-only label check — opens nothing."""
    return bool(os.environ.get("DATABASE_URL", "").strip())


def _pg() -> Any:
    """Open a PG connection when DATABASE_URL is set; caller must close it.

    Tables are auto-ensured once per process (P14 dbinit), so a fresh
    database works without a manual migration step.
    """
    from opentrading_mcp import dbinit

    url = dbinit.db_url().strip()
    if not url:
        return None
    dbinit.ensure_tables()
    try:
        import psycopg

        return psycopg.connect(url, autocommit=True, connect_timeout=5)
    except Exception as exc:
        logger.warning("postgres connect failed: %s", exc)
        return None


def _file_path(kind: str) -> Path:
    names = {"lists": "watchlists.json", "rules": "alert_rules.json"}
    return Path(_data_dir) / names[kind]


def _file_load(kind: str) -> list[dict[str, Any]]:
    path = _file_path(kind)
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        return []
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.warning("file load failed (%s): %s", kind, exc)
        return []


def _file_dump(kind: str, rows: list[dict[str, Any]]) -> None:
    path = _file_path(kind)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("file write failed (%s): %s", kind, exc)


# ------------------------------------------------------------------ storage


def _load_lists() -> list[dict[str, Any]]:
    conn = _pg()
    if conn is not None:
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT w.id, w.name,"
                    " COALESCE(array_agg(i.symbol ORDER BY i.symbol), '{}') AS symbols"
                    " FROM watchlists w LEFT JOIN watchlist_items i"
                    " ON i.watchlist_id = w.id"
                    " GROUP BY w.id, w.name ORDER BY w.id"
                )
                rows = cur.fetchall()
            return [
                {"id": r["id"], "name": r["name"], "symbols": list(r["symbols"] or [])}
                for r in rows
            ]
        except Exception:
            pass
        finally:
            conn.close()
    return _file_load("lists")


def _upsert_list_file(list_id: str, name: str) -> dict[str, Any]:
    """File fallback: caller validated duplicates; append only if new."""
    rows = _file_load("lists")
    for row in rows:
        if row["id"] == list_id:
            row["name"] = name
            row.setdefault("symbols", [])
            _file_dump("lists", rows)
            return dict(row)
    new = {"id": list_id, "name": name, "symbols": []}
    rows.append(new)
    _file_dump("lists", rows)
    return dict(new)


def _upsert_list(list_id: str, name: str) -> dict[str, Any]:
    conn = _pg()
    if conn is not None:
        try:
            int(list_id)
        except ValueError:
            conn.close()
            return _upsert_list_file(list_id, name)
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO watchlists (name, id) VALUES (%s, %s)"
                    " ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"
                    " RETURNING id, name",
                    (name, int(list_id)),
                )
                row = cur.fetchone()
                # Keep SERIAL ahead of any explicit id so later inserts
                # (watchlist_create) never collide with a restored id.
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence('watchlists', 'id'),"
                    " GREATEST((SELECT COALESCE(MAX(id), 1) FROM watchlists), 1))"
                )
            return {"id": row["id"], "name": row["name"], "symbols": []}
        except Exception:
            pass
        finally:
            conn.close()
    return _upsert_list_file(list_id, name)


def _delete_list(list_id: str) -> bool:
    conn = _pg()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM watchlists WHERE id = %s", (int(list_id),))
                return bool(cur.rowcount > 0)
        except Exception:
            return False
        finally:
            conn.close()
    rows = _file_load("lists")
    keep = [r for r in rows if r["id"] != list_id]
    if len(keep) == len(rows):
        return False
    _file_dump("lists", keep)
    return True


def _add_symbols(list_id: str, symbols: list[str]) -> list[str]:
    """Add case-insensitively deduped symbols; returns the list's symbols."""
    clean: list[str] = []
    seen: set[str] = set()
    for s in symbols:
        up = str(s).strip().upper()
        if up and up not in seen:
            seen.add(up)
            clean.append(up)
    conn = _pg()
    if conn is not None:
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT COALESCE(array_agg(i.symbol ORDER BY i.symbol), '{}') AS existing"
                    " FROM watchlist_items i WHERE i.watchlist_id = %s",
                    (int(list_id),),
                )
                existing = list(cur.fetchone()["existing"] or [])
                for sym in clean:
                    if sym not in existing:
                        cur.execute(
                            "INSERT INTO watchlist_items (watchlist_id, symbol)"
                            " VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (int(list_id), sym),
                        )
                        existing.append(sym)
                cur.execute(
                    "SELECT COALESCE(array_agg(i.symbol ORDER BY i.symbol), '{}') AS syms"
                    " FROM watchlist_items i WHERE i.watchlist_id = %s",
                    (int(list_id),),
                )
                return list(cur.fetchone()["syms"] or [])
        except Exception:
            pass
        finally:
            conn.close()
    rows = _file_load("lists")
    for row in rows:
        if row["id"] == list_id:
            have = list(row.get("symbols", []))
            for sym in clean:
                if sym not in have:
                    have.append(sym)
            row["symbols"] = have
            _file_dump("lists", rows)
            return have
    return []


def _remove_symbols(list_id: str, symbols: list[str]) -> list[str]:
    """Remove symbols in one transaction; on PG failure the transaction is
    rolled back and the error is raised — no partial delete may silently
    fall back to the file store."""
    drop = sorted({str(s).strip().upper() for s in symbols} - {""})
    conn = _pg()
    if conn is not None:
        try:
            with conn.transaction(), conn.cursor() as cur:
                if drop:
                    cur.execute(
                        "DELETE FROM watchlist_items WHERE watchlist_id = %s AND symbol = ANY(%s)",
                        (int(list_id), drop),
                    )
                cur.execute(
                    "SELECT COALESCE(array_agg(i.symbol ORDER BY i.symbol), '{}')"
                    " FROM watchlist_items i WHERE i.watchlist_id = %s",
                    (int(list_id),),
                )
                return list(cur.fetchone()[0] or [])
        finally:
            # close always; transaction() context rolled back on failure and
            # re-raised, so the caller (watchlist_remove) turns it into a
            # warning envelope instead of a file fallback.
            conn.close()
    return _remove_symbols_file(list_id, set(drop))


def _remove_symbols_file(list_id: str, drop: set[str]) -> list[str]:
    rows = _file_load("lists")
    for row in rows:
        if row["id"] == list_id:
            row["symbols"] = [s for s in row.get("symbols", []) if s not in drop]
            _file_dump("lists", rows)
            return list(row["symbols"])
    return []


def _load_rules() -> list[dict[str, Any]]:
    conn = _pg()
    if conn is not None:
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, symbol, metric, op, threshold, active FROM alert_rules ORDER BY id"
                )
                rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "symbol": r["symbol"],
                    "metric": r["metric"],
                    "op": r["op"],
                    "threshold": float(r["threshold"]),
                    "active": bool(r["active"]),
                }
                for r in rows
            ]
        except Exception:
            pass
        finally:
            conn.close()
    return _file_load("rules")


def _upsert_rule(rule: dict[str, Any]) -> Any:
    conn = _pg()
    if conn is not None:
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO alert_rules (symbol, metric, op, threshold, active)"
                    " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (
                        rule["symbol"],
                        rule.get("metric", "price"),
                        rule.get("op", ">"),
                        rule["threshold"],
                        rule.get("active", True),
                    ),
                )
                return cur.fetchone()["id"]
        except Exception:
            pass
        finally:
            conn.close()
    rows = _file_load("rules")
    if rule.get("id") is not None:
        rid = str(rule["id"])
        for row in rows:
            if str(row["id"]) == rid:
                row.update(rule)
                _file_dump("rules", rows)
                return rid
        record = dict(rule)
        record["id"] = rid
        rows.append(record)
        _file_dump("rules", rows)
        return rid
    new_id = max((int(str(r["id"])) for r in rows if str(r["id"]).isdigit()), default=0) + 1
    record = dict(rule)
    record["id"] = new_id
    rows.append(record)
    _file_dump("rules", rows)
    return new_id


def _delete_rule(rule_id: str) -> bool:
    conn = _pg()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM alert_rules WHERE id = %s", (int(rule_id),))
                return bool(cur.rowcount > 0)
        except Exception:
            return False
        finally:
            conn.close()
    rows = _file_load("rules")
    for row in rows:
        if str(row["id"]) == str(rule_id):
            rows = [r for r in rows if str(r["id"]) != str(rule_id)]
            _file_dump("rules", rows)
            return True
    return False


def _set_rule_active(rule_id: str, active: bool) -> dict[str, Any] | None:
    conn = _pg()
    if conn is not None:
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "UPDATE alert_rules SET active = %s WHERE id = %s"
                    " RETURNING id, symbol, metric, op, threshold, active",
                    (active, int(rule_id)),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()
    rows = _file_load("rules")
    for row in rows:
        if str(row["id"]) == str(rule_id):
            row["active"] = active
            _file_dump("rules", rows)
            return dict(row)
    return None


def _rename_list(list_id: str, name: str) -> dict[str, Any] | None:
    """Rename a list keeping its symbols; None when the id is unknown."""
    conn = _pg()
    if conn is not None:
        try:
            from psycopg.rows import dict_row

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "UPDATE watchlists SET name = %s WHERE id = %s RETURNING id, name",
                    (name, int(list_id)),
                )
                row = cur.fetchone()
            if row is None:
                return None
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT COALESCE(array_agg(i.symbol ORDER BY i.symbol), '{}') AS syms"
                    " FROM watchlist_items i WHERE i.watchlist_id = %s",
                    (int(list_id),),
                )
                symbols = list(cur.fetchone()["syms"] or [])
            return {"id": row["id"], "name": row["name"], "symbols": symbols}
        except Exception:
            return None
        finally:
            conn.close()
    rows = _file_load("lists")
    for row in rows:
        if str(row["id"]) == str(list_id):
            row["name"] = name
            row.setdefault("symbols", [])
            _file_dump("lists", rows)
            return dict(row)
    return None


async def _toggle(server: FastMCP, rule_id: int, active: bool) -> dict[str, Any]:
    """Shared body for alert_pause/alert_resume."""
    updated = await run_blocking(lambda: _set_rule_active(str(rule_id), active), "alert_toggle")
    if updated is None:
        return make_envelope(
            {"tool": "alert_toggle", "rule_id": rule_id}, source="local", availability="empty"
        )
    source = "postgres" if _pg_configured() else "file"
    verb = "paused" if not active else "resumed"
    return make_envelope({**updated, "state": verb}, source=source)


# -------------------------------------------------------------------- tools


def register_watchlist_tools(server: FastMCP) -> list[dict[str, Any]]:
    @server.tool(annotations=READ_WRITE_CREATE)
    async def watchlist_create(name: str, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Create a named watchlist. Use to start tracking a symbol group."""
        if ctx is not None:
            await ctx.log("info", f"watchlist_create {name}")
        name = name.strip()
        if not name:
            return make_envelope(
                {"tool": "watchlist_create"},
                source="local",
                warnings=["name required"],
                availability="empty",
            )
        conn = _pg()
        if conn is not None:
            try:
                from psycopg.rows import dict_row

                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SELECT id FROM watchlists WHERE name = %s", (name,))
                    if cur.fetchone() is not None:
                        return make_envelope(
                            {"tool": "watchlist_create"},
                            source="postgres",
                            warnings=[f"watchlist '{name}' already exists"],
                            availability="empty",
                        )
                    cur.execute(
                        "INSERT INTO watchlists (name) VALUES (%s) RETURNING id, name", (name,)
                    )
                    row = cur.fetchone()
                return make_envelope(
                    {"id": row["id"], "name": row["name"], "symbols": []}, source="postgres"
                )
            except Exception as exc:
                warnings_pg = f"pg create failed, file fallback: {exc}"
                logger.warning(warnings_pg)
            finally:
                conn.close()
        existing = _file_load("lists")
        if any(r["name"] == name for r in existing):
            return make_envelope(
                {"tool": "watchlist_create"},
                source="local",
                warnings=[f"watchlist '{name}' already exists"],
                availability="unavailable",
            )
        new_id = max((int(str(r["id"])) for r in existing if str(r["id"]).isdigit()), default=0) + 1
        created = _upsert_list(str(new_id), name)
        return make_envelope(created, source="file")

    @server.tool(annotations=READ_ONLY)
    async def watchlist_list(ctx: AnyContext | None = None) -> dict[str, Any]:
        """List all watchlists with their symbols. Use to recall tracking state."""
        if ctx is not None:
            await ctx.log("info", "watchlist_list")
        lists = await run_blocking(_load_lists, "watchlist_list")
        if not lists:
            return make_envelope({"watchlists": []}, source="local", availability="empty")
        return make_envelope(
            {"watchlists": lists},
            source="postgres" if _pg_configured() else "file",
        )

    @server.tool(annotations=READ_ONLY)
    async def watchlist_get(list_id: int, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Get one watchlist's symbols by id. Use before quoting a saved set."""
        if ctx is not None:
            await ctx.log("info", f"watchlist_get {list_id}")
        for entry in await run_blocking(_load_lists, "watchlist_get"):
            if int(entry["id"]) == int(list_id):
                return make_envelope(entry, source="postgres" if _pg_configured() else "file")
        return make_envelope(
            {"tool": "watchlist_get", "list_id": list_id}, source="local", availability="empty"
        )

    @server.tool(annotations=READ_WRITE_CREATE)
    async def watchlist_add(
        list_id: int, symbols: list[str], ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Add symbols (deduped, uppercase) to a watchlist. Use to track more."""
        if ctx is not None:
            await ctx.log("info", f"watchlist_add {list_id} {symbols}")
        lists = await run_blocking(_load_lists, "watchlist_add")
        known = {int(w["id"]) for w in lists}
        before = {
            str(s).upper()
            for w in lists
            if int(w["id"]) == int(list_id)
            for s in w.get("symbols") or []
        }
        if int(list_id) not in known:
            return make_envelope(
                {"tool": "watchlist_add", "list_id": list_id},
                source="local",
                warnings=[f"no watchlist {list_id}"],
                availability="empty",
            )
        out = await run_blocking(lambda: _add_symbols(str(list_id), symbols), "watchlist_add")
        return make_envelope(
            # added = symbols new to the list (it was the list's total size)
            {"list_id": list_id, "added": len([s for s in out if s not in before]),
             "symbols": out},
            source="postgres" if _pg_configured() else "file",
        )

    @server.tool(annotations=READ_WRITE_DELETE)
    async def watchlist_remove(
        list_id: int, symbols: list[str], ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Remove symbols from a watchlist. Use to trim tracking."""
        if ctx is not None:
            await ctx.log("info", f"watchlist_remove {list_id} {symbols}")
        try:
            out = await run_blocking(
                lambda: _remove_symbols(str(list_id), symbols), "watchlist_remove"
            )
        except Exception as exc:
            return make_envelope(
                {"tool": "watchlist_remove", "list_id": list_id},
                source="postgres" if _pg_configured() else "file",
                warnings=[f"remove failed: {exc}"],
                availability="unavailable",
            )
        return make_envelope(
            {"list_id": list_id, "symbols": out}, source="postgres" if _pg_configured() else "file"
        )

    @server.tool(annotations=READ_WRITE_DELETE)
    async def watchlist_delete(list_id: int, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Delete a watchlist and its items (cascade). Use to clean up."""
        if ctx is not None:
            await ctx.log("info", f"watchlist_delete {list_id}")
        ok = await run_blocking(lambda: _delete_list(str(list_id)), "watchlist_delete")
        if not ok:
            return make_envelope(
                {"tool": "watchlist_delete", "list_id": list_id},
                source="local",
                availability="empty",
            )
        return make_envelope(
            {"deleted": list_id},
            source="postgres" if _pg_configured() else "file",
        )

    @server.tool(annotations=READ_WRITE_CREATE)
    async def watchlist_update(
        list_id: int, name: str, ctx: AnyContext | None = None
    ) -> dict[str, Any]:
        """Rename a watchlist. Use sparingly; names are unique labels."""
        if ctx is not None:
            await ctx.log("info", f"watchlist_update {list_id} {name}")
        name = name.strip()
        if not name:
            return make_envelope(
                {"tool": "watchlist_update"},
                source="local",
                warnings=["name required"],
                availability="empty",
            )
        updated = await run_blocking(lambda: _rename_list(str(list_id), name), "watchlist_update")
        if updated is None:
            return make_envelope(
                {"tool": "watchlist_update", "list_id": list_id},
                source="local",
                availability="empty",
            )
        return make_envelope(updated, source="postgres" if _pg_configured() else "file")

    @server.tool(annotations=READ_WRITE_CREATE)
    async def alert_create(
        symbol: str,
        op: str = ">",
        threshold: float = 0.0,
        metric: str = "price",
        ctx: AnyContext | None = None,
    ) -> dict[str, Any]:
        """Create a stored alert rule (input to alert_check). Use for live watch.

        metric: 'price' or 'rsi14'. op: '>'/'>='/<'/'<=' (aliases 'gt'/'gte'/
        'lt'/'lte' accepted). threshold: comparison value for the metric.
        """
        if ctx is not None:
            await ctx.log("info", f"alert_create {symbol} {metric} {op} {threshold}")
        metric = metric if metric in ("price", "rsi14") else "price"
        op = _OP_ALIASES.get(op, op)
        if op not in VALID_ALERT_OPS:
            return make_envelope(
                {"tool": "alert_create"},
                source="local",
                warnings=[f"invalid op: {op} (use one of {', '.join(VALID_ALERT_OPS)})"],
                availability="empty",
            )
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return make_envelope(
                {"tool": "alert_create"},
                source="local",
                warnings=["threshold must be a number"],
                availability="empty",
            )
        record = {
            "symbol": symbol.upper(),
            "metric": metric,
            "op": op,
            "threshold": threshold,
            "active": True,
        }
        existing = await run_blocking(_load_rules, "alert_create")
        for r in existing:
            try:
                same = (
                    str(r.get("symbol", "")).upper() == record["symbol"]
                    and str(r.get("metric", "price")) == metric
                    and str(r.get("op", ">")) == op
                    and float(r.get("threshold", 0)) == threshold
                )
            except (TypeError, ValueError):
                continue
            if same:
                return make_envelope(
                    {**r, "state": "already exists"},
                    source="postgres" if _pg_configured() else "file",
                    warnings=[f"alert rule already exists: {record['symbol']} {op} {threshold}"],
                )
        rid = await run_blocking(lambda: _upsert_rule(record), "alert_create")
        created = dict(record)
        created["id"] = rid
        return make_envelope(created, source="postgres" if _pg_configured() else "file")

    @server.tool(annotations=READ_ONLY)
    async def alert_list(ctx: AnyContext | None = None) -> dict[str, Any]:
        """List stored alert rules (active and paused). Use before alert_check."""
        if ctx is not None:
            await ctx.log("info", "alert_list")
        rules = await run_blocking(_load_rules, "alert_list")
        return make_envelope(
            {"rules": rules},
            source="postgres" if _pg_configured() else "file",
            availability="empty" if not rules else None,
        )

    @server.tool(annotations=READ_WRITE_DELETE)
    async def alert_delete(rule_id: int, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Delete a stored alert rule by id. Use to clean up alerts."""
        if ctx is not None:
            await ctx.log("info", f"alert_delete {rule_id}")
        ok = await run_blocking(lambda: _delete_rule(str(rule_id)), "alert_delete")
        if not ok:
            return make_envelope(
                {"tool": "alert_delete", "rule_id": rule_id}, source="local", availability="empty"
            )
        return make_envelope(
            {"deleted": rule_id}, source="postgres" if _pg_configured() else "file"
        )

    @server.tool(annotations=READ_WRITE_CREATE)
    async def alert_pause(rule_id: int, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Pause a stored alert rule (active=false). Use to silence alerts."""
        return await _toggle(server, rule_id, False)

    @server.tool(annotations=READ_WRITE_CREATE)
    async def alert_resume(rule_id: int, ctx: AnyContext | None = None) -> dict[str, Any]:
        """Resume a paused alert rule (active=true). Use to re-enable alerts."""
        return await _toggle(server, rule_id, True)

    return [
        {"name": "watchlist_create"},
        {"name": "watchlist_list"},
        {"name": "watchlist_get"},
        {"name": "watchlist_add"},
        {"name": "watchlist_remove"},
        {"name": "watchlist_delete"},
        {"name": "watchlist_update"},
        {"name": "alert_create"},
        {"name": "alert_list"},
        {"name": "alert_delete"},
        {"name": "alert_pause"},
        {"name": "alert_resume"},
    ]
