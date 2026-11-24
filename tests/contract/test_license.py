"""#155: the repository declares a license and ships the file it points to."""

from __future__ import annotations

import pathlib
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_license_file_is_mit() -> None:
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "WITHOUT WARRANTY OF ANY KIND" in text


def test_project_metadata_declares_the_same_license() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == "MIT"
    assert "LICENSE" in project["license-files"]
    assert (REPO / project["license-files"][0]).is_file()


def test_readme_points_at_the_license_and_its_scope() -> None:
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "LICENSE" in text
    # MIT covers this repo's code, not the upstream data/package terms.
    assert "điều khoản riêng" in text
