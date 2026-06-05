#!/usr/bin/env python3
"""Tests for verify_no_conflict_markers.py.

Covers:
- Issue #2424: intentional fenced ``<<<<<<<`` examples committed in
  unrelated docs MUST NOT trigger a false positive.
- Real leftover markers in unstaged, staged, or both must be flagged.
- Files in unmerged (UU) state must be flagged.
- Non-git directories return the documented usage-error exit code.
- JSON output is parseable and round-trips.

These tests use real ``git`` invocations against ephemeral repos in
``tmp_path`` because the script's value is in the exact ``git diff
HEAD --check`` + ``git diff --diff-filter=U`` semantics. Mocking git
would hide whether we got the primitives right.

Exit codes follow ADR-035:

    0 - All tests passed
    1 - One or more tests failed
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

from claude_skills_import import import_skill_script  # noqa: E402

mod = import_skill_script(".claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py")
verify = mod.verify
main = mod.main
list_unmerged_files = mod.list_unmerged_files
find_leftover_markers = mod.find_leftover_markers


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git in ``cwd`` -- tests need real git, not a mock."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture()
def empty_repo(tmp_path: Path) -> Path:
    """An initialized git repo with no commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


@pytest.fixture()
def repo_with_intentional_fenced_marker(empty_repo: Path) -> Path:
    """Repo where committed docs intentionally fence ``<<<<<<<`` markers.

    This is the exact false-positive scenario from issue #2424:
    documentation and Serena memories that contain example conflict
    markers inside fenced code blocks. The verifier must report clean.
    """
    docs = empty_repo / "docs" / "conflict-example.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text(
        "# Conflict marker example\n\n```text\n<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> main\n```\n"
    )
    _git(empty_repo, "add", "docs/conflict-example.md")
    _git(empty_repo, "commit", "-q", "-m", "docs: intentional fenced example")
    return empty_repo


# ---------------------------------------------------------------------------
# Issue #2424 false-positive regression
# ---------------------------------------------------------------------------


class TestIntentionalFencedExamplesIgnored:
    """Issue #2424: committed fenced examples must not false-fail.

    The legacy ``git grep -n '<<<<<<<' --`` approach found these and
    incorrectly reported the merge as dirty. The new helper checks
    in-flight changes only, so committed examples are invisible.
    """

    def test_clean_repo_with_committed_fenced_markers_returns_ok(
        self,
        repo_with_intentional_fenced_marker: Path,
    ) -> None:
        exit_code, report = verify(repo_with_intentional_fenced_marker)
        assert exit_code == 0
        assert report["ok"] is True
        assert report["unmerged_files"] == []
        assert report["leftover_markers"] == []

    def test_clean_repo_after_innocent_edit_still_returns_ok(
        self,
        repo_with_intentional_fenced_marker: Path,
    ) -> None:
        """An ordinary edit to an unrelated file must not flip the verdict."""
        unrelated = repo_with_intentional_fenced_marker / "README.md"
        unrelated.write_text("Hello, world.\n")
        _git(repo_with_intentional_fenced_marker, "add", "README.md")
        _git(
            repo_with_intentional_fenced_marker,
            "commit",
            "-q",
            "-m",
            "add README",
        )

        exit_code, report = verify(repo_with_intentional_fenced_marker)
        assert exit_code == 0
        assert report["ok"] is True


# ---------------------------------------------------------------------------
# Real conflicts still fail
# ---------------------------------------------------------------------------


class TestRealConflictsFlagged:
    def test_unstaged_leftover_markers_are_flagged(
        self,
        repo_with_intentional_fenced_marker: Path,
    ) -> None:
        """Markers in working tree (post-merge, not yet ``git add``) fail.

        Simulates the realistic case where a merge wrote conflict
        markers into a previously-tracked file. The user is partway
        through resolution -- the file is modified but not yet
        ``git add``-ed.
        """
        # Commit a clean version first so the file is tracked.
        app = repo_with_intentional_fenced_marker / "app.py"
        app.write_text("def foo():\n    return 1\n")
        _git(repo_with_intentional_fenced_marker, "add", "app.py")
        _git(repo_with_intentional_fenced_marker, "commit", "-q", "-m", "seed app.py")

        # Now overwrite with conflict markers (simulating a botched merge
        # the user hasn't finished resolving). Do not stage.
        app.write_text(
            "def foo():\n<<<<<<< HEAD\n    return 1\n=======\n    return 2\n>>>>>>> feature\n"
        )

        exit_code, report = verify(repo_with_intentional_fenced_marker)
        assert exit_code == 1
        assert report["ok"] is False
        assert any("app.py" in m for m in report["leftover_markers"])

    def test_staged_leftover_markers_are_flagged(
        self,
        repo_with_intentional_fenced_marker: Path,
    ) -> None:
        """Markers staged but not committed still fail.

        Covers the case where ``git add`` was run on a file that still
        contains conflict markers (an easy mistake during resolution).
        """
        app = repo_with_intentional_fenced_marker / "app.py"
        app.write_text("def foo():\n    return 1\n")
        _git(repo_with_intentional_fenced_marker, "add", "app.py")
        _git(repo_with_intentional_fenced_marker, "commit", "-q", "-m", "seed app.py")

        app.write_text(
            "def foo():\n<<<<<<< HEAD\n    return 1\n=======\n    return 2\n>>>>>>> feature\n"
        )
        _git(repo_with_intentional_fenced_marker, "add", "app.py")

        exit_code, report = verify(repo_with_intentional_fenced_marker)
        assert exit_code == 1
        assert any("app.py" in m for m in report["leftover_markers"])

    def test_unmerged_uu_file_is_flagged(self, empty_repo: Path) -> None:
        """A file left in unmerged (UU) state is reported separately."""
        # Build base
        app = empty_repo / "app.py"
        app.write_text("def foo():\n    return 1\n")
        _git(empty_repo, "add", "app.py")
        _git(empty_repo, "commit", "-q", "-m", "base")

        # Feature branch with a competing change
        _git(empty_repo, "checkout", "-q", "-b", "feature")
        app.write_text("def foo():\n    return 99\n")
        _git(empty_repo, "commit", "-q", "-am", "feature")

        # Main branch diverges
        _git(empty_repo, "checkout", "-q", "main")
        app.write_text("def foo():\n    return 42\n")
        _git(empty_repo, "commit", "-q", "-am", "main change")

        # Trigger a real conflict and leave it unresolved
        merge = _git(empty_repo, "merge", "--no-commit", "feature", check=False)
        assert merge.returncode != 0, "expected merge conflict"

        unmerged = list_unmerged_files(empty_repo)
        assert "app.py" in unmerged

        exit_code, report = verify(empty_repo)
        assert exit_code == 1
        assert "app.py" in report["unmerged_files"]

    def test_fully_resolved_conflict_returns_ok(self, empty_repo: Path) -> None:
        """After resolving and staging, the verifier must return clean.

        This test specifically covers acceptance criterion #1 of issue
        #2424: real conflicts that have actually been resolved should
        not be incorrectly flagged as dirty -- which is what the legacy
        ``git grep`` approach did when intentional fenced docs existed.
        """
        # Base commit
        app = empty_repo / "app.py"
        app.write_text("def foo():\n    return 1\n")
        _git(empty_repo, "add", "app.py")
        _git(empty_repo, "commit", "-q", "-m", "base")

        # Commit a doc with an intentional fenced marker BEFORE branching.
        # This mirrors the real-repo conditions in the ai-agents codebase.
        docs = empty_repo / "docs.md"
        docs.write_text("Example:\n\n```text\n<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> main\n```\n")
        _git(empty_repo, "add", "docs.md")
        _git(empty_repo, "commit", "-q", "-m", "docs: example")

        # Diverge
        _git(empty_repo, "checkout", "-q", "-b", "feature")
        app.write_text("def foo():\n    return 99\n")
        _git(empty_repo, "commit", "-q", "-am", "feature")
        _git(empty_repo, "checkout", "-q", "main")
        app.write_text("def foo():\n    return 42\n")
        _git(empty_repo, "commit", "-q", "-am", "main change")

        # Trigger and resolve
        _git(empty_repo, "merge", "--no-commit", "feature", check=False)
        app.write_text("def foo():\n    return 42  # took main\n")
        _git(empty_repo, "add", "app.py")

        # Verifier must report clean even though committed docs.md
        # contains intentional fenced ``<<<<<<<`` markers.
        exit_code, report = verify(empty_repo)
        assert exit_code == 0, (
            f"expected clean verdict; got report={report!r}. "
            "Issue #2424 regressed -- intentional fenced docs are "
            "causing a false positive again."
        )
        assert report["ok"] is True


# ---------------------------------------------------------------------------
# Setup / usage error handling
# ---------------------------------------------------------------------------


class TestSetupAndUsageErrors:
    def test_non_git_directory_returns_exit_2(self, tmp_path: Path) -> None:
        not_a_repo = tmp_path / "not-a-repo"
        not_a_repo.mkdir()
        exit_code, report = verify(not_a_repo)
        assert exit_code == 2
        assert report["ok"] is False
        assert report["error"] == "not_in_git_repo"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestCliEntryPoint:
    def test_main_returns_zero_for_clean_repo(
        self,
        repo_with_intentional_fenced_marker: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = main(["--cwd", str(repo_with_intentional_fenced_marker), "--json"])
        captured = capsys.readouterr()
        assert exit_code == 0
        parsed = json.loads(captured.out)
        assert parsed["ok"] is True

    def test_main_returns_one_for_leftover_markers(
        self,
        repo_with_intentional_fenced_marker: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Seed a tracked file, then overwrite with conflict markers.
        bad = repo_with_intentional_fenced_marker / "app.py"
        bad.write_text("seed\n")
        _git(repo_with_intentional_fenced_marker, "add", "app.py")
        _git(repo_with_intentional_fenced_marker, "commit", "-q", "-m", "seed")
        bad.write_text("a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> b\n")

        exit_code = main(["--cwd", str(repo_with_intentional_fenced_marker), "--json"])
        captured = capsys.readouterr()
        assert exit_code == 1
        parsed = json.loads(captured.out)
        assert parsed["ok"] is False
        assert any("app.py" in m for m in parsed["leftover_markers"])

    def test_main_returns_two_for_non_git_dir(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        not_a_repo = tmp_path / "x"
        not_a_repo.mkdir()
        exit_code = main(["--cwd", str(not_a_repo), "--json"])
        captured = capsys.readouterr()
        assert exit_code == 2
        parsed = json.loads(captured.out)
        assert parsed["error"] == "not_in_git_repo"

    def test_main_human_format_includes_marker_lines(
        self,
        repo_with_intentional_fenced_marker: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bad = repo_with_intentional_fenced_marker / "app.py"
        bad.write_text("seed\n")
        _git(repo_with_intentional_fenced_marker, "add", "app.py")
        _git(repo_with_intentional_fenced_marker, "commit", "-q", "-m", "seed")
        bad.write_text("a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> b\n")
        exit_code = main(["--cwd", str(repo_with_intentional_fenced_marker)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert "[fail]" in out
        assert "app.py" in out


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_list_unmerged_files_empty_for_clean_repo(
        self, repo_with_intentional_fenced_marker: Path
    ) -> None:
        assert list_unmerged_files(repo_with_intentional_fenced_marker) == []

    def test_find_leftover_markers_empty_for_clean_repo(
        self, repo_with_intentional_fenced_marker: Path
    ) -> None:
        # The committed fenced example must be invisible to the verifier.
        assert find_leftover_markers(repo_with_intentional_fenced_marker) == []
