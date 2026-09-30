"""Tests for the branch-wide em/en-dash prohibition check.

Split out of ``test_markdown_checks.py`` when the added scope-visibility
coverage pushed that file past the 500 line ceiling. The dash check and the
markdown-lint check are independent validators, so they split cleanly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.evidence import pre_pr_policy


@pytest.fixture(autouse=True)
def _local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test as a local checkout unless it opts into CI.

    GitHub Actions sets ``CI`` and ``GITHUB_ACTIONS`` for the pytest run itself,
    and the scan reads them, so an unpinned test would change verdict by host.
    """
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


class TestValidateDashProhibition:
    """Tests for the branch-wide em/en-dash check."""

    def test_returns_true_when_no_base_ref_resolves(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        # tmp_path is not a git repo; no ref will resolve. Locally the scan warns
        # and passes so a shallow or detached checkout does not stop a push.
        assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_returns_true_for_clean_branch(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "README.md\n", ""),  # git diff
                (0, "clean content\n", ""),  # git show
            ]
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_returns_false_on_em_dash(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        # _find_dash_violations now reads HEAD content via `git show`
        # rather than the working tree. Mock the two subprocess calls
        # in order: (1) git diff returns the file list, (2) git show
        # returns the file content as if from HEAD.
        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "doc.md\n", ""),  # git diff
                (0, f"prose with {chr(0x2014)} em-dash\n", ""),  # git show
            ]
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_returns_false_on_en_dash(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "range.md\n", ""),
                (0, f"range 1{chr(0x2013)}10\n", ""),
            ]
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_skips_vendored_paths(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        vendored = tmp_path / "node_modules" / "pkg" / "README.md"
        vendored.parent.mkdir(parents=True)
        vendored.write_text(f"upstream prose with {chr(0x2014)} dash\n", encoding="utf-8")
        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "node_modules/pkg/README.md\n", "")
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_skips_test_fixtures_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        fixture = tmp_path / "tests" / "hooks" / "fixtures" / "dash_violations.md"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(f"intentional {chr(0x2014)}\n", encoding="utf-8")
        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "tests/hooks/fixtures/dash_violations.md\n", "")
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_skips_worktree_scratch_paths(self, tmp_path: Path) -> None:
        """issue #4892: sibling-session scratch trees must not enter the scan."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        for prefix in ("worktrees", ".agent-scratch", ".scratch"):
            scratch = tmp_path / prefix / "sub" / "notes.md"
            scratch.parent.mkdir(parents=True)
            scratch.write_text(f"scratch prose with {chr(0x2014)} dash\n", encoding="utf-8")
        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (
                0,
                "worktrees/sub/notes.md\n.agent-scratch/sub/notes.md\n.scratch/sub/notes.md\n",
                "",
            )
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))
        mock_run.assert_called_once()

    def test_includes_github_instructions_tree(self, tmp_path: Path) -> None:
        """REQ-006-AC4: .github/instructions/ is NOT excluded."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, ".github/instructions/universal.instructions.md\n", ""),
                (0, f"prose {chr(0x2014)} dash\n", ""),
            ]
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_returns_true_when_git_diff_fails(self, tmp_path: Path) -> None:
        """Locally, a failed git diff warns and passes (no CI variable set)."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (128, "", "fatal: bad revision")
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_reads_head_content_not_working_tree(self, tmp_path: Path) -> None:
        """`_find_dash_violations` reads HEAD via `git show`, not the working tree.

        Working-tree edit could differ from committed content. The branch-wide
        scan must reflect what is committed (HEAD), since the diff scope
        comes from `git diff base...HEAD`.
        """
        from scripts.validation.pre_pr import validate_dash_prohibition

        # Working tree clean, but HEAD content (mocked) has em-dash:
        # the function MUST flag it.
        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "doc.md\n", ""),
                # HEAD content has dash; working tree (clean) does not.
                (0, f"committed em-dash {chr(0x2014)} here\n", ""),
            ]
            # No file at tmp_path/doc.md (working tree). Function should
            # still detect the violation because it reads HEAD content.
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_unreadable_head_blob_is_reported_not_silent(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A `git show` failure on a candidate path must be visible.

        Regression for the fail-open inventory row
        `.agents/governance/FAIL-OPEN-INVENTORY.md` (`checks_dash.py:107-127`,
        `_find_dash_violations`): the file used to be dropped from the scan
        with no print at all, so a blocking gate silently narrowed its own
        scope. This is the input the unfixed implementation gets wrong: it
        returns the same `True` with the same stdout as a genuinely clean
        scan, so a reader (or an assertion) cannot tell "nothing found" from
        "one file was never examined".
        """
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "unreadable.md\n", ""),  # git diff
                (128, "", "fatal: path unknown revision"),  # git show fails
            ]
            result = validate_dash_prohibition(tmp_path)

        out = capsys.readouterr().out
        assert pre_pr_policy().accepts(result), "a single unreadable file still fails open"
        assert "[WARNING]" in out
        assert "unreadable.md" in out
        assert "skipped" in out
        # The unfixed implementation prints the ordinary all-clean PASS line
        # with no scope caveat; the fix MUST NOT claim the full candidate set
        # was checked when one of the two files was never read.
        assert "1 of 1 markdown file(s) checked" not in out

    def test_unreadable_file_does_not_hide_a_real_violation_elsewhere(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A skipped file must not mask a violation found in a sibling file."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "unreadable.md\nviolation.md\n", ""),  # git diff
                (128, "", "fatal: path unknown revision"),  # unreadable.md
                (0, f"prose with {chr(0x2014)} dash\n", ""),  # violation.md
            ]
            result = validate_dash_prohibition(tmp_path)

        out = capsys.readouterr().out
        assert not pre_pr_policy().accepts(result)
        assert "violation.md:1" in out
        assert "[WARNING]" in out
        assert "unreadable.md" in out

    def test_narrowed_scope_reports_examined_count_alongside_skip_count(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The PASS summary distinguishes examined files from skipped ones.

        `.claude/rules/ci-scripts.md` MUST 12: a scope measurement must be
        reported together with the size of the scope, not a bare "checked N
        files" that folds the skipped files into the same count as the
        examined ones.
        """
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "clean.md\nunreadable.md\n", ""),  # git diff
                (0, "no dashes here\n", ""),  # clean.md
                (128, "", "fatal: bad object"),  # unreadable.md
            ]
            result = validate_dash_prohibition(tmp_path)

        out = capsys.readouterr().out
        assert pre_pr_policy().accepts(result)
        assert "1 of 2 markdown file(s) checked" in out
        assert "1 unreadable at HEAD, skipped" in out

    def test_fully_readable_scan_reports_no_skip_caveat(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Negative control: an all-readable scan prints the plain PASS line."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with (
            patch("checks_dash._resolve_branch_base_ref") as mock_ref,
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "clean.md\n", ""),  # git diff
                (0, "no dashes here\n", ""),  # clean.md
            ]
            result = validate_dash_prohibition(tmp_path)

        out = capsys.readouterr().out
        assert pre_pr_policy().accepts(result)
        assert "1 markdown file(s) checked" in out
        assert "skipped" not in out
        assert "[WARNING]" not in out


class TestScanUnavailableUnderCi:
    """Issue #5636, D10: an unresolved base ref is BLOCKED under CI, a warning locally."""

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("CI", "true"),
            ("CI", "1"),
            ("CI", "TRUE"),
            ("GITHUB_ACTIONS", "true"),
            ("GITHUB_ACTIONS", " 1 "),
        ],
    )
    def test_unresolved_base_ref_fails_closed_under_ci(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
        value: str,
    ) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        monkeypatch.setenv(name, value)
        with patch("checks_dash._resolve_branch_base_ref", return_value=None):
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))
        out = capsys.readouterr().out
        assert "[BLOCKED] Em/en-dash branch scan: no base ref resolved" in out
        assert "no file was examined" in out

    def test_unresolved_base_ref_only_warns_locally(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("checks_dash._resolve_branch_base_ref", return_value=None):
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))
        out = capsys.readouterr().out
        assert "[WARNING] Em/en-dash branch scan skipped: no base ref resolved" in out
        assert "[BLOCKED]" not in out

    @pytest.mark.parametrize("value", ["", "0", "false", "no"])
    def test_falsy_ci_values_stay_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        monkeypatch.setenv("CI", value)
        with patch("checks_dash._resolve_branch_base_ref", return_value=None):
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_failed_git_diff_fails_closed_under_ci(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        monkeypatch.setenv("CI", "true")
        with (
            patch("checks_dash._resolve_branch_base_ref", return_value="origin/main"),
            patch("checks_dash._run_subprocess", return_value=(128, "", "fatal: bad revision")),
        ):
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))
        assert "[BLOCKED] Em/en-dash branch scan: git diff failed" in capsys.readouterr().out

    def test_resolved_base_ref_is_unaffected_by_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: CI must not block a scan that ran and found nothing."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        monkeypatch.setenv("CI", "true")
        with (
            patch("checks_dash._resolve_branch_base_ref", return_value="origin/main"),
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_run.side_effect = [(0, "README.md\n", ""), (0, "clean\n", "")]
            assert pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))

    def test_violation_still_fails_under_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        monkeypatch.setenv("CI", "true")
        with (
            patch("checks_dash._resolve_branch_base_ref", return_value="origin/main"),
            patch("checks_dash._run_subprocess") as mock_run,
        ):
            mock_run.side_effect = [(0, "doc.md\n", ""), (0, f"a {chr(0x2014)} b\n", "")]
            assert not pre_pr_policy().accepts(validate_dash_prohibition(tmp_path))
