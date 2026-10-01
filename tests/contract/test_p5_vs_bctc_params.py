"""P5 contract: enriched params for vs_bctc.py tools (TDD)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def _tool_fn(name: str):
    server = create_server("market")
    register_preset(server, "market")
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"tool {name} not registered"
    return tool.fn


def _check_envelope(env: dict[str, Any], tool: str) -> None:
    for key in ("data", "provenance", "warnings", "availability"):
        assert key in env, f"{tool}: envelope missing {key!r}"
    assert env["provenance"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert env["availability"] in {"available", "empty", "stale", "partial", "unavailable"}


async def test_vs_financial_values_accepts_tids(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_values(symbol: str, btype: int = 1, years: int = 3, tids: list[int] | None = None):
        seen.update(symbol=symbol, btype=btype, years=years, tids=tids)
        return {"rows": []}

    monkeypatch.setattr(vs_p, "financial_values", fake_values)
    fn = _tool_fn("vs_financial_values")
    env = await fn(symbol="VCB", btype=3, years=2, tids=[4, 5])
    _check_envelope(env, "vs_financial_values")
    assert seen == {"symbol": "VCB", "btype": 3, "years": 2, "tids": [4, 5]}


async def test_vs_financial_values_default_tids_none(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_values(symbol: str, btype: int = 1, years: int = 3, tids: list[int] | None = None):
        seen["tids"] = tids
        return {"rows": []}

    monkeypatch.setattr(vs_p, "financial_values", fake_values)
    fn = _tool_fn("vs_financial_values")
    await fn(symbol="VCB")
    assert seen["tids"] is None


async def test_vs_documents_accepts_page_size(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_documents(symbol: str, page_size: int = 60):
        seen.update(symbol=symbol, page_size=page_size)
        return []

    monkeypatch.setattr(vs_p, "documents", fake_documents)
    fn = _tool_fn("vs_documents")
    env = await fn(symbol="FPT", page_size=10)
    _check_envelope(env, "vs_documents")
    assert seen == {"symbol": "FPT", "page_size": 10}


async def test_vs_xnk_detail_accepts_range(monkeypatch):
    from opentrading_mcp.providers import vietstock as vs_p

    seen: dict[str, Any] = {}

    def fake_macro(tt: int, cat: int, sub: str = "", frm: str = "2022-01-01") -> Any:
        seen.update(tt=tt, cat=cat, sub=sub, frm=frm)
        return {"rows": [{"name": "Trung Quoc", "value": 1.0}]}

    monkeypatch.setattr(vs_p, "macro_report_data", fake_macro)
    fn = _tool_fn("vs_xnk_detail")
    env = await fn(direction="nk", from_date="2022-01-01")
    _check_envelope(env, "vs_xnk_detail")
    assert seen == {"tt": 2, "cat": 65, "sub": "", "frm": "2022-01-01"}
    assert env["data"]["direction"] == "nk"
