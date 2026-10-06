"""Full-matrix contract test: every tool, single surface, over real stdio."""

from opentrading_mcp.verify_matrix import all_calls, run_stdio_all


async def test_full_matrix_stdio():
    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    tools = register_all(server)
    calls = all_calls()
    assert len(calls) == len(tools) == 139, f"matrix {len(calls)} vs tools {len(tools)}"
    rows = await run_stdio_all()
    assert rows, "matrix returned no rows"
    assert len(rows) == len(calls)
    failures = [f"{row['tool']}: {row['detail']}" for row in rows if not row["ok"]]
    assert not failures, "contract failures:\n" + "\n".join(failures)
