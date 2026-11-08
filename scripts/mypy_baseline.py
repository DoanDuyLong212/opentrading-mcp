"""mypy gate with a baseline (#98): CI fails on NEW mypy errors only.

`pyproject.toml` sets `[tool.mypy] strict = true`, but the code base carries
known errors, so a plain `mypy` step would be red from day one. This gate keys
each error by file + error code + message (no line number, so unrelated edits
that shift lines do not break it) and compares counts with
`mypy-baseline.txt`:

- an error key that is new, or more frequent than in the baseline, fails;
- fewer errors than the baseline passes and asks for `--update`, so the
  baseline only ever shrinks.

Usage:
    uv run python scripts/mypy_baseline.py            # check (CI)
    uv run python scripts/mypy_baseline.py --update   # rewrite the baseline
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "mypy-baseline.txt"
_LINE = re.compile(r"^(?P<path>[^:]+):\d+(?::\d+)?: error: (?P<msg>.*?)\s+\[(?P<code>[\w-]+)\]$")


def parse(output: str) -> Counter[str]:
    """Error keys ``path|code|message`` → count, from mypy's text output."""
    keys: Counter[str] = Counter()
    for raw in output.splitlines():
        match = _LINE.match(raw.strip())
        if match:
            path = match["path"].replace("\\", "/")
            keys[f"{path}|{match['code']}|{match['msg']}"] += 1
    return keys


def load(path: Path = BASELINE) -> Counter[str]:
    keys: Counter[str] = Counter()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                count, _, key = line.partition(" ")
                keys[key] = int(count)
    return keys


def dump(keys: Counter[str], path: Path = BASELINE) -> None:
    header = (
        "# Known mypy errors (scripts/mypy_baseline.py). Never add lines by hand:\n"
        "# fix errors, then run `uv run python scripts/mypy_baseline.py --update`.\n"
    )
    body = "".join(f"{count} {key}\n" for key, count in sorted(keys.items()))
    path.write_text(header + body, encoding="utf-8")


def new_errors(current: Counter[str], baseline: Counter[str]) -> list[str]:
    return [
        f"{key}  (now {count}, baseline {baseline.get(key, 0)})"
        for key, count in sorted(current.items())
        if count > baseline.get(key, 0)
    ]


def run_mypy() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return proc.stdout + proc.stderr


def main(argv: list[str]) -> int:
    current = parse(run_mypy())
    if "--update" in argv:
        dump(current)
        print(f"baseline written: {sum(current.values())} errors")
        return 0
    baseline = load()
    added = new_errors(current, baseline)
    total, known = sum(current.values()), sum(baseline.values())
    if added:
        print(f"{len(added)} new mypy error kind(s) beyond the baseline:")
        print("\n".join(f"  {line}" for line in added))
        return 1
    print(f"mypy: {total} errors, baseline {known}: no new errors")
    if total < known:
        print("errors went down: run `uv run python scripts/mypy_baseline.py --update`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
