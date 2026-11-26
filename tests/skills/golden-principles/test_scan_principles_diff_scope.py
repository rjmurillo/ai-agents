#!/usr/bin/env python3
"""Tests for the --diff-scope flag in scan_principles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.skills.diff_scope_repo import DiffFileSelectionContract, make_repo_with_diff, run_git

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


class TestGetDiffFiles(DiffFileSelectionContract):
    """Tests for diff-scoped file selection (--diff-scope)."""

    get_diff_files = staticmethod(get_diff_files)
    governance_doc = core.GOVERNANCE_DOC

    def test_raises_when_git_missing(self) -> None:
        with patch.object(core.subprocess, "run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError):
                get_diff_files("main")

    def test_raises_on_unknown_base(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # An unknown base makes git exit non-zero. That is a failure, not an
        # empty diff: returning [] would let a standards pre-flight pass without
        # scanning. The function must surface the failure.
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
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
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        # A pre-existing shell script on the base would trip GP-001 on a
        # whole-tree scan, but it is not in the diff so --diff-scope ignores it.
        (tmp_path / "legacy.sh").write_text("echo hi\n", encoding="utf-8")
        run_git(tmp_path, "checkout", "main")
        run_git(tmp_path, "add", "legacy.sh")
        run_git(tmp_path, "commit", "-m", "legacy shell on main")
        run_git(tmp_path, "checkout", "feature")
        run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_SUCCESS

    def test_diff_scope_flags_violation_in_changed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        # Add a new shell script in the diff: GP-001 (script-language) is an error.
        (tmp_path / "added.sh").write_text("echo added\n", encoding="utf-8")
        run_git(tmp_path, "add", "added.sh")
        run_git(tmp_path, "commit", "-m", "add shell script")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS

    def test_diff_scope_unknown_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A git failure must surface as EXIT_ERROR, never a false EXIT_SUCCESS.
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "does-not-exist"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_dash_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope=--bad"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_empty_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An empty base (e.g. ship/review passing "$BASE_BRANCH" while unset) must
        # error, not silently fall through to a full-repository scan.
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
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
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        (tmp_path / "added.sh").write_text("echo added\n", encoding="utf-8")
        run_git(tmp_path, "add", "added.sh")
        run_git(tmp_path, "commit", "-m", "add shell script")
        subdir = tmp_path / "nested"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        with patch("sys.argv", ["scan_principles.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS
