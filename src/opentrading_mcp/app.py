"""FastMCP subclass that keeps tools/list and tool results small.

One hook point instead of touching every ``@server.tool`` decorator:

- ``tool()``: no outputSchema/structuredContent (every tool returns the same
  generic envelope, so the schema said nothing and the payload went out twice);
  docstrings dedented; per-tool annotation overrides and ``_meta`` search hints.
- ``list_tools()``: input schemas without pydantic ``title`` keys and with
  ``anyOf: [X, null]`` collapsed to ``X``.
- ``call_tool()``: an envelope becomes ONE compact JSON text block, and
  ``isError`` is set when ``availability == "unavailable"``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pydantic_core
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.func_metadata import _convert_to_content
from mcp.types import CallToolResult, Icon, TextContent, ToolAnnotations
from mcp.types import Tool as MCPTool

from opentrading_mcp.hints import search_meta
from opentrading_mcp.tools.shared import ANNOTATION_OVERRIDES

_ENVELOPE_KEYS = frozenset({"data", "provenance", "warnings", "availability"})


def clean_schema(node: Any) -> Any:
    """Drop noise pydantic adds to a JSON Schema; parameter names are never touched.

    - ``title`` keywords go (``properties`` is a name -> schema map, so a
      parameter literally named ``title`` survives).
    - ``anyOf: [X, {"type": "null"}]`` becomes ``X``; ``default: null`` goes.
    """
    if isinstance(node, list):
        return [clean_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "title" and isinstance(value, str):
            continue
        if key == "default" and value is None:
            continue
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            out[key] = {name: clean_schema(schema) for name, schema in value.items()}
        else:
            out[key] = clean_schema(value)
    variants = out.get("anyOf")
    if isinstance(variants, list):
        rest = [v for v in variants if v != {"type": "null"}]
        if len(rest) == 1 and len(rest) < len(variants) and isinstance(rest[0], dict):
            merged = {k: v for k, v in out.items() if k != "anyOf"}
            return {**rest[0], **merged}
    return out


def envelope_result(result: dict[str, Any]) -> CallToolResult:
    text = pydantic_core.to_json(result, fallback=str).decode()
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=result.get("availability") == "unavailable",
    )


class OpenTradingMCP(FastMCP):
    """FastMCP with compact schemas and results (see module docstring)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._listed: list[MCPTool] | None = None

    def tool(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
        icons: list[Icon] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Any], Any]:
        def decorator(fn: Any) -> Any:
            tool_name = name or fn.__name__
            self._listed = None
            return super(OpenTradingMCP, self).tool(
                name=name,
                title=title,
                description=description or inspect.cleandoc(fn.__doc__ or ""),
                annotations=ANNOTATION_OVERRIDES.get(tool_name, annotations),
                icons=icons,
                meta={**search_meta(tool_name), **(meta or {})} or None,
                structured_output=False if structured_output is None else structured_output,
            )(fn)

        return decorator

    async def list_tools(self) -> list[MCPTool]:
        if self._listed is None:
            tools = await super().list_tools()
            self._listed = [
                t.model_copy(
                    update={"inputSchema": clean_schema(t.inputSchema), "outputSchema": None}
                )
                for t in tools
            ]
        return self._listed

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        raw = await self._tool_manager.call_tool(
            name, arguments, context=self.get_context(), convert_result=False
        )
        if isinstance(raw, dict) and _ENVELOPE_KEYS <= raw.keys():
            return envelope_result(raw)
        return _convert_to_content(raw)
