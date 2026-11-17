"""#154: run_blocking labels are tool names, not one-letter codes.

The label surfaces in shed/timeout messages ("o shed: server busy") and logs;
single letters made production logs unreadable.
"""

from __future__ import annotations

import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "src" / "opentrading_mcp" / "tools"


def test_no_single_letter_call_labels():
    offenders = []
    for path in sorted(TOOLS.glob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'_call\("[a-z]{1,2}"', line):
                offenders.append(f"{path.name}:{i}: {line.strip()[:80]}")
    assert not offenders, "\n".join(offenders)


def test_labels_name_the_calling_tool():
    brief = (TOOLS / "brief.py").read_text(encoding="utf-8")
    assert '_call("brief_build"' in brief
    assert '_call("market_brief_world"' in brief or '_call("brief_build"' in brief
