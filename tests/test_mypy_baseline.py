"""#98: the mypy baseline gate fails on new errors only."""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "mypy_baseline", Path(__file__).resolve().parents[1] / "scripts" / "mypy_baseline.py"
)
assert _SPEC and _SPEC.loader
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)

OUT = """\
src\\opentrading_mcp\\a.py:10: error: Value of type "int" is not indexable  [index]
src/opentrading_mcp/a.py:22: error: Value of type "int" is not indexable  [index]
src/opentrading_mcp/b.py:3:5: error: Missing return statement  [return]
src/opentrading_mcp/b.py:4: note: See https://mypy.readthedocs.io
Found 3 errors in 2 files (checked 2 source files)
"""


def test_parse_ignores_line_numbers_and_notes():
    keys = gate.parse(OUT)
    assert keys == Counter({
        'src/opentrading_mcp/a.py|index|Value of type "int" is not indexable': 2,
        "src/opentrading_mcp/b.py|return|Missing return statement": 1,
    })


def test_new_kind_or_higher_count_fails_fewer_passes():
    baseline = gate.parse(OUT)
    assert gate.new_errors(baseline, baseline) == []
    fewer = baseline.copy()
    fewer["src/opentrading_mcp/b.py|return|Missing return statement"] = 0
    assert gate.new_errors(fewer, baseline) == []
    more = baseline.copy()
    more['src/opentrading_mcp/a.py|index|Value of type "int" is not indexable'] = 3
    more["src/opentrading_mcp/c.py|arg-type|bad"] = 1
    added = gate.new_errors(more, baseline)
    assert len(added) == 2 and any("c.py" in line for line in added)


def test_baseline_round_trips(tmp_path):
    keys = gate.parse(OUT)
    target = tmp_path / "baseline.txt"
    gate.dump(keys, target)
    assert gate.load(target) == keys
