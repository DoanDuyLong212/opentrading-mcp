"""Print tools/list size per preset: tool count, compact UTF-8 bytes, heaviest tools.

python scripts/measure_tools_list.py [--top 10]
"""

from __future__ import annotations

import argparse
import asyncio
import json

from opentrading_mcp.server import PRESETS, SERVER_INSTRUCTIONS, create_server, register_preset


def _size(obj: object) -> int:
    return len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())


async def main(top: int) -> None:
    print(f"instructions: {len(SERVER_INSTRUCTIONS.encode())} bytes")
    for preset in PRESETS:
        server = create_server(preset)
        register_preset(server, preset)
        tools = [
            t.model_dump(by_alias=True, exclude_none=True, mode="json")
            for t in await server.list_tools()
        ]
        print(f"{preset:7} {len(tools):4} tools {_size(tools):7} bytes")
        if preset == "all":
            for t in sorted(tools, key=_size, reverse=True)[:top]:
                print(f"    {_size(t):5}  {t['name']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10)
    asyncio.run(main(parser.parse_args().top))
