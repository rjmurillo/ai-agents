"""The AI resolver may only write files git reports as conflicted (D27, CWE-22/CWE-94).

Conflict text comes from the pull request and can steer the model, so an AI-chosen
path must never reach ``.git/`` (hooks, config) or the ``.trusted-helper`` checkout
that later secret-bearing steps run from.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.ci.apply_ai_conflict_resolution as aacr


@pytest.mark.parametrize(
    "filepath",
    [
        ".git/hooks/pre-commit",
        "./.git/config",
        ".trusted-helper/scripts/ci/invoke_pr_comment_processing.py",
        "src/../.git/hooks/post-commit",
    ],
)
def test_safe_repo_path_rejects_git_and_trusted_helper(
    filepath: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="protected"):
        aacr._safe_repo_path(filepath)


def _git_with_conflicts(conflicted: str, calls: list[list[str]]):
    """Fake git: the first conflict listing returns ``conflicted``, later ones are clean."""
    listings = iter([conflicted])

    def fake(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:3] == ["diff", "--name-only", "--diff-filter=U"]:
            return subprocess.CompletedProcess(args, 0, next(listings, ""), "")
        return subprocess.CompletedProcess(args, 0, "", "")

    return fake


def test_main_rejects_a_resolution_for_a_file_that_is_not_conflicted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEAD_REF", "feat/x")
    monkeypatch.setenv("BASE_REF", "main")
    resolution = {
        "file": "notes/new.txt",
        "strategy": "combine",
        "reasoning": "",
        "combined_content": "planted",
    }
    monkeypatch.setenv("AI_FINDINGS", json.dumps({"resolutions": [resolution]}))
    calls: list[list[str]] = []

    with patch.object(aacr, "_git", _git_with_conflicts("f.py\n", calls)):
        rc = aacr.main()

    assert rc == aacr.EXIT_FAILURE
    assert ["merge", "--abort"] in calls
    assert not (tmp_path / "notes" / "new.txt").exists()
