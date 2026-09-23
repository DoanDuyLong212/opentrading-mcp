"""Full-matrix contract test: every tool, every preset, over real stdio.

Spawns the server exactly like an opencode local entry
(`python -m opentrading_mcp serve --preset X`), lists tools and calls each
one with representative args. Asserts transport success AND the shared
envelope contract (data/provenance/warnings/availability + tz + as_of).
Data availability itself is NOT asserted: empty/unavailable is legitimate
offline, off-hours or without upstream credentials.
"""

from opentrading_mcp.server import PRESETS
from opentrading_mcp.verify_matrix import run_preset_stdio


async def test_full_matrix_all_presets_stdio():
    failures: list[str] = []
    total = 0
    for preset in PRESETS:
        rows = await run_preset_stdio(preset)
        assert rows, f"preset {preset} returned no rows"
        for row in rows:
            total += 1
            if not row["ok"]:
                failures.append(f"{row['preset']}/{row['tool']}: {row['detail']}")
    assert total == 96, f"expected 96 tool calls, got {total}"
    assert not failures, "contract failures:\n" + "\n".join(failures)
