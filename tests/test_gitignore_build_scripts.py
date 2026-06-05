"""Regression tests for issue #2383.

`.gitignore` must permit new generator sources under `build/` and
`build/scripts/` to be tracked without `git add -f`, while still ignoring
real build outputs under `build/` (e.g. `build/lib/`, `build/dist/`).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
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
        "build/lib/foo.txt",
        "build/dist/wheel.whl",
        "build/temp.linux/obj.o",
    ):
        assert _check_ignore(REPO_ROOT, output), (
            f"{output} should remain gitignored — it's a real build output."
        )


def test_dist_root_remains_ignored():
    """/dist/ must remain ignored."""
    assert _check_ignore(REPO_ROOT, "dist/anything.whl")
