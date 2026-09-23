"""Full-matrix contract test: every tool, every preset, over real stdio."""

from opentrading_mcp.server import PRESETS
from opentrading_mcp.verify_matrix import calls_for_preset, run_preset_stdio


async def test_full_matrix_all_presets_stdio():
    failures: list[str] = []
    total = 0
    expected = sum(len(calls_for_preset(preset)) for preset in PRESETS)
    assert expected > 0
    for preset in PRESETS:
        rows = await run_preset_stdio(preset)
        assert rows, f"preset {preset} returned no rows"
        for row in rows:
            total += 1
            if not row["ok"]:
                failures.append(f"{row['preset']}/{row['tool']}: {row['detail']}")
    assert total == expected, f"expected {expected} tool calls, got {total}"
    assert not failures, "contract failures:\n" + "\n".join(failures)
