"""Vendor portability, review marker, and CI-pin tests for scripts.validation.pre_pr.

Split from tests/test_validation_pre_pr.py (issue #4352). Covers:
- validate_vendor_portability
- validate_review_marker
- validate_ci_dependency_pins skip logic
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import validate_review_marker, validate_vendor_portability


class TestValidateVendorPortability:
    """The vendor-portability gate wraps check_vendor_portability.py (#2050).

    Exit-code contract mirrored from the wrapped script:
    0 (no new offenders / no scan roots) -> pass, 1 (new offender) -> fail,
    2 (config error) -> fail. A missing wrapped script raises MissingScriptSkip.
    """

    def _make_repo(self, tmp_path: Path) -> Path:
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "check_vendor_portability.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        return tmp_path

    def test_passes_when_checker_exits_zero(self, tmp_path: Path) -> None:

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (0, "[PASS] No new vendor-portability offenders.\n", "")
            assert validate_vendor_portability(repo) is True

    def test_fails_on_new_offender_exit_one(self, tmp_path: Path) -> None:

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (1, "[FAIL] 1 new vendor-portability offender(s).\n", "")
            assert validate_vendor_portability(repo) is False

    def test_fails_on_config_error_exit_two(self, tmp_path: Path) -> None:

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (2, "", "[FAIL] repo root not found")
            assert validate_vendor_portability(repo) is False

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import (
            MissingScriptSkip,
        )

        with pytest.raises(MissingScriptSkip):
            validate_vendor_portability(tmp_path)

    def test_passes_repo_root_to_checker(self, tmp_path: Path) -> None:

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (0, "", "")
            validate_vendor_portability(repo)

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        repo_root_index = command.index("--repo-root")
        assert command[repo_root_index + 1] == str(repo)


# ---------------------------------------------------------------------------
# validate_review_marker  (Issue #1938)
# ---------------------------------------------------------------------------


class TestValidateReviewMarker:
    """Tests for the SHA-bound /review marker advisory check.

    Behavior contract:

    - Script missing, ``REVIEW_MARKER_ENFORCED`` unset / 0: returns ``True``
      (advisory skip; never blocks pre-PR).
    - Script missing, ``REVIEW_MARKER_ENFORCED=1``: returns ``False``.
    - Script present, HEAD has a binding marker: returns ``True`` regardless
      of enforcement.
    - Script present, HEAD has no marker, advisory: returns ``True``.
    - Script present, HEAD has no marker, enforced: returns ``False``.
    """

    import subprocess as _subprocess

    @staticmethod
    def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
        result = TestValidateReviewMarker._subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            input=stdin,
            check=True,
        )
        return result.stdout.strip()

    def _make_repo(self, tmp_path: Path, with_script: bool) -> Path:
        """Build a fake repo: real validator script (optionally) + git history."""
        repo = tmp_path / "repo"
        repo.mkdir()
        if with_script:
            dest = repo / "scripts" / "validation"
            dest.mkdir(parents=True)
            real = (
                Path(__file__).resolve().parent.parent
                / "scripts"
                / "validation"
                / "validate_review_marker.py"
            )
            (dest / "validate_review_marker.py").write_text(
                real.read_text(encoding="utf-8"), encoding="utf-8"
            )
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Tester")
        self._git(repo, "config", "commit.gpgsign", "false")
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "feat: one")
        (repo / "b.txt").write_text("y\n", encoding="utf-8")
        self._git(repo, "add", "b.txt")
        self._git(repo, "commit", "-q", "-m", "feat: two")
        return repo

    def _add_marker(self, repo: Path) -> None:
        """Add an empty /review marker commit binding the current tip."""
        tip = self._git(repo, "rev-parse", "HEAD")
        self._git(
            repo,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "review: marker",
            "--trailer",
            f"Reviewed-By: /review@analyst,security on {tip}",
        )

    def test_missing_script_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_missing_script_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_no_marker_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_no_marker_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_valid_marker_passes_advisory(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_valid_marker_passes_enforced(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is True


class TestValidateCiDependencyPinsSkipsBeforeImporting:
    """The skip path must survive a tree that cannot import the checker.

    ``check_ci_dependency_pins`` imports ``packaging``. A downstream install
    with no ``.github/`` tree is also the install least likely to carry dev
    dependencies, so importing before the existence check would raise
    ImportError on exactly the tree the function is written to skip. Issue #3377.
    """

    @staticmethod
    def _block_import(monkeypatch: Any) -> None:  # noqa: ANN401

        # A None entry makes ``import check_ci_dependency_pins`` raise
        # ImportError, which is what a missing ``packaging`` looks like from
        # the caller's side.
        monkeypatch.setitem(sys.modules, "check_ci_dependency_pins", None)

    def test_an_absent_github_tree_skips_without_importing(
        self,
        tmp_path: Path,
        monkeypatch: Any,  # noqa: ANN401
    ) -> None:
        from checks_tooling import validate_ci_dependency_pins

        from scripts.validation.pre_pr import MissingScriptSkip

        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        self._block_import(monkeypatch)
        with pytest.raises(MissingScriptSkip):
            validate_ci_dependency_pins(tmp_path)

    def test_an_absent_pyproject_skips_without_importing(
        self,
        tmp_path: Path,
        monkeypatch: Any,  # noqa: ANN401
    ) -> None:
        from checks_tooling import validate_ci_dependency_pins

        from scripts.validation.pre_pr import MissingScriptSkip

        (tmp_path / ".github").mkdir()
        self._block_import(monkeypatch)
        with pytest.raises(MissingScriptSkip):
            validate_ci_dependency_pins(tmp_path)

    def test_a_present_tree_still_imports_and_runs(self, tmp_path: Path) -> None:
        """Negative control: a bad pin returns False, proving the checker ran."""
        from checks_tooling import validate_ci_dependency_pins

        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "w.yml").write_text(
            "run: pip install pytest==8.0.0\n", encoding="utf-8"
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname="x"\ndependencies=["pytest>=9.0.3"]\n', encoding="utf-8"
        )
        assert validate_ci_dependency_pins(tmp_path) is False


# ---------------------------------------------------------------------------
# Issue #3710: a markdown gate that selects nothing must not report success
# ---------------------------------------------------------------------------
