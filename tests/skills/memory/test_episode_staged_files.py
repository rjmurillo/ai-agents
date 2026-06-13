"""Tests for the staged-files backfill in extract_session_episode (issue #2537).

The episode extractor runs in pre-commit, where the in-flight commit is staged
but no SHA exists. ``_staged_files_changed`` derives files_changed from
``git diff --cached --numstat`` so episodes stop reporting files_changed=0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "memory"
    / "scripts"
)
sys.path.insert(0, str(_SCRIPTS))

import extract_session_episode as ese  # noqa: E402


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


class TestStagedFilesChanged:
    def test_counts_numstat_lines(self) -> None:
        numstat = "3\t0\ta.py\n10\t2\tb.md\n0\t5\tc.txt\n"
        with patch.object(ese.subprocess, "run", return_value=_completed(numstat)):
            assert ese._staged_files_changed() == 3

    def test_zero_when_nothing_staged(self) -> None:
        with patch.object(ese.subprocess, "run", return_value=_completed("")):
            assert ese._staged_files_changed() == 0

    def test_zero_on_nonzero_returncode(self) -> None:
        with patch.object(ese.subprocess, "run", return_value=_completed("x", returncode=128)):
            assert ese._staged_files_changed() == 0

    def test_zero_when_git_missing(self) -> None:
        with patch.object(ese.subprocess, "run", side_effect=OSError("no git")):
            assert ese._staged_files_changed() == 0

    def test_zero_on_timeout(self) -> None:
        with patch.object(
            ese.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 10)
        ):
            assert ese._staged_files_changed() == 0

    def test_passes_cwd_via_git_c(self) -> None:
        with patch.object(ese.subprocess, "run", return_value=_completed("")) as run:
            ese._staged_files_changed("/some/repo")
        cmd = run.call_args[0][0]
        assert cmd[:3] == ["git", "-C", "/some/repo"]

    def test_runs_git_with_utf8_clean_env_and_c_locale(self) -> None:
        with (
            patch.dict(
                ese.os.environ,
                {
                    "GIT_DIR": "bad",
                    "GIT_WORK_TREE": "bad",
                    "GIT_COMMON_DIR": "bad",
                    "GIT_INDEX_FILE": "bad",
                    "PATH": "keep",
                },
                clear=True,
            ),
            patch.object(ese.subprocess, "run", return_value=_completed("")) as run,
        ):
            ese._staged_files_changed()

        kwargs = run.call_args.kwargs
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["env"]["LC_ALL"] == "C"
        assert kwargs["env"]["PATH"] == "keep"
        assert "GIT_DIR" not in kwargs["env"]
        assert "GIT_WORK_TREE" not in kwargs["env"]
        assert "GIT_COMMON_DIR" not in kwargs["env"]
        assert "GIT_INDEX_FILE" not in kwargs["env"]

    def test_non_repo_dir_yields_zero(self, tmp_path: Path) -> None:
        # Real git call against a non-repo path must return 0, not raise.
        assert ese._staged_files_changed(tmp_path) == 0
