"""Contract: symbol_resolve multi-asset resolver (TDD, Phase A2)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str, preset: str = "market"):
    server = create_server(preset)
    register_preset(server, preset)
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


FAKE_LISTING = [
    {"symbol": "FPT", "name": "CTCP FPT"},
    {"symbol": "HPG", "name": "CTCP Tap doan Hoa Phat"},
    {"symbol": "VCB", "name": "Ngan hang TMCP Ngoai thuong Viet Nam"},
    {"symbol": "HAP", "name": "CTCP Hapaco"},
    {"symbol": "HPA", "name": "CTCP Phat trien Nong nghiep Hoa Phat"},
]


def _patch_listing(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p

    monkeypatch.setattr(vn_p, "listing_symbols", lambda: list(FAKE_LISTING))


async def test_exact_vn_symbol_resolves_top(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="FPT")
    _check_envelope(env, "symbol_resolve")
    d = env["data"]
    assert d["resolved"]["symbol"] == "FPT"
    assert d["resolved"]["asset_class"] == "vn_equity"
    assert d["resolved"]["score"] == 100
    assert d["ambiguous"] is False


async def test_accented_name_matches(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="hòa phát")
    d = env["data"]
    syms = [c["symbol"] for c in d["candidates"]]
    # genuinely matches both HPG and HPA -> ambiguous with both listed
    assert "HPG" in syms and "HPA" in syms
    assert d["ambiguous"] is True


async def test_crypto_detected(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="BTC")
    r = env["data"]["resolved"]
    assert r["symbol"] == "BTCUSDT"
    assert r["asset_class"] == "crypto"
    assert "crypto_spot" in r["use_tool"]


async def test_crypto_spelling_variants(monkeypatch):
    _patch_listing(monkeypatch)
    for q in ("btc-usdt", "BTC/USDT", "btc usdt"):
        env = await _tool_fn("symbol_resolve")(query=q)
        assert env["data"]["resolved"]["symbol"] == "BTCUSDT", q


async def test_forex_pair(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="USDVND")
    r = env["data"]["resolved"]
    assert r["asset_class"] == "forex"
    assert r["symbol"] == "USDVND"


async def test_futures_detected(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="VN30F1M")
    r = env["data"]["resolved"]
    assert r["asset_class"] == "vn_futures"
    assert r["symbol"] == "VN30F1M"


async def test_global_alias(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="S&P 500")
    r = env["data"]["resolved"]
    assert r["symbol"] == "^GSPC"
    assert r["asset_class"] == "global_index"


async def test_commodity_vietnamese(monkeypatch):
    _patch_listing(monkeypatch)
    for q, sym in (("vàng", "GC=F"), ("gold", "GC=F"), ("dầu brent", "BZ=F")):
        env = await _tool_fn("symbol_resolve")(query=q)
        assert env["data"]["resolved"]["symbol"] == sym, q


async def test_ambiguous_returns_fallback_list(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="HPA")
    d = env["data"]
    # HPA exact exists but HAP is close -> either resolved HPA or ambiguous flag
    syms = [c["symbol"] for c in d["candidates"]]
    assert "HPA" in syms and "HAP" in syms
    assert d["ambiguous"] is True or d["resolved"]["symbol"] == "HPA"


async def test_unknown_returns_empty(monkeypatch):
    _patch_listing(monkeypatch)
    env = await _tool_fn("symbol_resolve")(query="ZZZQQQ")
    _check_envelope(env, "symbol_resolve")
    assert env["availability"] == "empty"
    assert env["data"]["candidates"] == []


async def test_listing_failure_still_returns_pattern_hits(monkeypatch):
    from opentrading_mcp.providers import vnstock as vn_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    def boom():
        raise ProviderUnavailable("vnstock listing failed")

    monkeypatch.setattr(vn_p, "listing_symbols", boom)
    env = await _tool_fn("symbol_resolve")(query="ETH")
    _check_envelope(env, "symbol_resolve")
    assert env["data"]["resolved"]["symbol"] == "ETHUSDT"
    assert env["warnings"], "pattern-only mode must warn"
