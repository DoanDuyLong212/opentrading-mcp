"""M1 hygiene: compact tools/list and results, annotations, instructions, hints."""

from __future__ import annotations

import json
from typing import Any

import pytest

from opentrading_mcp.app import clean_schema
from opentrading_mcp.hints import HINTS, MAX_HINT_CHARS, SEARCH_HINT_KEY
from opentrading_mcp.server import PRESETS, SERVER_INSTRUCTIONS, create_server, register_preset

# Compact UTF-8 bytes of tools/list per preset, measured after M1 plus ~5% headroom.
# Raise deliberately (and say why in the PR) when adding tools or text.
BUDGET = {
    "market": 31_700,
    "scan": 25_000,
    "quant": 5_700,
    "brief": 3_800,
    "intel": 3_900,
    "all": 69_500,
}


def _server(preset: str):
    server = create_server(preset)
    register_preset(server, preset)
    return server


def _tools_list_bytes(tools: list[Any]) -> int:
    dumped = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools]
    return len(json.dumps(dumped, separators=(",", ":"), ensure_ascii=False).encode())


def _walk(node: Any, path: str = ""):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for name, schema in value.items():
                    yield from _walk(schema, f"{path}.{name}")
            else:
                yield from _walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")


@pytest.mark.parametrize("preset", PRESETS)
async def test_tools_list_is_compact_and_within_budget(preset):
    tools = await _server(preset).list_tools()
    for tool in tools:
        assert tool.outputSchema is None, tool.name
        for path, node in _walk(tool.inputSchema):
            assert not isinstance(node.get("title"), str), f"{tool.name}{path}: title"
            variants = node.get("anyOf") or []
            assert {"type": "null"} not in variants or len(variants) > 2, (
                f"{tool.name}{path}: anyOf null"
            )
        assert not tool.description.startswith(" ") and "\n        " not in tool.description, (
            tool.name
        )
    size = _tools_list_bytes(tools)
    assert size <= BUDGET[preset], f"{preset}: tools/list is {size} bytes, budget {BUDGET[preset]}"


async def test_every_tool_has_a_short_search_hint():
    tools = await _server("all").list_tools()
    names = {t.name for t in tools} | {"web_search"}  # web_search registers only with a key
    assert set(HINTS) == names, sorted(set(HINTS) ^ names)
    for tool in tools:
        hint = (tool.meta or {}).get(SEARCH_HINT_KEY)
        assert hint, tool.name
        assert len(hint) <= MAX_HINT_CHARS, tool.name


def test_clean_schema_keeps_parameters_named_title_and_collapses_optional():
    schema = {
        "title": "argsModel",
        "type": "object",
        "properties": {
            "title": {"title": "Title", "type": "string"},
            "limit": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "title": "Limit",
            },
            "kind": {"anyOf": [{"type": "string"}, {"type": "integer"}], "title": "Kind"},
        },
        "required": ["title"],
    }
    assert clean_schema(schema) == {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "limit": {"type": "integer"},
            "kind": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        },
        "required": ["title"],
    }


def test_instructions_fit_client_caps():
    assert len(SERVER_INSTRUCTIONS.encode()) <= 2048
    assert "Asia/Ho_Chi_Minh" in SERVER_INSTRUCTIONS
    # No stale claims: every tool the routing guide names exists.
    import re

    names = {t.name for t in _server("all")._tool_manager.list_tools()}
    mentioned = set(re.findall(r"\b[a-z]+(?:_[a-z0-9]+)+\b", SERVER_INSTRUCTIONS)) - {
        "as_of",
        "term_types",
    }
    assert mentioned <= names, sorted(mentioned - names)


async def test_write_annotations_describe_the_effect():
    tools = {t.name: t for t in await _server("all").list_tools()}
    for name in ("watchlist_delete", "watchlist_remove", "alert_delete"):
        assert tools[name].annotations.destructiveHint is True, name
    for name in ("watchlist_create", "alert_create"):
        assert tools[name].annotations.idempotentHint is False, name
    assert tools["market_snapshot"].annotations.readOnlyHint is True


async def test_result_is_one_compact_text_block_with_iserror_on_unavailable(monkeypatch):
    import opentrading_mcp.tools.brief as brief_mod

    server = _server("brief")

    async def ok_call(tool: str, fn: Any, *args: Any, **kwargs: Any):
        return [{"title": "Tài liệu ĐHCĐ"}]

    monkeypatch.setattr(brief_mod, "_call", ok_call)
    result = await server.call_tool("corporate_calendar", {"symbol": "VCB", "limit": 1})
    assert result.isError is False
    assert result.structuredContent is None
    assert len(result.content) == 1
    text = result.content[0].text
    assert "\n" not in text and "Tài liệu ĐHCĐ" in text  # compact, UTF-8 (no \\u escapes)
    assert json.loads(text)["provenance"]["as_of"].endswith("+07:00")

    from opentrading_mcp.providers.errors import ProviderUnavailable

    async def down(tool: str, fn: Any, *args: Any, **kwargs: Any):
        raise ProviderUnavailable("vietstock down")

    monkeypatch.setattr(brief_mod, "_call", down)
    failed = await server.call_tool("corporate_calendar", {"symbol": "VCB"})
    assert failed.isError is True
    assert json.loads(failed.content[0].text)["availability"] == "unavailable"
