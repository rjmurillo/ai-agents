"""Copies of one rule across skill-bootstrap scripts must agree (issue #6666).

Skill scripts do not import each other, so the JSON fence rule and the line-count
rule are repeated. `test_skill_name_rule.py` pins the name rule the same way.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from bootstrap_helpers import run_git

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".claude" / "skills" / "skill-bootstrap" / "scripts"
RUNNER = ROOT / "scripts" / "eval" / "eval_skill_bootstrap_capability.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"shared_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"shared_{name}"] = module
    spec.loader.exec_module(module)
    return module


evaluator = _load("bootstrap_eval", SCRIPTS / "bootstrap_eval.py")
drift = _load("bootstrap_drift", SCRIPTS / "bootstrap_drift.py")
mine = _load("bootstrap_mine", SCRIPTS / "bootstrap_mine.py")
runner = _load("runner", RUNNER)

FENCE_TEXTS = {
    "no fence": "just prose",
    "one block": '```json\n{"a": 1}\n```',
    "two blocks, last wins": '```json\n{"a": 1}\n```\ntext\n```json\n{"a": 2}\n```',
    "unterminated draft then final": '```json\n{"draft": 1\n```json\n{"a": 3}\n```',
    "non-object last, object before": '```json\n{"a": 1}\n```\n```json\n[1, 2]\n```',
    "invalid last, object before": '```json\n{"a": 1}\n```\n```json\n{oops\n```',
    "upper-case tag": '```JSON\n{"a": 4}\n```',
    "trailing blanks after tag": '```json  \t\n{"a": 5}\n```',
    "crlf after tag": '```json\r\n{"a": 6}\r\n```',
    "other language fence": '```python\n{"a": 7}\n```',
    "empty text": "",
    "block with no closing fence": '```json\n{"a": 8}',
    "deep nesting skipped": '```json\n{"a": 9}\n```\n```json\n' + "[" * 200_000 + "\n```",
}


@pytest.mark.parametrize("text", FENCE_TEXTS.values(), ids=FENCE_TEXTS.keys())
def test_eval_and_runner_pick_the_same_json_block(text: str) -> None:
    assert evaluator.extract_last_json_object(text) == runner.extract_answer(text)


def test_eval_and_runner_share_one_fence_pattern() -> None:
    assert evaluator.JSON_FENCE.pattern == runner.JSON_BLOCK.pattern
    assert evaluator.JSON_FENCE.flags == runner.JSON_BLOCK.flags


LINE_TEXTS = {
    "empty": ("", 0),
    "no newline": ("a", 1),
    "one line": ("a\n", 1),
    "two lines": ("a\nb\n", 2),
    "no trailing newline": ("a\nb", 2),
    "blank lines": ("\n\n\n", 3),
    "form feeds are not breaks": ("a\fb\fc\n", 1),
    # Text-mode reads translate a lone CR to a newline, in all three counters.
    "lone carriage returns become breaks": ("a\rb\rc\n", 3),
    "crlf is one break": ("a\r\nb\r\n", 2),
    "unicode separators are not breaks": ("a b\u0085c\n", 1),
}


def _drift_count(tmp_path: Path, text: str) -> int:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "f.txt").write_bytes(text.encode("utf-8"))
    probe = 1_000_000
    check = {"id": "L", "kind": "line_count_at_least", "path": "f.txt", "min": probe}
    detail = drift.evaluate_check(check, repo, False, float("inf"))["detail"]
    return int(detail.split(" lines")[0])


def _mine_disk_count(tmp_path: Path, text: str) -> int:
    repo = tmp_path / "mrepo"
    repo.mkdir(exist_ok=True)
    (repo / "f.txt").write_bytes(text.encode("utf-8"))
    view = object.__new__(mine.RepoView)
    view._root = repo
    count = 0
    while view.disk_status("f.txt", count + 1) == "ok":
        count += 1
    return count


def _mine_blob_count(tmp_path: Path, text: str) -> int:
    repo = tmp_path / "grepo"
    repo.mkdir(exist_ok=True)
    setup = [
        ("init", "-q"),
        ("config", "user.name", "T"),
        ("config", "user.email", "t@e.x"),
        ("config", "commit.gpgsign", "false"),
        ("config", "core.autocrlf", "false"),
    ]
    for args in setup:
        run_git(repo, *args)
    (repo / "f.txt").write_bytes(text.encode("utf-8"))
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "chore: fixture")
    view = mine.RepoView(repo, mine.resolve_rev(repo, "HEAD"))
    return int(view.line_count("f.txt"))


@pytest.mark.parametrize(("text", "lines"), LINE_TEXTS.values(), ids=LINE_TEXTS.keys())
def test_drift_and_mine_count_lines_alike(tmp_path: Path, text: str, lines: int) -> None:
    assert _drift_count(tmp_path, text) == lines
    assert _mine_disk_count(tmp_path, text) == lines
    assert _mine_blob_count(tmp_path, text) == lines
