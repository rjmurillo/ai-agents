#!/usr/bin/env python3
"""Tests for the --diff-scope flag in scan_principles."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from scripts.ai_review_common.verdict import adapt_local_axis_verdict

core = import_skill_script(
    ".claude/skills/golden-principles/scripts/scan_principles_core.py",
    module_name="scan_principles_core",
)
mod = import_skill_script(".claude/skills/golden-principles/scripts/scan_principles.py")
get_diff_files = mod.get_diff_files
main = mod.main
EXIT_SUCCESS = mod.EXIT_SUCCESS
EXIT_ERROR = mod.EXIT_ERROR
EXIT_VIOLATIONS = mod.EXIT_VIOLATIONS


def _run_git(repo: Path, *args: str) -> None:
    """Run a git command in the given repo, failing loudly on error."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )


def _make_repo_with_diff(repo: Path, *, adopts_principles: bool = True) -> None:
    """Create a git repo on a feature branch with one file changed vs main.

    By default main carries the golden-principles governance document, so
    GP-001 is enforced. Pass ``adopts_principles=False`` for a consumer
    repository that never adopted it (issue #7483).
    """
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    (repo / "base.py").write_text("x = 1\n")
    _run_git(repo, "add", "base.py")
    if adopts_principles:
        doc = repo / core.GOVERNANCE_DOC
        doc.parent.mkdir(parents=True)
        doc.write_text("# Golden principles\n")
        _run_git(repo, "add", core.GOVERNANCE_DOC)
    _run_git(repo, "commit", "-m", "base")
    _run_git(repo, "checkout", "-b", "feature")
    (repo / "changed.py").write_text("y = 2\n")
    _run_git(repo, "add", "changed.py")
    _run_git(repo, "commit", "-m", "change")


class TestGetDiffFiles:
    """Tests for diff-scoped file selection (--diff-scope)."""

    def test_returns_only_changed_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        # Paths are anchored to the git root so they resolve from any cwd.
        assert len(result) == 1
        assert os.path.isabs(result[0])
        assert result[0].endswith("/changed.py")
        assert os.path.isfile(result[0])

    def test_returns_empty_when_no_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        _run_git(tmp_path, "checkout", "main")
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        assert result == []

    def test_raises_when_git_missing(self) -> None:
        with patch.object(core.subprocess, "run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError):
                get_diff_files("main")

    def test_raises_on_unknown_base(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # An unknown base makes git exit non-zero. That is a failure, not an
        # empty diff: returning [] would let a standards pre-flight pass without
        # scanning. The function must surface the failure.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError):
            get_diff_files("does-not-exist")

    def test_rejects_dash_base(self) -> None:
        # CWE-88: a base starting with "-" would be parsed by git as an option.
        with pytest.raises(ValueError):
            get_diff_files("--output=/tmp/pwn")

    def test_rejects_empty_base(self) -> None:
        with pytest.raises(ValueError):
            get_diff_files("")

    def test_drops_traversal_paths(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="changed.py\n../escape.py\nfoo/../bar.py\n",
        )
        with (
            patch.object(core, "_git_root", return_value="/repo"),
            patch.object(core.subprocess, "run", return_value=completed),
        ):
            result = get_diff_files("main")
        assert result == ["/repo/changed.py"]


class TestMainDiffScope:
    """Tests for the --diff-scope main entry path."""

    def test_diff_scope_scans_only_changed_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        # A pre-existing shell script on the base would trip GP-001 on a
        # whole-tree scan, but it is not in the diff so --diff-scope ignores it.
        (tmp_path / "legacy.sh").write_text("echo hi\n")
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "legacy.sh")
        _run_git(tmp_path, "commit", "-m", "legacy shell on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_SUCCESS

    def test_diff_scope_flags_violation_in_changed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        # Add a new shell script in the diff: GP-001 (script-language) is an error.
        (tmp_path / "added.sh").write_text("echo added\n")
        _run_git(tmp_path, "add", "added.sh")
        _run_git(tmp_path, "commit", "-m", "add shell script")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS

    def test_diff_scope_unknown_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A git failure must surface as EXIT_ERROR, never a false EXIT_SUCCESS.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "does-not-exist"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_dash_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope=--bad"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_empty_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An empty base (e.g. ship/review passing "$BASE_BRANCH" while unset) must
        # error, not silently fall through to a full-repository scan.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", ""]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_catches_violation_from_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Diff paths are repo-root-relative; anchoring them to the git root means
        # the scan still finds them when cwd is a subdirectory. Without the
        # anchor the file would be skipped and the gate would pass falsely.
        _make_repo_with_diff(tmp_path)
        (tmp_path / "added.sh").write_text("echo added\n")
        _run_git(tmp_path, "add", "added.sh")
        _run_git(tmp_path, "commit", "-m", "add shell script")
        subdir = tmp_path / "nested"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS


def _scan_new_shell_script(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, object]]:
    """Commit one new .sh on the feature branch and run the /review invocation."""
    (repo / "verify-package-contents.sh").write_text("echo verify\n")
    _run_git(repo, "add", "verify-package-contents.sh")
    _run_git(repo, "commit", "-m", "add shell helper")
    monkeypatch.chdir(repo)
    capsys.readouterr()
    argv = ["scan_principles.py", "--diff-scope", "main", "--format", "json"]
    with patch("sys.argv", argv):
        rc = main()
    return rc, json.loads(capsys.readouterr().out)


class TestRepositoryPolicyOptIn:
    """GP-001 binds only a repository that carries the governance document (#7483)."""

    def test_non_adopting_repo_reports_gp001_as_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_repo_with_diff(tmp_path, adopts_principles=False)

        rc, payload = _scan_new_shell_script(tmp_path, monkeypatch, capsys)

        assert rc == EXIT_SUCCESS
        assert payload["principles_adopted"] is False
        assert payload["error_count"] == 0
        assert payload["warning_count"] == 1
        violation = payload["violations"][0]
        assert violation["principle"] == "GP-001"
        assert violation["severity"] == "warning"
        assert "Advisory only" in violation["remediation"]
        assert "ADR-042" not in violation["remediation"]

    def test_non_adopting_repo_does_not_fail_review_axis(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_repo_with_diff(tmp_path, adopts_principles=False)

        rc, payload = _scan_new_shell_script(tmp_path, monkeypatch, capsys)

        verdict = adapt_local_axis_verdict("golden-principles", json.dumps(payload), rc)
        assert verdict == "WARN"

    def test_adopting_repo_still_fails_review_axis(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_repo_with_diff(tmp_path, adopts_principles=True)

        rc, payload = _scan_new_shell_script(tmp_path, monkeypatch, capsys)

        assert rc == EXIT_VIOLATIONS
        assert payload["principles_adopted"] is True
        assert payload["error_count"] == 1
        assert payload["violations"][0]["severity"] == "error"
        verdict = adapt_local_axis_verdict("golden-principles", json.dumps(payload), rc)
        assert verdict == "FAIL"

    def test_opt_in_is_read_from_git_root_not_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Running from a subdirectory must still find the root's document.
        _make_repo_with_diff(tmp_path, adopts_principles=True)
        (tmp_path / "added.sh").write_text("echo added\n")
        _run_git(tmp_path, "add", "added.sh")
        _run_git(tmp_path, "commit", "-m", "add shell script")
        subdir = tmp_path / "nested"
        subdir.mkdir()
        monkeypatch.chdir(subdir)

        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            rc = main()

        assert rc == EXIT_VIOLATIONS

    def test_directory_scan_reads_opt_in_from_scanned_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # cwd sits outside any repository; the scanned directory's repo adopts.
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_with_diff(repo, adopts_principles=True)
        (repo / "tool.sh").write_text("echo hi\n")
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)

        with patch("sys.argv", ["scan_principles.py", "--directory", str(repo)]):
            rc = main()

        assert rc == EXIT_VIOLATIONS

    def test_directory_scan_without_repo_is_advisory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No repository root means no governance document: advisory, exit 0.
        (tmp_path / "tool.sh").write_text("echo hi\n")
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["scan_principles.py", "--directory", str(tmp_path)]):
            rc = main()

        assert rc == EXIT_SUCCESS
