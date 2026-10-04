"""Unit tests for web providers + web tool gating (mirror opencode 1:1)."""

import hashlib

from opentrading_mcp.providers import webfetch, websearch


def _exa_body(text: str) -> str:
    payload = (
        '{"result": {"content": [{"type": "text", "text": '
        + __import__("json").dumps(text)
        + "}]}}"
    )
    return payload


def test_parse_response_direct_json_extracts_text():
    assert websearch.parse_response(_exa_body("hello world")) == "hello world"


def test_parse_response_sse_data_lines_extracts_text():
    body = "event: message\ndata: " + _exa_body("from sse") + "\n\n"
    assert websearch.parse_response(body) == "from sse"


def test_parse_response_garbage_returns_none():
    assert websearch.parse_response("not json at all") is None
    assert websearch.parse_response("") is None


def test_select_provider_env_override(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_PROVIDER", "parallel")
    assert websearch.select_provider("anything") == "parallel"
    monkeypatch.setenv("WEBSEARCH_PROVIDER", "exa")
    assert websearch.select_provider("anything") == "exa"


def test_select_provider_deterministic_per_query():
    first = websearch.select_provider("VNINDEX outlook 2026")
    assert websearch.select_provider("VNINDEX outlook 2026") == first
    seen = {websearch.select_provider(f"query {i}") for i in range(20)}
    assert seen == {"exa", "parallel"}


def test_select_provider_matches_opencode_ab_split():
    digest = hashlib.sha256(b"probe").hexdigest()
    expected = "exa" if int(digest, 16) % 2 == 0 else "parallel"
    assert websearch.select_provider("probe") == expected


def test_accept_header_map_per_format():
    assert "text/markdown" in webfetch.accept_header("markdown")
    assert "text/plain" in webfetch.accept_header("text")
    assert "text/html" in webfetch.accept_header("html")


def test_fetch_url_rejects_non_http():
    import pytest

    from opentrading_mcp.providers.errors import ProviderBadData

    with pytest.raises(ProviderBadData):
        webfetch.fetch_url("ftp://example.invalid/x.txt")


def test_web_search_unavailable_without_keys(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    assert websearch.web_search_available() is False


def test_web_search_available_with_key(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    assert websearch.web_search_available() is True


def test_intel_preset_gates_web_search_without_keys(monkeypatch):
    import asyncio

    from opentrading_mcp.server import create_server, register_preset

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    server = create_server("intel")
    names = sorted(t["name"] for t in register_preset(server, "intel"))
    assert "web_fetch" in names
    assert "web_search" not in names
    listed = sorted(t.name for t in asyncio.run(server.list_tools()))
    assert "web_fetch" in listed
    assert "web_search" not in listed


def test_intel_preset_includes_web_search_with_key(monkeypatch):
    from opentrading_mcp.server import create_server, register_preset

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    server = create_server("intel")
    names = sorted(t["name"] for t in register_preset(server, "intel"))
    assert "web_fetch" in names
    assert "web_search" in names


def _tiny_pdf(payload: bytes) -> bytes:
    import zlib

    stream = zlib.compress(b"BT /F1 12 Tf 72 720 Td " + payload + b" Tj ET")
    head = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length " + str(len(stream)).encode() + b"/Filter/FlateDecode>>stream\n"
    )
    return head + stream + b"\nendstream\nendobj\ntrailer<</Root 1 0 R>>"


def test_extract_pdf_text():
    from opentrading_mcp.providers import webfetch

    data = webfetch._extract_pdf(
        _tiny_pdf(b"(Cong hoa Xa hoi Chu nghia Viet Nam - Bao cao tai chinh quy 3 nam 2026)"),
        "t.pdf",
    )
    assert "Cong hoa" in data["output"]
    assert data["chars"] > 10


def test_extract_pdf_scanned_fails_honestly():
    import zlib

    from opentrading_mcp.providers import webfetch

    stream = zlib.compress(b"/Image1 Do")  # no text operators
    pdf = (
        b"%PDF-1.4\n4 0 obj<</Length 1/Filter/FlateDecode>>stream\n"
        + stream
        + b"\nendstream\nendobj"
    )
    try:
        webfetch._extract_pdf(pdf, "scan.pdf")
    except Exception as exc:  # any honest failure ok
        assert "extractable" in str(exc) or "parse" in str(exc) or "PDF" in str(exc)
    else:
        raise AssertionError("scanned pdf must not return fake text")


async def test_web_fetch_pdf_format(monkeypatch):
    from opentrading_mcp.providers import webfetch
    from opentrading_mcp.server import create_server, register_preset

    async def fake_call(tool, fn, *args, **kwargs):
        return webfetch._extract_pdf(
            _tiny_pdf(b"(Bao cao tai chinh Q3 nam 2026 cua cong ty co phan chung khoan)"), "r.pdf"
        )

    import opentrading_mcp.tools.web as web_mod

    monkeypatch.setattr(web_mod, "_call", fake_call)
    server = create_server("all")
    register_preset(server, "all")
    fn = server._tool_manager.get_tool("web_fetch").fn
    env = await fn(url="https://static2.vietstock.vn/x.pdf", format="pdf")
    assert env["availability"] == "available"
    assert "Bao cao" in env["data"]["output"]
