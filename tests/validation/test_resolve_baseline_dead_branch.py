"""Tests for issue #4242 (dead branch, docstring, sentinel in resolve_baseline_path).

Verifies that the dead reject_outside_root=False branch is gone and that
resolve_baseline_path always enforces containment.

Tests for issue #4511 (untracked advisory lock file).

Verifies that .gitignore covers all three portability lock file names,
anchored to scripts/validation.
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

from scripts.validation import portability_common as common


class TestResolveBaselinePathNoBranching:
    """resolve_baseline_path always enforces containment (no opt-out branch)."""

    def test_rejects_absolute_path_outside_repo(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "other.json"
        outside.write_text("{}", encoding="utf-8")

        result = common.resolve_baseline_path(root, outside, "d.json")

        assert result is None

    def test_rejects_relative_path_that_escapes(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()

        result = common.resolve_baseline_path(root, Path("../escape.json"), "d.json")

        assert result is None

    def test_accepts_relative_path_inside_repo(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)

        result = common.resolve_baseline_path(
            root, Path("scripts/validation/b.json"), "d.json"
        )

        assert result == root / "scripts" / "validation" / "b.json"

    def test_default_when_baseline_is_none(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()

        result = common.resolve_baseline_path(root, None, "my_baseline.json")

        assert result == root / "scripts" / "validation" / "my_baseline.json"

    def test_function_signature_has_no_reject_outside_root_param(self) -> None:
        sig = inspect.signature(common.resolve_baseline_path)
        assert "reject_outside_root" not in sig.parameters, (
            "Dead branch parameter reject_outside_root must be removed"
        )

    def test_rejects_symlink_pointing_outside_repo(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = root / "scripts" / "validation" / "escape.json"
        link.symlink_to(outside)

        result = common.resolve_baseline_path(root, link, "d.json")

        assert result is None

    def test_returns_none_not_empty_path_on_escape(self, tmp_path: Path) -> None:
        """Sentinel must be None, not Path(''), so callers cannot mistake it."""
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "other.json"
        outside.write_text("{}", encoding="utf-8")

        result = common.resolve_baseline_path(root, outside, "d.json")

        assert result is None
        assert result != Path("")


class TestDocstringAccuracy:
    """Docstring must not claim check_vendor_portability delegates here."""

    def test_docstring_does_not_claim_all_checkers_delegate(self) -> None:
        doc = common.resolve_baseline_path.__doc__ or ""
        bad_phrases = [
            "Every checker",
            "rather than keeping a copy",
        ]
        for phrase in bad_phrases:
            assert phrase not in doc, (
                f"Docstring still contains stale claim: {phrase!r}. "
                "check_vendor_portability.py has its own resolver."
            )


class TestGitignoreLockFiles:
    """Advisory lock files for all three canonical baselines must be git-ignored."""

    LOCK_NAMES = [
        "scripts/validation/.skill_md_portability_baseline.json.write-lock",
        "scripts/validation/.skill_md_exec_portability_baseline.json.write-lock",
        "scripts/validation/.skill_portability_baseline.json.write-lock",
    ]
    REPO_ROOT = Path(__file__).resolve().parents[2]

    @pytest.mark.parametrize("lock_name", LOCK_NAMES)
    def test_lock_file_is_gitignored(self, lock_name: str, tmp_path: Path) -> None:
        """git check-ignore confirms each lock name is ignored."""
        result = subprocess.run(
            ["git", "check-ignore", "-q", lock_name],
            cwd=str(self.REPO_ROOT),
            capture_output=True,
        )
        assert result.returncode == 0, (
            f"{lock_name} is NOT covered by .gitignore. "
            "Advisory lock files must be ignored to keep git status clean (issue #4511)."
        )

    @pytest.mark.parametrize("other_name", [
        "scripts/validation/skill_md_portability_baseline.json",
        "docs/something.write-lock",
    ])
    def test_non_lock_files_are_not_gitignored(self, other_name: str) -> None:
        """The ignore rule must not swallow actual baseline files or unrelated paths."""
        result = subprocess.run(
            ["git", "check-ignore", "-q", other_name],
            cwd=str(self.REPO_ROOT),
            capture_output=True,
        )
        assert result.returncode != 0, (
            f"{other_name} is wrongly ignored by .gitignore"
        )
