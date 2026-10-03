"""Pre-push review-marker gate passes the axis directory (issue #5113).

The canonical validator has no skill sibling, so the caller must pass
``--references-dir``. Without it every valid marker exits 2 and blocks the push.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy as policy

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "validation").mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py",
        root / "scripts" / "validation" / "validate_review_marker.py",
    )
    references = root / ".claude" / "skills" / "review" / "references"
    references.mkdir(parents=True)
    (references / "analyst.md").write_text("axis\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: code")
    return root


def _marker(repo: Path, axes: str) -> policy.PushUpdate:
    tip = _git(repo, "rev-parse", "HEAD")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "review: marker",
         "--trailer", f"Reviewed-By: /review@{axes} on {tip}")
    head = _git(repo, "rev-parse", "HEAD")
    source = policy.PushRef("refs/heads/a", head, "refs/heads/a", "0" * 40)
    return policy.PushUpdate(source, tip, head, f"{tip}..{head}", "a")


def test_valid_marker_passes_the_push_gate(repo: Path) -> None:
    assert policy._check_review_marker(_marker(repo, "analyst,correctness"), repo) == 0


def test_unknown_axis_blocks_the_push_gate(repo: Path) -> None:
    assert policy._check_review_marker(_marker(repo, "analyst,bogus"), repo) == 1


def test_gate_passes_the_references_dir_argument(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []
    real_command = policy._run_command

    def fake_command(
        args: list[str], repo_root: Path, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[0] == "git":
            return real_command(args, repo_root, **kwargs)
        captured.extend(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    update = _marker(repo, "analyst")
    monkeypatch.setattr(policy, "_run_command", fake_command)
    assert policy._check_review_marker(update, repo) == 0
    value = captured[captured.index("--references-dir") + 1]
    assert value == str(repo / ".claude" / "skills" / "review" / "references")
