"""Contract: 06-10 fixes — geo_intel (political filter + military), event_stats aggregate,
valuation_run btype validation."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_all


def _tool_fn(name: str):
    server = create_server()
    register_all(server)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"


async def test_geo_intel_filters_non_political(monkeypatch):
    """Eval 06-10 (S03): sports articles leaked into geo_intel — must be dropped."""
    from opentrading_mcp.providers import intel as intel_p
    from opentrading_mcp.tools import intel as tools_intel

    def fake_gdelt(query: str = "x", max_records: int = 20):
        return {
            "query": query,
            "articles": [
                {"title": "ĐT Việt Nam chuẩn bị cho trận đại chiến bóng đá", "url": "http://vov.vn/the-thao/x"},
                {"title": "US imposes new sanctions on oil exports", "url": "https://reuters.com/a"},
                {"title": "Military drill near Taiwan Strait escalates", "url": "https://cna.com/b"},
                {"title": "Football final results", "url": "http://x.com/c"},
            ],
        }

    monkeypatch.setattr(intel_p, "gdelt_events", fake_gdelt)
    monkeypatch.setattr(tools_intel, "_call", fake_ok(fake_gdelt()))
    fn = _tool_fn("geo_intel")
    env = await fn(topic="vietnam")
    _check_envelope(env, "geo_intel")
    data = env["data"]
    assert data["count"] == 2, data
    assert data["top_sources"], "aggregate missing"
    assert data["date_range"] is not None or data["by_day"] == {}
    assert any("sanction" in a["title"] for a in data["articles"])
    assert not any("bóng đá" in a["title"] for a in data["articles"])
    assert any("non-political" in w for w in (env["warnings"] or [])), env["warnings"]


async def test_geo_intel_military_mode(monkeypatch):
    """Eval feedback (S4): military aircraft frequency near conflict zones (oracle 8010 port)."""
    from opentrading_mcp.providers import geo as geo_p
    from opentrading_mcp.tools import intel as tools_intel

    def fake_flights(timeout: float = 15.0):
        return [
            {"hex": "ae1234", "callsign": "RCH123", "model": "C17", "type": "transport",
             "operator_country": "US", "lat": 47.0, "lng": 32.0, "alt_m": 9000,
             "gs_kt": 400, "nearest_zone": "ukraine", "zone_label": "Ukraine War",
             "zone_km": 120.0},
            {"hex": "44abcd", "callsign": "ZZZ", "model": "UNKNOWN", "type": "mil-other",
             "operator_country": "UK", "lat": 10.0, "lng": 107.0, "alt_m": 5000,
             "gs_kt": 300, "nearest_zone": "myanmar", "zone_label": "Myanmar Conflict",
             "zone_km": 1200.0},
        ]

    monkeypatch.setattr(geo_p, "military_flights", fake_flights)
    monkeypatch.setattr(tools_intel, "_call", fake_ok(fake_flights()))
    fn = _tool_fn("geo_intel")
    env = await fn(military=True)
    _check_envelope(env, "geo_intel")
    data = env["data"]
    assert data["count"] == 2
    assert data["by_country"] == {"US": 1, "UK": 1}
    assert data["near_zone"][0]["nearest_zone"] == "ukraine"
    assert "lost_near_zone" in data and "reacquired" in data
    assert env["provenance"]["source"] == "adsb.lol"


async def test_event_stats_aggregate_shape(monkeypatch):
    """06-10: event_stats distinct from geo_intel — aggregate + ≤5 articles."""
    from opentrading_mcp.providers import intel as intel_p
    from opentrading_mcp.tools import compute_intel as comp_intel

    def fake_gdelt(query: str = "stock market", max_records: int = 20):
        return {
            "query": query,
            "articles": [
                {"title": f"event {i}", "url": f"https://src{i % 2}.com/{i}",
                 "date": f"2026-10-0{i % 5 + 1}"}
                for i in range(9)
            ],
        }

    monkeypatch.setattr(intel_p, "gdelt_events", fake_gdelt)
    monkeypatch.setattr(comp_intel, "_call", fake_ok(fake_gdelt()))
    fn = _tool_fn("event_stats")
    env = await fn(query="vietnam")
    _check_envelope(env, "event_stats")
    data = env["data"]
    assert data["count"] == 9
    assert len(data["articles"]) <= 5
    assert data["top_sources"] and data["by_day"]


async def test_valuation_run_btype_validation(monkeypatch):
    """Eval feedback (S9): btype→method reference + unknown btype warns."""
    from opentrading_mcp.providers import vietstock as vs_p
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.tools import compute_financial as comp_fin

    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        if tool == "v":
            return {"EPS": 5.0, "BVPS": 20.0}
        return [{"close_price": 100.0}]

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(vs_p, "overview_trading", lambda s: {})
    monkeypatch.setattr(vn_p, "equity_quote_batch", lambda syms: [])
    fn = _tool_fn("valuation_run")
    env = await fn(symbol="VCB", btype=3)
    _check_envelope(env, "valuation_run")
    assert env["data"]["method"] == "pb_bank_broker"
    env = await fn(symbol="VCB", btype=2)
    assert env["data"]["method"] == "pb_bank_broker"
    env = await fn(symbol="FPT", btype=1)
    assert env["data"]["method"] == "per_pb"
    env = await fn(symbol="FPT", btype=99)
    assert env["data"]["method"] == "per_pb"
    assert any("unknown btype" in w for w in (env["warnings"] or [])), env["warnings"]


def fake_ok(value: Any):
    async def _inner(*a: Any, **k: Any) -> Any:
        return value

    return _inner
