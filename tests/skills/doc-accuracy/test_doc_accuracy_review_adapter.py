"""doc-accuracy gate output through the /review local-axis adapter.

A branch that deletes one Markdown file and edits another must adapt to
PASS on a clean run. Before the fix, the deleted path sat in
``changed_files``, the adapter saw a partial inventory, and the axis
reported UNKNOWN, which blocks the /review PASS marker.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from scripts.ai_review_common.verdict import adapt_local_axis_verdict

main = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy_review_adapter",
).main


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo_with_history(tmp_path: Path, *, edit_kept: bool) -> Path:
    """Commit two docs and a source file, then delete one doc."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "kept.md").write_text("# Kept\n")
    (repo / "gone.md").write_text("# Gone\n")
    (repo / "main.py").write_text("def foo():\n    pass\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    (repo / "gone.md").unlink()
    if edit_kept:
        (repo / "kept.md").write_text("# Kept, edited\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change")
    return repo


def _run_gate(repo: Path, out_dir: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    rc = main(
        [
            "--target",
            str(repo),
            "--diff-base",
            "HEAD~1",
            "--format",
            "gate",
            "--output-dir",
            str(out_dir),
        ]
    )
    return rc, capsys.readouterr().out


def test_delete_and_edit_adapts_to_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_with_history(tmp_path, edit_kept=True)

    rc, output = _run_gate(repo, tmp_path / "out", capsys)

    assert rc == 0
    assert json.loads(output)["assessment"]["changed_files"] == ["kept.md"]
    assert adapt_local_axis_verdict("doc-accuracy", output, rc) == "PASS"


def test_deletion_only_diff_stays_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Edge: a diff that only deletes docs inventories nothing, so no PASS."""
    repo = _repo_with_history(tmp_path, edit_kept=False)

    rc, output = _run_gate(repo, tmp_path / "out", capsys)

    assert rc == 0
    assert json.loads(output)["assessment"]["changed_files"] == []
    assert adapt_local_axis_verdict("doc-accuracy", output, rc) == "UNKNOWN"
