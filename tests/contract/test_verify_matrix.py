"""Full-matrix contract test: every tool, single surface, over real stdio."""

from opentrading_mcp.verify_matrix import all_calls, run_stdio_all


async def test_full_matrix_stdio():
    from opentrading_mcp.server import create_server, register_all

    server = create_server()
    tools = register_all(server)
    calls = all_calls()
    assert len(calls) == len(tools) == 170, f"matrix {len(calls)} vs tools {len(tools)}"
    rows = await run_stdio_all()
    assert rows, "matrix returned no rows"
    assert len(rows) == len(calls)
    failures = [f"{row['tool']}: {row['detail']}" for row in rows if not row["ok"]]
    assert not failures, "contract failures:\n" + "\n".join(failures)


def test_shared_table_writers_are_skipped_unless_enabled(monkeypatch):
    from opentrading_mcp.verify_matrix import (
        SHARED_TABLE_WRITES,
        VERIFY_WRITES_ENV,
        runnable_calls,
    )

    calls = all_calls()
    assert SHARED_TABLE_WRITES <= {tool for tool, _, _ in calls}
    monkeypatch.delenv(VERIFY_WRITES_ENV, raising=False)
    run, skipped = runnable_calls(calls)
    assert set(skipped) == SHARED_TABLE_WRITES
    assert not {tool for tool, _, _ in run} & SHARED_TABLE_WRITES
    assert len(run) + len(skipped) == len(calls)
    monkeypatch.setenv(VERIFY_WRITES_ENV, "1")
    assert runnable_calls(calls) == (calls, [])
