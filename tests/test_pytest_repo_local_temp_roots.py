"""Regression guards for repo-local pytest temp roots."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path


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
