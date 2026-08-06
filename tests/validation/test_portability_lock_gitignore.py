"""Regression tests for issue #4511.

All three portability-baseline advisory write-lock files under
scripts/validation/ must be gitignored. The lock names are derived
generically by portability_baseline.py, so any new caller would
reintroduce the bug if the anchored rules are missing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _check_ignore(repo: Path, relpath: str) -> bool:
    """Return True iff git considers `relpath` ignored inside `repo`."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=repo,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError(
        f"git check-ignore failed (exit {result.returncode}) on {relpath}"
    )


class TestPortabilityLockFilesIgnored:
    """All three canonical lock paths under scripts/validation/ are ignored."""

    def test_skill_md_portability_lock_ignored(self) -> None:
        assert _check_ignore(
            REPO_ROOT,
            "scripts/validation/.skill_md_portability_baseline.json.write-lock",
        )

    def test_skill_md_exec_portability_lock_ignored(self) -> None:
        assert _check_ignore(
            REPO_ROOT,
            "scripts/validation/.skill_md_exec_portability_baseline.json.write-lock",
        )

    def test_skill_portability_lock_ignored(self) -> None:
        assert _check_ignore(
            REPO_ROOT,
            "scripts/validation/.skill_portability_baseline.json.write-lock",
        )


class TestLockRulesAreAnchored:
    """The same basename outside scripts/validation/ must NOT be ignored.

    Proves the rules are anchored and do not blanket-hide same-named files
    elsewhere in the tree (issue #4511 acceptance criterion).
    """

    def test_lock_outside_scripts_validation_not_ignored(self) -> None:
        assert not _check_ignore(
            REPO_ROOT,
            "docs/.skill_portability_baseline.json.write-lock",
        )

    def test_md_lock_outside_scripts_validation_not_ignored(self) -> None:
        assert not _check_ignore(
            REPO_ROOT,
            "docs/.skill_md_portability_baseline.json.write-lock",
        )

    def test_exec_lock_outside_scripts_validation_not_ignored(self) -> None:
        assert not _check_ignore(
            REPO_ROOT,
            "docs/.skill_md_exec_portability_baseline.json.write-lock",
        )
