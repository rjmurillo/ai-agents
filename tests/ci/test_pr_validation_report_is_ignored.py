"""The PR validation report is generated into the repo root, so git must ignore it.

`scripts/ci/build_pr_validation_report.py` writes its output to a relative path.
On an ephemeral CI runner that is harmless. In a working tree it leaves untracked
litter at the repository root, where `git add -A` sweeps it into a commit.

These tests read the path from the writing script rather than from a literal, so
renaming the output cannot silently reopen the hole.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITER = REPO_ROOT / "scripts" / "ci" / "build_pr_validation_report.py"


def _report_path() -> Path:
    """Load the writer module and return the path it actually writes to."""
    spec = importlib.util.spec_from_file_location("_pr_report_writer", WRITER)
    if spec is None or spec.loader is None:
        pytest.fail(f"cannot load the report writer at {WRITER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Path(module.REPORT_PATH)


def _is_ignored(relative_path: str) -> bool:
    """Ask git whether a path is ignored, without needing the file to exist."""
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode not in (0, 1):
        pytest.fail(
            f"git check-ignore failed for {relative_path!r}: "
            f"rc={completed.returncode} stderr={completed.stderr.decode(errors='replace')}"
        )
    return completed.returncode == 0


class TestTheGeneratedReportStaysOutOfCommits:
    def test_the_writer_declares_a_relative_path_at_the_repo_root(self) -> None:
        """Edge: the risk only exists because the path is relative and unnested."""
        report = _report_path()
        assert not report.is_absolute()
        assert report.parent == Path("."), (
            "the report is no longer written to the repo root; "
            "this test guards a root-level litter path"
        )

    def test_the_path_the_writer_uses_is_ignored(self) -> None:
        """Positive: the exact path the script writes is ignored by git."""
        report = _report_path()
        assert _is_ignored(report.as_posix()), (
            f"{report.as_posix()} is generated into the working tree but git does "
            "not ignore it, so `git add -A` will commit it"
        )

    def test_a_tracked_file_is_not_reported_as_ignored(self) -> None:
        """Negative control: the probe distinguishes ignored from not ignored."""
        assert not _is_ignored("README.md"), (
            "the ignore probe reports a tracked file as ignored, so a passing "
            "result in the positive test would prove nothing"
        )

    def test_the_rule_is_anchored_to_the_repo_root(self) -> None:
        """Negative control: an unanchored rule would hide same-named files anywhere."""
        report = _report_path()
        nested = (Path("docs") / report.name).as_posix()
        assert not _is_ignored(nested), (
            f"{nested} is ignored, so the rule lost its leading slash and now "
            "hides every same-named file in the tree, not just the generated one"
        )
