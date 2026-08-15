"""Tests for issue #4915: investigation scope excludes merge-from-main files.

The bug: ``_changed_files(startingCommit, HEAD)`` used a two-dot tree diff
that included upstream files introduced by merging main into the branch.
The whole-tree ratchet demands a merge; the investigation scope gate then
rejected it.  Unsatisfiable.

The fix: when both base and head refs are provided (the CI path), use
``git log --first-parent --no-merges --name-status`` to collect only
files changed by the branch's own non-merge commits.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "session"
    / "scripts"
    / "test_investigation_eligibility.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("test_investigation_eligibility", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()



@pytest.fixture()
def merge_repo(tmp_path: Path) -> dict[str, str]:
    """Create a repo reproducing issue #4915.

    Layout:
        main: A (init) -- D (src/code.py)
               \\                          \\
        branch:  C (.agents/sessions/)  -- M (merge main)

    Returns dict with keys: repo_dir, start_sha, head_sha.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    # A: initial commit (session start point)
    (repo / "README.md").write_text("init\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "A: init"], repo)
    start_sha = _git(["rev-parse", "HEAD"], repo)

    # Branch: investigation-only change
    _git(["checkout", "-b", "investigation"], repo)
    (repo / ".agents").mkdir()
    (repo / ".agents" / "sessions").mkdir()
    (repo / ".agents" / "sessions" / "log.json").write_text("{}\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "C: investigation work"], repo)

    # Main: non-investigation change
    _git(["checkout", "main"], repo)
    (repo / "src_code.py").write_text("x = 1\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "D: main work (non-investigation)"], repo)

    # Merge main into branch
    _git(["checkout", "investigation"], repo)
    _git(["merge", "main", "--no-edit"], repo)
    head_sha = _git(["rev-parse", "HEAD"], repo)

    return {"repo_dir": str(repo), "start_sha": start_sha, "head_sha": head_sha}


class TestMergeFromMainExcluded:
    """Positive: merge from main does not pollute investigation scope."""

    def test_branch_only_files_returned(
        self, merge_repo: dict[str, str], monkeypatch: pytest.MonkeyPatch,
    ):
        """After merging main, _changed_files returns only branch work."""
        monkeypatch.chdir(merge_repo["repo_dir"])
        mod = _load_module()
        files, error = mod._changed_files(merge_repo["start_sha"], merge_repo["head_sha"])
        assert error is None
        assert ".agents/sessions/log.json" in files
        assert "src_code.py" not in files

    def test_main_via_subprocess(self, merge_repo: dict[str, str]):
        """End-to-end: the script reports Eligible after a merge from main."""
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT),
                "--base-ref",
                merge_repo["start_sha"],
                "--head-ref",
                merge_repo["head_sha"],
            ],
            cwd=merge_repo["repo_dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["Eligible"] is True
        assert payload["Violations"] == []


class TestNoMergeUnchanged:
    """Positive: normal (no-merge) behavior is preserved."""

    def test_linear_history_still_detected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """On a linear branch, non-investigation files are still flagged."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(["init", "-b", "main"], repo)
        _git(["config", "user.email", "t@example.com"], repo)
        _git(["config", "user.name", "T"], repo)
        (repo / "README.md").write_text("init\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "init"], repo)
        start = _git(["rev-parse", "HEAD"], repo)

        # Non-investigation file on the branch itself (no merge)
        (repo / "code.py").write_text("y = 2\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "add code"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        monkeypatch.chdir(str(repo))
        mod = _load_module()
        files, error = mod._changed_files(start, head)
        assert error is None
        assert "code.py" in files


class TestNegativePaths:
    """Negative: errors and edge cases fail closed."""

    def test_invalid_base_ref(self):
        """Invalid base ref produces ineligible output, not a crash."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--base-ref", "not-a-sha"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["Eligible"] is False
        assert "Invalid base ref" in payload.get("Error", "")

    def test_nonexistent_commit_fails_closed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A base ref that doesn't exist in the repo returns an error."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(["init", "-b", "main"], repo)
        _git(["config", "user.email", "t@example.com"], repo)
        _git(["config", "user.name", "T"], repo)
        (repo / "x").write_text("x\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "init"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        monkeypatch.chdir(str(repo))
        mod = _load_module()
        # Use a valid-format SHA that doesn't exist
        files, error = mod._changed_files("0" * 40, head)
        assert files is None
        assert error is not None


class TestEdgeCases:
    """Edge cases around the merge-base logic."""

    def test_multiple_merges_from_main(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Two consecutive merges from main still exclude upstream files."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(["init", "-b", "main"], repo)
        _git(["config", "user.email", "t@example.com"], repo)
        _git(["config", "user.name", "T"], repo)
        (repo / "README.md").write_text("init\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "init"], repo)
        start = _git(["rev-parse", "HEAD"], repo)

        # Branch: investigation change
        _git(["checkout", "-b", "branch"], repo)
        (repo / ".agents").mkdir()
        (repo / ".agents" / "sessions").mkdir()
        (repo / ".agents" / "sessions" / "s.json").write_text("{}\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "session work"], repo)

        # First merge from main
        _git(["checkout", "main"], repo)
        (repo / "a.py").write_text("a\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "main: a.py"], repo)
        _git(["checkout", "branch"], repo)
        _git(["merge", "main", "--no-edit"], repo)

        # Second merge from main
        _git(["checkout", "main"], repo)
        (repo / "b.py").write_text("b\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "main: b.py"], repo)
        _git(["checkout", "branch"], repo)
        _git(["merge", "main", "--no-edit"], repo)
        head = _git(["rev-parse", "HEAD"], repo)

        monkeypatch.chdir(str(repo))
        mod = _load_module()
        files, error = mod._changed_files(start, head)
        assert error is None
        assert ".agents/sessions/s.json" in files
        assert "a.py" not in files
        assert "b.py" not in files

    def test_no_head_ref_uses_diff_and_working_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """When head_ref is empty, the old diff+staged+untracked path runs."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(["init", "-b", "main"], repo)
        _git(["config", "user.email", "t@example.com"], repo)
        _git(["config", "user.name", "T"], repo)
        (repo / "README.md").write_text("init\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "init"], repo)
        start = _git(["rev-parse", "HEAD"], repo)

        # Stage a file (simulates the local/interactive path)
        (repo / "staged.txt").write_text("s\n")
        _git(["add", "staged.txt"], repo)

        monkeypatch.chdir(str(repo))
        mod = _load_module()
        files, error = mod._changed_files(start)
        assert error is None
        assert "staged.txt" in files
