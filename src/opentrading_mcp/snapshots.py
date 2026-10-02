"""Daily snapshot storage: preserve rolling data before it disappears (P14).

Worker saves each kind once per trading day (~17:15 VN after ATC); tools read
history via snapshot_history. Payload is a JSONB blob keyed (date, kind).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from opentrading_mcp import dbinit

SNAPSHOT_KINDS = (
    "market_board",
    "breadth_3ex",
    "flows_charts",
    "heatmap_gics",
    "gold_btmc",
    "sbv_rates",
    "nso_releases",
    "analyst_titles",
    "macro_curated",
    "vn30_quotes",
    "futures_basis",
    "documents_feed",
    "events_feed",
    "news_feed",
)


def _json_safe(obj: Any) -> Any:
    """Recursively NaN/Inf -> None so PG JSONB accepts the blob."""
    import math

    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def save(kind: str, payload: Any, day: str | None = None) -> bool:
    """Upsert today's (or given date's) snapshot row. False when db down."""
    conn = dbinit.connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO daily_snapshots (date, kind, payload) VALUES (%s, %s, %s)"
                " ON CONFLICT (date, kind) DO UPDATE SET payload = EXCLUDED.payload",
                (
                    day or date.today().isoformat(),
                    kind,
                    json.dumps(_json_safe(payload), default=str, allow_nan=False),
                ),
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def load(kind: str, days: int = 90) -> list[dict[str, Any]]:
    """Snapshot rows for a kind, newest first: [{date, kind, payload}]."""
    conn = dbinit.connect()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT date::text, kind, payload FROM daily_snapshots"
                " WHERE kind = %s AND date >= CURRENT_DATE - %s"
                " ORDER BY date DESC",
                (kind, max(int(days), 1)),
            )
            rows = []
            for r in cur.fetchall():
                payload = r[2]
                if isinstance(payload, (bytes, str)):
                    try:
                        payload = json.loads(payload)
                    except ValueError:
                        payload = str(payload)[:2000]
                rows.append({"date": r[0], "kind": r[1], "payload": payload})
            return rows
    except Exception:
        return []
    finally:
        conn.close()


def kinds() -> list[str]:
    conn = dbinit.connect()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT kind, COUNT(*) FROM daily_snapshots GROUP BY kind ORDER BY kind")
            return [f"{r[0]}({r[1]})" for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def snapshot_once(day: str | None = None) -> dict[str, Any]:
    """Run every snapshot kind best-effort; returns {kind: ok|fail reason}."""
    out: dict[str, Any] = {}
    day = day or date.today().isoformat()

    def _run(kind: str, fn: Any, *args: Any) -> None:
        try:
            out[kind] = "ok" if save(kind, fn(*args), day) else "db-down"
        except Exception as exc:
            out[kind] = f"fail: {type(exc).__name__}"

    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers import vn_public as pub_p
    from opentrading_mcp.providers import vnstock as vn_p

    _run("market_board", vs_p.market_price)
    _run("breadth_3ex", lambda: [vs_p.market_info_board(ex) for ex in ("HOSE", "HNX", "UPCOM")])
    _run("flows_charts", lambda: {"nn": vs_p.nn_flow_chart(), "prop": vs_p.selftrading_chart()})
    _run("heatmap_gics", vs_p.industry_heatmap)
    _run("gold_btmc", pub_p.btmc_gold)
    _run("sbv_rates", pub_p.sbv_rates)
    _run("nso_releases", pub_p.nso_releases)
    _run("analyst_titles", lambda: pub_p.analyst_reports(50))
    _run(
        "macro_curated",
        lambda: {
            "gdp73_t3": vs_p.macro_report_data(3, 73),
            "cpi15_t7s2": vs_p.macro_report_data(7, 15, "2"),
            "fx55_t1": vs_p.macro_report_data(
                1, 55, "", (date.today() - timedelta(days=92)).isoformat()
            ),
            "xk38_t2": vs_p.macro_report_data(2, 38),
            "nk39_t2": vs_p.macro_report_data(2, 39),
        },
    )
    _run("vn30_quotes", lambda: vn_p.equity_quote_batch(vn_p.VN30))
    from opentrading_mcp.providers import intel as intel_p

    _run("news_feed", lambda: intel_p.fireant_posts(None, 50))
    _run("documents_feed", lambda: vs_p.documents("VCB", 60))
    _run("events_feed", lambda: vs_p.event_calendar("dividends", "", 100))
    return out


async def snapshot_loop() -> None:
    """Worker job: snapshot once per day after ATC (~17:15 Asia/Ho_Chi_Minh)."""
    import asyncio
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from opentrading_mcp.tools.shared import run_blocking

    ran_for: str | None = None
    while True:
        try:
            now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            stamp = now.strftime("%H:%M")
            today = now.date().isoformat()
            if stamp >= "17:15" and ran_for != today:
                from opentrading_mcp.loops import _log as worker_log

                worker_log("snapshot job start")
                result = await run_blocking(snapshot_once, "snapshot_once", timeout_secs=300.0)
                worker_log(f"snapshot job done: {result}")
                ran_for = today
        except Exception:
            pass
        await asyncio.sleep(60)
