"""Regression guards for repo-local pytest temp roots."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

# The sanctioned repo-local scratch directory: `.gitignore` covers it and
# `build/scripts/validate_plugin_manifests.py` prunes it when walking the
# checkout. A hyphenated near-miss of this name gets neither.
SANCTIONED_TEMP_ROOT = ".pytest_tmp"


def test_repo_local_tmpdir_and_basetemp_keep_git_isolation(project_root: Path) -> None:
    """Run representative tests with both pytest temp roots inside the checkout."""
    run_id = uuid.uuid4().hex
    tmpdir = project_root / ".pytest_cache" / "tmp" / "repo-local-guard" / run_id
    basetemp = project_root / ".pytest_cache" / "basetemp" / "repo-local-guard" / run_id
    tmpdir.mkdir(parents=True)
    basetemp.mkdir(parents=True)

    env = os.environ.copy()
    env.pop("GIT_CEILING_DIRECTORIES", None)
    env["TMPDIR"] = env["TEMP"] = env["TMP"] = str(tmpdir)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            f"--basetemp={basetemp}",
            "tests/build_scripts/test_build_all.py::test_ignored_paths_empty_when_not_a_git_repo",
            "tests/test_hook_utilities.py::TestGetProjectDirectory::test_returns_cwd_when_no_git_found",
        ],
        cwd=project_root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=900,
        check=False,
    )

    assert result.returncode == 0, (
        "repo-local pytest temp root guard failed\n"
        f"TMPDIR={tmpdir}\n"
        f"--basetemp={basetemp}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_no_test_writes_to_an_unrecognized_temp_root(project_root: Path) -> None:
    """A hyphenated near-miss of the scratch root gets no ignore and no prune.

    The variant differs by one character, is not covered by `.gitignore`, and
    is not in the prune list `validate_plugin_manifests.py` walks with. A
    directory created there survives the run and is visible to anything
    walking the checkout, so the spelling has to stay exact. This scan covers
    the Python trees where fixtures get written; it is a regression lock on
    the one spelling that bit us, not a general leak gate.
    """
    near_miss = SANCTIONED_TEMP_ROOT.replace("_", "-")
    offenders = [
        f"{path.relative_to(project_root)}:{number}"
        for tree in ("tests", "scripts", "build")
        for path in sorted((project_root / tree).rglob("*.py"))
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if near_miss in line
    ]

    assert offenders == [], (
        f"{near_miss} is neither gitignored nor pruned; "
        f"use {SANCTIONED_TEMP_ROOT} instead. Offenders: {offenders}"
    )
