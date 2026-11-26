#!/usr/bin/env python3
"""GP-001 binds only a repository that adopted the governance document (#7483).

Each test builds a throwaway git repository, with or without the document,
and runs the scanner the way /review does. The review adapter must record
WARN for a consumer repository and FAIL for an adopting one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from scripts.ai_review_common.verdict import adapt_local_axis_verdict
from tests.skills.diff_scope_repo import make_repo_with_diff, run_git

core = import_skill_script(
    ".claude/skills/golden-principles/scripts/scan_principles_core.py",
    module_name="scan_principles_core",
)
mod = import_skill_script(".claude/skills/golden-principles/scripts/scan_principles.py")
main = mod.main
EXIT_SUCCESS = mod.EXIT_SUCCESS
EXIT_VIOLATIONS = mod.EXIT_VIOLATIONS


def _scan_new_shell_script(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, Any]]:
    """Commit one new .sh on the feature branch and run the /review invocation."""
    (repo / "verify-package-contents.sh").write_text("echo verify\n", encoding="utf-8")
    run_git(repo, "add", "verify-package-contents.sh")
    run_git(repo, "commit", "-m", "add shell helper")
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
        make_repo_with_diff(tmp_path)

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
        make_repo_with_diff(tmp_path)

        rc, payload = _scan_new_shell_script(tmp_path, monkeypatch, capsys)

        verdict = adapt_local_axis_verdict("golden-principles", json.dumps(payload), rc)
        assert verdict == "WARN"

    def test_adopting_repo_still_fails_review_axis(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)

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
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        (tmp_path / "added.sh").write_text("echo added\n", encoding="utf-8")
        run_git(tmp_path, "add", "added.sh")
        run_git(tmp_path, "commit", "-m", "add shell script")
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
        make_repo_with_diff(repo, core.GOVERNANCE_DOC)
        (repo / "tool.sh").write_text("echo hi\n", encoding="utf-8")
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
        # Patch the root lookup so a governed checkout above tmp_path cannot leak in.
        (tmp_path / "tool.sh").write_text("echo hi\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        argv = ["scan_principles.py", "--directory", str(tmp_path)]

        with patch.object(mod, "_find_repo_root", return_value=None), patch("sys.argv", argv):
            rc = main()

        assert rc == EXIT_SUCCESS

    def test_branch_deleting_document_still_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The base adopted the rule; the branch cannot exempt itself by deleting it.
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        run_git(tmp_path, "rm", "-q", core.GOVERNANCE_DOC)
        run_git(tmp_path, "commit", "-m", "drop governance doc")

        rc, payload = _scan_new_shell_script(tmp_path, monkeypatch, capsys)

        assert rc == EXIT_VIOLATIONS
        assert payload["principles_adopted"] is True

    def test_branch_adding_document_enforces_on_itself(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_repo_with_diff(tmp_path)
        doc = tmp_path / core.GOVERNANCE_DOC
        doc.parent.mkdir(parents=True)
        doc.write_text("# Golden principles\n", encoding="utf-8")
        run_git(tmp_path, "add", core.GOVERNANCE_DOC)
        run_git(tmp_path, "commit", "-m", "adopt governance doc")

        rc, _ = _scan_new_shell_script(tmp_path, monkeypatch, capsys)

        assert rc == EXIT_VIOLATIONS

    def test_named_files_read_opt_in_from_their_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        make_repo_with_diff(repo, core.GOVERNANCE_DOC)
        script = repo / "tool.sh"
        script.write_text("echo hi\n", encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)

        with patch("sys.argv", ["scan_principles.py", str(script)]):
            rc = main()

        assert rc == EXIT_VIOLATIONS

    def test_base_adoption_is_false_for_unknown_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        monkeypatch.chdir(tmp_path)

        assert core.base_adopts_principles("main") is True
        assert core.base_adopts_principles("no-such-ref") is False

    @pytest.mark.parametrize(
        "error",
        [
            FileNotFoundError("git"),
            subprocess.TimeoutExpired(cmd="git", timeout=30),
            RuntimeError("git rev-parse failed"),
        ],
    )
    def test_base_adoption_is_false_when_git_fails(self, error: Exception) -> None:
        # A git failure reads as "not adopted at base". The caller still checks
        # HEAD, so this never relaxes an adopting working tree.
        with patch.object(core, "_git_root", return_value="/repo"):
            with patch("subprocess.run", side_effect=error):
                assert core.base_adopts_principles("main") is False

    def test_default_scan_reads_opt_in_from_cwd_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No arguments: scan the repository that holds cwd, and honor its document.
        make_repo_with_diff(tmp_path, core.GOVERNANCE_DOC)
        (tmp_path / "tool.sh").write_text("echo hi\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["scan_principles.py"]):
            rc = main()

        assert rc == EXIT_VIOLATIONS
