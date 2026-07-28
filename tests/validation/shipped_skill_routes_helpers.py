"""Fixtures and builders shared by the shipped-route gate suites.

The gate is exercised through ``subprocess`` rather than by importing it, which
pins the CLI exit contract the pre-push and CI callers depend on and avoids the
dataclass-at-collection-time failure that importlib loading produces.

Kept out of ``conftest.py`` because the ``repo`` fixture is specific to this
gate; a generic name in the package-wide conftest would be visible to every
validation suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_shipped_skill_routes.py"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2

TREES = (".claude", "src/copilot-cli")


def run_gate(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def write_manifest(root: Path, tree: str) -> None:
    path = root / tree / ".claude-plugin" / "plugin.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")


def write_skill(root: Path, tree: str, name: str, body: str = "") -> Path:
    path = root / tree / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body or f"# {name}\n", encoding="utf-8")
    return path


def drop_skill(root: Path, tree: str, name: str) -> None:
    (root / tree / "skills" / name / "SKILL.md").unlink()


def write_doc(root: Path, tree: str, name: str, body: str) -> Path:
    """Write a non-SKILL markdown file inside a skill directory."""
    path = root / tree / "skills" / "autoplan" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal two-root repo in which every route resolves."""
    for tree in TREES:
        write_manifest(tmp_path, tree)
        write_skill(
            tmp_path,
            tree,
            "autoplan",
            "| Task | Route |\n| --- | --- |\n| Merge | Skill: merge-resolver |\n",
        )
        write_skill(tmp_path, tree, "merge-resolver")
    return tmp_path
