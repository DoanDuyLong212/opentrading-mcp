"""P12b contract: sentiment list-body + money_flow fallback path (TDD RED)."""

from __future__ import annotations

from typing import Any

from opentrading_mcp.server import create_server, register_preset


def test_fireant_posts_accepts_bare_list(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    monkeypatch.setenv("FIREANT_TOKEN", "test-token")

    class FakeResp:
        status_code = 200

        def json(self) -> Any:
            return [{"post_id": 1, "content": "VCB ngon", "user": {"name": "a"}, "likes": 5}]

    class FakeClient:
        def get(self, *a: Any, **k: Any) -> Any:
            return FakeResp()

        def post(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("no POST expected here")

    monkeypatch.setattr(intel_p, "_client", lambda: FakeClient())
    out = intel_p.fireant_posts("VCB", 3)
    assert isinstance(out, list) and len(out) == 1


async def test_money_flow_uses_nn_chart_fallback(monkeypatch):
    from opentrading_mcp.providers import dnse as dnse_p
    from opentrading_mcp.providers.errors import ProviderUnavailable

    def boom(symbols: list[str] | None = None) -> Any:
        raise ProviderUnavailable("ws worker has not published yet")

    async def fake_block(fn: Any, tool: str, timeout_secs: float = 60.0) -> Any:
        from opentrading_mcp.providers import vietstock as vs_mod

        # nn_flow_chart is submitted directly; the ws leg arrives as a
        # functools.partial (P02 offload) — invoking it raises the patched
        # ProviderUnavailable and triggers this fallback.
        if fn is vs_mod.nn_flow_chart or getattr(fn, "func", None) is vs_mod.nn_flow_chart:
            return [["/Date(1)/"], [{"BuyVol": 2.0}]]
        return fn()

    monkeypatch.setattr(dnse_p, "ws_snapshot", boom)
    import opentrading_mcp.tools.scan as scan_mod

    monkeypatch.setattr(scan_mod, "run_blocking", fake_block)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("money_flow")
    assert tool is not None
    env = await tool.fn(symbols=["VNINDEX"])
    assert env["availability"] == "available"
    assert env["data"]["primary"] == "vietstock"


async def test_sentiment_score_end_to_end(monkeypatch):
    async def fake_call(tool: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if tool == "s":
            return [{"text": "VCB quá ngon, múc mạnh", "likes": 10}]
        return '{"score": 0.8}'

    import opentrading_mcp.tools.compute_financial as comp_fin
    import opentrading_mcp.tools.compute_infra as comp_infra
    import opentrading_mcp.tools.compute_intel as comp_intel

    monkeypatch.setattr(comp_fin, "_call", fake_call)
    monkeypatch.setattr(comp_intel, "_call", fake_call)
    monkeypatch.setattr(comp_infra, "_call", fake_call)
    server = create_server("scan")
    register_preset(server, "scan")
    tool = server._tool_manager.get_tool("sentiment_score")
    assert tool is not None
    env = await tool.fn(symbol="VCB", limit=3)
    assert env["availability"] == "available"


def test_fireant_posts_reads_postid_fields(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    monkeypatch.setenv("FIREANT_TOKEN", "test-token")

    class FakeResp:
        status_code = 200

        def json(self) -> Any:
            return [
                {
                    "postID": 42088453,
                    "description": "PNJ ngon",
                    "user": {"name": "Vo Thi"},
                    "totalLikes": 7,
                    "totalReplies": 2,
                }
            ]

    class FakeClient:
        def get(self, *a: Any, **k: Any) -> Any:
            return FakeResp()

        def post(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("no POST expected here")

    monkeypatch.setattr(intel_p, "_client", lambda: FakeClient())
    out = intel_p.fireant_posts("PNJ", 3)
    assert out[0]["id"] == 42088453
    assert out[0]["user"] == "Vo Thi"
    assert out[0]["likes"] == 7
    assert out[0]["replies"] == 2


def test_fireant_thread_parses_replies(monkeypatch):
    from opentrading_mcp.providers import intel as intel_p

    monkeypatch.setenv("FIREANT_TOKEN", "test-token")

    class FakeResp:
        status_code = 200

        def __init__(self, body: Any):
            self._body = body

        def json(self) -> Any:
            return self._body

    root = {"postID": 1, "description": "root post", "user": {"name": "a"}}
    reps = [
        {"postID": 2, "description": "reply one", "replyToPostID": 1},
        {"postID": 3, "description": "reply two", "replyToPostID": 1},
    ]

    def fake_get(url: str, **kwargs: Any) -> Any:
        if url.endswith("/posts/1"):
            return FakeResp(root)
        assert url.endswith("/posts/1/replies")
        return FakeResp(reps)

    class FakeClient:
        def get(self, url: str, **kwargs: Any) -> Any:
            return fake_get(url, **kwargs)

        def post(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("no POST expected here")

    monkeypatch.setattr(intel_p, "_client", lambda: FakeClient())
    out = intel_p.fireant_thread(1, limit=10)
    assert out["post"]["id"] == 1
    assert out["reply_count"] == 2
    assert out["replies"][0]["id"] == 2
