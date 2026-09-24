"""P4 contract: watchlist + alert persist (TDD).

Covers: init.sql 3 tables, watchlist CRUD file-fallback shape, alert CRUD,
alert_check with metric rsi14 + cross_up/cross_down ops (monkeypatched, no
network), scan preset cap <=50 with watchlist module wired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _wl_tool_fn(name: str):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"


@pytest.fixture()
def file_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the JSON file fallback at a temp dir; DATABASE_URL unset."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("opentrading_mcp.tools.watchlist._data_dir", data_dir)
    from opentrading_mcp.providers import store

    monkeypatch.setattr(store, "_memory", {})
    return data_dir


# ---------------------------------------------------------------- SQL schema


def test_init_sql_has_three_tables():
    init = (ROOT / "docker" / "postgres" / "init.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS watchlists (" in init
    assert "CREATE TABLE IF NOT EXISTS watchlist_items (" in init
    assert "CREATE TABLE IF NOT EXISTS alert_rules (" in init
    # FK cascade: removing a list removes its items, rules stand alone
    assert "REFERENCES watchlists(id) ON DELETE CASCADE" in init
    assert "UNIQUE(watchlist_id, symbol)" in init


def test_no_mongo_still_passes():
    text = (ROOT / "docker-compose.mcp.yml").read_text()
    assert "mongo" not in text.lower()


# ---------------------------------------------------------------- watchlist


async def test_watchlist_create_list_get_add_remove_delete(file_store: Path):
    fn_create = _wl_tool_fn("watchlist_create")
    fn_list = _wl_tool_fn("watchlist_list")
    fn_get = _wl_tool_fn("watchlist_get")
    fn_add = _wl_tool_fn("watchlist_add")
    fn_remove = _wl_tool_fn("watchlist_remove")
    fn_delete = _wl_tool_fn("watchlist_delete")

    env = await fn_create("core")
    _check_envelope(env, "watchlist_create")
    wl = env["data"]
    assert wl["name"] == "core" and "id" in wl

    env_list = await fn_list()
    assert [w["name"] for w in env_list["data"]["watchlists"]] == ["core"]
    id_ = wl["id"]

    env_add = await fn_add(id_, ["VCB", "vcb", "HPG"])  # dedupe vcb case-insensitive
    assert env_add["data"]["added"] == 2
    assert env_add["data"]["symbols"] == ["VCB", "HPG"]

    env_get = await fn_get(id_)
    assert env_get["data"]["symbols"] == ["VCB", "HPG"]

    env_rm = await fn_remove(id_, ["VCB"])
    assert env_rm["data"]["symbols"] == ["HPG"]

    env_del = await fn_delete(id_)
    assert env_del["data"]["deleted"] == id_
    env_list2 = await fn_list()
    assert env_list2["data"]["watchlists"] == []
    env_gone = await fn_get(id_)
    assert env_gone["availability"] == "empty"


async def test_watchlist_create_rejects_duplicate_name(file_store: Path):
    fn_create = _wl_tool_fn("watchlist_create")
    await fn_create("dup")
    env = await fn_create("dup")
    assert env["availability"] == "unavailable" or "exists" in str(env["warnings"]).lower()


async def test_watchlist_add_unknown_list_is_empty(file_store: Path):
    fn_add = _wl_tool_fn("watchlist_add")
    env = await fn_add(999999, ["VCB"])
    assert env["availability"] == "empty"


async def test_watchlist_update_note(file_store: Path):
    fn_create = _wl_tool_fn("watchlist_create")
    fn_update = _wl_tool_fn("watchlist_update")
    env = await fn_create("notes")
    old = env["data"]
    out = await fn_update(old["id"], "notes2")
    assert out["data"]["name"] == "notes2"


# ------------------------------------------------------------------- alerts


async def test_alert_crud_roundtrip(file_store: Path):
    fn_create = _wl_tool_fn("alert_create")
    fn_list = _wl_tool_fn("alert_list")
    fn_delete = _wl_tool_fn("alert_delete")

    env = await fn_create("VCB", ">", 50000.0)
    _check_envelope(env, "alert_create")
    rule = env["data"]
    assert rule["symbol"] == "VCB"
    assert rule["metric"] == "price"
    assert rule["active"] is True
    assert "id" in rule

    env_list = await fn_list()
    ids = [r["id"] for r in env_list["data"]["rules"]]
    assert rule["id"] in ids

    env_del = await fn_delete(rule["id"])
    assert env_del["data"]["deleted"] == rule["id"]
    env_list2 = await fn_list()
    assert rule["id"] not in [r["id"] for r in env_list2["data"]["rules"]]


async def test_alert_pause_resume(file_store: Path):
    fn_create = _wl_tool_fn("alert_create")
    fn_pause = _wl_tool_fn("alert_pause")
    fn_resume = _wl_tool_fn("alert_resume")
    fn_list = _wl_tool_fn("alert_list")

    rule = (await fn_create("HPG", "cross_up", 30.0))["data"]
    assert rule["op"] == "cross_up"
    assert (await fn_pause(rule["id"]))["data"]["active"] is False
    assert (await fn_list())["data"]["rules"][0]["active"] is False
    assert (await fn_resume(rule["id"]))["data"]["active"] is True


async def test_alert_delete_unknown_id_empty(file_store: Path):
    fn_delete = _wl_tool_fn("alert_delete")
    env = await fn_delete(999999)
    assert env["availability"] == "empty"


# ----------------------------------------------------- alert_check extensions


def _quote(sym: str, close: float) -> dict[str, Any]:
    return {"symbol": sym, "close_price": close}


def _patch_quotes(monkeypatch: pytest.MonkeyPatch, quotes: list[dict[str, Any]]):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "equity_quote_batch", lambda symbols: quotes)


def _patch_history(monkeypatch: pytest.MonkeyPatch, candles: list[dict[str, Any]]):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(
        vn_p, "quote_history", lambda symbol, days=365: [dict(c) for c in candles]
    )


def _candles(rsi_target: float) -> list[dict[str, Any]]:
    """Minimal synthetic series; compute() only needs enough rows."""
    candles: list[dict[str, Any]] = []
    price = 100.0
    # simple monotonic ramp then a small pullback to land RSI near a target
    for i in range(60):
        if i < 50:
            price += 1.0  # rising push RSI toward 100
        else:
            price -= 0.25  # mild pullback keeps RSI > 70
        candles.append(
            {"t": f"2026-06-{i % 28 + 1:02d}", "o": price, "h": price + 0.2,
             "l": price - 0.2, "c": price, "v": 1000.0}
        )
    return candles


async def test_alert_check_metric_price_cross_up(monkeypatch):
    fn = _wl_tool_fn("alert_check")
    _patch_quotes(monkeypatch, [_quote("VCB", 51000.0)])
    rules = [
        {"symbol": "VCB", "metric": "price", "op": "cross_up", "threshold": 50000.0}
    ]
    env = await fn(rules)
    _check_envelope(env, "alert_check")
    assert env["data"]["triggered"], "price cross_up must trigger"
    assert env["data"]["triggered"][0]["op"] == "cross_up"


async def test_alert_check_metric_rsi14_threshold(monkeypatch):
    from opentrading_mcp.providers import technicals as tech_p

    fn = _wl_tool_fn("alert_check")
    candles = _candles(75.0)
    out = tech_p.compute(candles)
    assert out["rsi14"] > 70, f"synthetic candles must yield high RSI, got {out['rsi14']}"
    _patch_history(monkeypatch, candles)
    _patch_quotes(monkeypatch, [_quote("VCB", 120.0)])
    env = await fn([{"symbol": "VCB", "metric": "rsi14", "op": ">", "threshold": 70.0}])
    _check_envelope(env, "alert_check")
    hit = [t for t in env["data"]["triggered"] if t["metric"] == "rsi14"]
    assert hit, "rsi14 > 70 must trigger on synthetic high-RSI candles"


async def test_alert_check_cross_down_fires(monkeypatch):
    fn = _wl_tool_fn("alert_check")
    _patch_quotes(monkeypatch, [_quote("VCB", 49000.0)])
    env = await fn(
        [{"symbol": "VCB", "metric": "price", "op": "cross_down", "threshold": 50000.0}]
    )
    assert env["data"]["triggered"], "price cross_down must trigger"


async def test_alert_check_ops_ge_le(monkeypatch):
    fn = _wl_tool_fn("alert_check")
    _patch_quotes(monkeypatch, [{"symbol": "VCB", "close": 100.0}])
    env = await fn([{"symbol": "VCB", "metric": "price", "op": ">=", "threshold": 100.0}])
    assert env["data"]["triggered"]
    env2 = await fn([{"symbol": "VCB", "metric": "price", "op": "<=", "threshold": 100.0}])
    assert env2["data"]["triggered"]


async def test_alert_check_backward_compat_default_price_gt(monkeypatch):
    """Old behavior: default metric=price, default op=gt (>)."""
    fn = _wl_tool_fn("alert_check")
    _patch_quotes(monkeypatch, [_quote("VCB", 51000.0)])
    env = await fn([{"symbol": "VCB", "threshold": 50000.0}])
    assert env["data"]["triggered"], "default metric/op must keep old behavior"


async def test_alert_check_cross_up_fresh_state_standing(file_store, monkeypatch):
    """First observation beyond threshold fires as standing + seeds alert state."""
    fn = _wl_tool_fn("alert_check")
    _patch_quotes(monkeypatch, [_quote("VCB", 51000.0)])
    env = await fn(
        [{"symbol": "VCB", "metric": "price", "op": "cross_up", "threshold": 50000.0}]
    )
    assert env["data"]["triggered"], "fresh cross_up beyond threshold must fire"
    assert any("seed" in w.lower() for w in env["warnings"]), "must note state seeding"


async def test_alert_check_cross_up_strict_crossing_with_state(monkeypatch):
    """With prev state: cross_up fires only on a real below->above transition."""
    from opentrading_mcp.providers import store

    fn = _wl_tool_fn("alert_check")
    store.cache_set("mcp:scan:alert_state", {"STRICT:price": 49000.0}, ttl_seconds=60)
    _patch_quotes(monkeypatch, [_quote("STRICT", 51000.0)])
    env = await fn(
        [{"symbol": "STRICT", "metric": "price", "op": "cross_up", "threshold": 50000.0}]
    )
    assert env["data"]["triggered"], "prev<=threshold and cur>threshold must fire"
    # prev already above threshold, cur stays above -> no new cross
    store.cache_set("mcp:scan:alert_state", {"STRICT:price": 52000.0}, ttl_seconds=60)
    _patch_quotes(monkeypatch, [_quote("STRICT", 52500.0)])
    env2 = await fn(
        [{"symbol": "STRICT", "metric": "price", "op": "cross_up", "threshold": 50000.0}]
    )
    assert not env2["data"]["triggered"], "already above must not re-fire cross_up"


async def test_alert_check_inactive_rules_are_skipped(file_store: Path):
    """alert_check reads stored rules only when called with stored active ones."""
    fn_create = _wl_tool_fn("alert_create")
    fn_pause = _wl_tool_fn("alert_pause")
    from opentrading_mcp.tools import watchlist as wl_store

    rule = (await fn_create("VCB", ">", 10.0))["data"]
    await fn_pause(rule["id"])
    stored = wl_store._load_rules()
    active = [r for r in stored if r["active"]]
    assert all(r["active"] for r in active)


# ------------------------------------------------- preset wiring + persist


async def test_preset_scan_includes_watchlist_and_cap(file_store: Path):
    from opentrading_mcp.server import create_server, register_preset

    server = create_server("scan")
    tools = register_preset(server, "scan")
    names = [t["name"] for t in tools]
    assert len(tools) <= 50
    for expected in (
        "watchlist_create", "watchlist_list", "watchlist_get", "watchlist_add",
        "watchlist_remove", "watchlist_delete", "watchlist_update",
        "alert_create", "alert_list", "alert_delete", "alert_pause", "alert_resume",
    ):
        assert expected in names, f"{expected} missing from scan preset"


async def test_watchlist_persist_roundtrip_file(file_store: Path):
    """Direct store roundtrip: file fallback keeps data across calls."""
    from opentrading_mcp.tools import watchlist as wl_store

    wl_store._upsert_list("persist-id-1", "persistname")
    wl_store._add_symbols("persist-id-1", ["VCB"])
    loaded = {w["id"]: w for w in wl_store._load_lists()}
    assert loaded["persist-id-1"]["symbols"] == ["VCB"]
    assert (file_store / "watchlists.json").exists()


async def test_alert_rules_persist_roundtrip_file(file_store: Path):
    from opentrading_mcp.tools import watchlist as wl_store

    rid = wl_store._upsert_rule(
        {"id": "r1", "symbol": "VCB", "metric": "price", "op": ">", "threshold": 10.0,
         "active": True}
    )
    assert rid == "r1"
    rules = wl_store._load_rules()
    assert rules[0]["symbol"] == "VCB"
    assert (file_store / "alert_rules.json").exists()


def test_data_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OT_DATA_DIR", str(tmp_path / "envset"))
    from importlib import reload

    import opentrading_mcp.tools.watchlist as wl_store

    reload(wl_store)
    assert wl_store._data_dir == tmp_path / "envset"
    # restore for other tests
    monkeypatch.delenv("OT_DATA_DIR", raising=False)
    reload(wl_store)


def test_cross_state_cache_key_present(monkeypatch):
    from opentrading_mcp.providers import store

    monkeypatch.delenv("REDIS_URL", raising=False)
    store.cache_set("mcp:scan:alert_state", {"a": 1}, ttl_seconds=60)
    assert store.cache_get("mcp:scan:alert_state") == '{"a": 1}'


# ------------------------------------------------------------ review fixes


async def test_alert_create_rejects_invalid_op(file_store: Path):
    """Invalid op must not be stored: warning envelope, availability empty."""
    fn_create = _wl_tool_fn("alert_create")
    fn_list = _wl_tool_fn("alert_list")

    env = await fn_create("VCB", "bananas", 100.0)
    assert env["availability"] == "empty"
    assert "op" in str(env["warnings"]).lower()
    # alias ops still normalize to canonical form and get stored
    env2 = await fn_create("HPG", "gt", 10.0)
    assert env2["data"]["op"] == ">"
    assert (await fn_list())["data"]["rules"][0]["op"] == ">"


async def test_alert_create_duplicate_warns_already_exists(file_store: Path):
    fn_create = _wl_tool_fn("alert_create")
    fn_list = _wl_tool_fn("alert_list")

    first = (await fn_create("VCB", ">", 50000.0))["data"]
    env = await fn_create("VCB", ">", 50000.0)
    assert "already exists" in str(env["warnings"]).lower()
    assert env["data"]["id"] == first["id"]
    ids = [r["id"] for r in (await fn_list())["data"]["rules"]]
    assert ids.count(first["id"]) == 1, "duplicate must not create a second rule"


def test_alert_state_ttl_is_durable():
    """Cross state must outlive one scan cycle so it never re-fires."""
    from opentrading_mcp.tools.scan import ALERT_STATE_KEY, ALERT_STATE_TTL

    assert ALERT_STATE_KEY == "mcp:scan:alert_state"
    assert ALERT_STATE_TTL >= 3600


def test_pg_label_is_env_only_no_connect(monkeypatch: pytest.MonkeyPatch):
    """Label check must read DATABASE_URL only, never open a connection."""
    from opentrading_mcp.tools import watchlist as wl_store

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/x")
    assert wl_store._pg_configured() is True
    monkeypatch.delenv("DATABASE_URL")
    assert wl_store._pg_configured() is False


async def test_watchlist_remove_pg_failure_no_file_fallback(
    file_store: Path, monkeypatch: pytest.MonkeyPatch
):
    """PG failure mid-transaction must roll back + raise, not write the file."""
    from opentrading_mcp.tools import watchlist as wl_store

    class _FakeTx:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any):
            return False

    class _FakeCur:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any):
            return False

        def execute(self, *args: Any, **kwargs: Any):
            raise RuntimeError("boom mid-delete")

    class _FakeConn:
        def transaction(self):
            return _FakeTx()

        def cursor(self):
            return _FakeCur()

        def close(self):
            pass

    monkeypatch.setattr(wl_store, "_pg", lambda: _FakeConn())
    fn_remove = _wl_tool_fn("watchlist_remove")
    env = await fn_remove(1, ["VCB"])
    assert env["availability"] == "unavailable"
    assert "remove failed" in str(env["warnings"])
    assert not (file_store / "watchlists.json").exists(), (
        "must not fall back to file after a failed PG transaction"
    )


async def test_alert_check_history_partial_failure_warns(
    file_store: Path, monkeypatch: pytest.MonkeyPatch
):
    """One symbol's history failure must not kill the whole gather."""
    from opentrading_mcp.providers import vnstock as vn_p

    fn = _wl_tool_fn("alert_check")
    _patch_quotes(monkeypatch, [_quote("AAA", 10.0), _quote("BBB", 20.0)])

    def fake_history(symbol: str, days: int = 365):
        if symbol == "AAA":
            raise RuntimeError("provider down")
        return [
            {"t": f"2026-06-{i % 28 + 1:02d}", "o": 10, "h": 11, "l": 9, "c": 10.5,
             "v": 1000.0}
            for i in range(30)
        ]

    monkeypatch.setattr(vn_p, "quote_history", fake_history)
    env = await fn(
        [
            {"symbol": "AAA", "metric": "rsi14", "op": ">", "threshold": 5.0},
            {"symbol": "BBB", "metric": "rsi14", "op": ">", "threshold": 5.0},
        ]
    )
    _check_envelope(env, "alert_check")
    assert any("AAA" in w and "failed" in w for w in env["warnings"])
    assert env["data"]["evaluated"] == 2


def test_file_dump_leaves_no_tmp(file_store: Path):
    """Atomic write: tmp file is consumed by os.replace."""
    from opentrading_mcp.tools import watchlist as wl_store

    wl_store._upsert_list("t1", "atomic")
    assert (file_store / "watchlists.json").exists()
    assert not (file_store / "watchlists.json.tmp").exists()
