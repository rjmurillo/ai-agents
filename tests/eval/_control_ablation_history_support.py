"""A throwaway git repository with one real bug and its shipped fix (issue #6814).

The base commit holds a `calc.half` that floors instead of halving, a visible
test that still passes on it, and the control files; the fix commit corrects
the code and adds the test that catches the bug. Historical-task tests read
both commits through the same `git archive`/`git show` path a live run uses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BUGGY = "def half(n):\n    return n // 2\n"
FIXED = "def half(n):\n    return n / 2\n"
VISIBLE_TEST = (
    "import unittest\n\nfrom calc import half\n\n\n"
    "class TestHalf(unittest.TestCase):\n"
    "    def test_even(self):\n"
    "        self.assertEqual(half(4), 2)\n"
)
WITHHELD_TEST = VISIBLE_TEST + "\n    def test_odd(self):\n        self.assertEqual(half(3), 1.5)\n"
CONTROL_FILES = {
    "AGENTS.md": "# agents\n",
    "CLAUDE.md": "@AGENTS.md\n",
    ".claude/rules/voice.md": "# voice\n" + "prose rule\n" * 10,
    ".claude/rules/universal.md": "# universal\n",
}
WITHHELD_PATH = "tests/test_withheld.py"


@dataclass(frozen=True)
class HistoryRepo:
    root: Path
    base_sha: str
    fix_sha: str


def git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout.strip()


def _write(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def make_history_repo(root: Path) -> HistoryRepo:
    root.mkdir(parents=True)
    git(root, "init", "--quiet")
    _write(
        root,
        {
            "calc.py": BUGGY,
            "tests/__init__.py": "",
            "tests/test_calc.py": VISIBLE_TEST,
            **CONTROL_FILES,
        },
    )
    git(root, "add", "-A")
    git(root, "commit", "--quiet", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    _write(root, {"calc.py": FIXED, "tests/test_calc.py": WITHHELD_TEST})
    git(root, "commit", "--quiet", "-am", "fix")
    return HistoryRepo(root=root, base_sha=base, fix_sha=git(root, "rev-parse", "HEAD"))


def make_historical_task(repo: HistoryRepo, **overrides: object) -> dict[str, Any]:
    task: dict[str, Any] = {
        "id": "half-odd",
        "case": "historical_fix",
        "prompt": "Issue 7: half(3) returns 1, expected 1.5.",
        "source": {
            "repository": "example/calc",
            "issue": 7,
            "fix_pr": 8,
            "base_sha": repo.base_sha,
            "fix_sha": repo.fix_sha,
            "seed_paths": ["calc.py", "tests"],
            "withheld_files": {WITHHELD_PATH: "tests/test_calc.py"},
        },
        "allowed_paths": ["calc.py", "tests/*.py"],
        "acceptance": ["{python}", "-m", "unittest", "tests.test_calc"],
        "followup": ["{python}", "-m", "unittest", "tests.test_withheld"],
        "external_marker": None,
        "response_checks": [],
        "controls": {
            "known_good": {"files_from_fix": ["calc.py"], "response": "Fixed half."},
            "known_bad": {
                "edits": [{"path": "calc.py", "old": "n // 2", "new": "round(n / 2)"}],
                "response": "Fixed half.",
            },
        },
    }
    task.update(overrides)
    return task


def make_historical_document(repo: HistoryRepo, *tasks: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 2, "tasks": list(tasks) or [make_historical_task(repo)]}


def write_document(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def tool_use(name: str, **tool_input: object) -> dict[str, object]:
    """One stream-json `tool_use` block."""
    return {"type": "tool_use", "name": name, "input": tool_input}


def history_tasks(repo: HistoryRepo) -> list[Any]:
    """The default historical document's tasks, checks bound to this interpreter."""
    import _control_ablation_history as history

    document = make_historical_document(repo)
    return history.load_historical_tasks(document, repo.root, sys.executable).tasks


def live_args(repo: HistoryRepo, tmp_path: Path, *extra: str) -> list[str]:
    """CLI args for a live run of the default historical document into `tmp_path`."""
    tasks_file = write_document(tmp_path / "tasks.json", make_historical_document(repo))
    return [
        "--tasks",
        str(tasks_file),
        "--workspace-root",
        str(tmp_path / "ws"),
        "--output-dir",
        str(tmp_path / "out"),
        *extra,
    ]
