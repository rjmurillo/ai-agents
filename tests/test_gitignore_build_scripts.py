"""Regression tests for issue #2383.

`.gitignore` must permit new generator sources under `build/` and
`build/scripts/` to be tracked without `git add -f`, while still ignoring
real build outputs under `build/` (e.g. `build/lib/`, `build/dist/`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _check_ignore(repo: Path, relpath: str) -> bool:
    """Return True iff git considers `relpath` ignored inside `repo`."""
    # check-ignore exits 0 when the path IS ignored, 1 when NOT ignored.
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


def test_new_build_script_is_not_ignored():
    """A brand-new build/scripts/*.py must be trackable without `git add -f`."""
    new_path = "build/scripts/__regression_2383_new_module.py"
    assert not _check_ignore(REPO_ROOT, new_path), (
        f"{new_path} is gitignored; new generators silently won't be tracked. "
        "See issue #2383."
    )


def test_nested_build_script_is_not_ignored():
    """Nested subdirectories under build/scripts/ stay trackable."""
    nested = "build/scripts/sub/__regression_2383_module.py"
    assert not _check_ignore(REPO_ROOT, nested)


def test_top_level_build_python_files_are_not_ignored():
    """build/*.py (e.g. generate_agents.py) must be trackable."""
    assert not _check_ignore(REPO_ROOT, "build/generate_agents.py")
    assert not _check_ignore(REPO_ROOT, "build/__regression_2383_top.py")


def test_top_level_build_markdown_is_not_ignored():
    """build/AGENTS.md and other top-level .md files must be trackable."""
    assert not _check_ignore(REPO_ROOT, "build/AGENTS.md")


def test_build_output_directories_remain_ignored():
    """Real build outputs (build/lib/, build/dist/) must still be ignored."""
    for output in (
        "build/dist/wheel.whl",
        "build/build/temp.bin",
        "build/lib/foo.txt",
        "build/lib.linux-x86_64-cpython-314/foo.py",
        "build/temp/obj.o",
        "build/temp.linux/obj.o",
        "build/bdist.linux-x86_64/wheel.whl",
        "build/audit/report.json",
    ):
        assert _check_ignore(REPO_ROOT, output), (
            f"{output} should remain gitignored; it is a real build output."
        )


def test_dist_root_remains_ignored():
    """/dist/ must remain ignored."""
    assert _check_ignore(REPO_ROOT, "dist/anything.whl")


def test_model_sweep_artifact_directories_are_ignored():
    """Model sweep artifacts under evals/ must not stage by accident."""
    for artifact in (
        "evals/architect-spike/reports/sweep-claude-opus-4-6-50a27ed1/report.json",
        "evals/critic-spike/runs/sweep-claude-sonnet-4-6-563e53a2/result.json",
    ):
        assert _check_ignore(REPO_ROOT, artifact), (
            f"{artifact} should be gitignored; model sweep outputs are runtime "
            "evidence, not source of truth. See issue #3597."
        )


def test_non_sweep_eval_reports_remain_trackable():
    """Only sweep-* eval artifacts are ignored, not every eval report/run."""
    for tracked_candidate in (
        "evals/architect-spike/reports/manual-report/report.json",
        "evals/critic-spike/runs/manual-run/result.json",
    ):
        assert not _check_ignore(REPO_ROOT, tracked_candidate)
