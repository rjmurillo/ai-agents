"""Shared builders for the closure manifest tests: a throwaway git repository."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

GATE = ".claude/skills/github/scripts/pr/run_completion_gate.py"
SHA = "a" * 40


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )


def make_repo(root: Path, files: dict[str, str], with_gate: bool = True) -> Path:
    """Write ``files`` into ``root``, add the real gate script, and `git add` everything."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    if with_gate:
        target = root / GATE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / GATE).read_bytes())
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    git(root, "add", "-A")
    return root


def workflow(name: str, steps: str, extra: str = "") -> str:
    """A workflow with one job named Run Python Tests."""
    return (
        f"name: wf\non: pull_request\n{extra}jobs:\n  {name}:\n    name: Run Python Tests\n"
        f"    runs-on: ubuntu-latest\n    steps:\n{steps}"
    )
