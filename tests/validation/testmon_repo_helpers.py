"""Throwaway-repository helpers for the testmon reselection tests (issues #7126, #7286).

Imported by test_testmon_data_inputs.py and test_testmon_tree_scanners.py. The
name does not match `test_*.py`, so pytest never walks it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.validation import testmon_scoped_sync as sync

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FLAG = f"-p{sync.__name__}"
OTHER_TEST = "def test_other():\n    assert True\n"


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(root: Path, files: dict[str, str]) -> Path:
    """Commit `files` on `main`, then move to a branch so `main` is the merge base."""
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    for rel, text in files.items():
        write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "feature")
    return root


class Select:
    deselected_files: Any
    deselected_tests: Any

    def __init__(self, files: list[str], tests: list[str]) -> None:
        self.deselected_files = files
        self.deselected_tests = tests
        self.testmon_data = object()


def run_pytest(project: Path, *flags: str) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "TESTMON_"))}
    env.update(COVERAGE_CORE="ctrace", PYTHONPATH=str(REPO_ROOT))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--testmon",
            "--testmon-forceselect",
            *flags,
            "-q",
            "-o",
            "addopts=",
            "tests",
        ],
        cwd=project,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr
