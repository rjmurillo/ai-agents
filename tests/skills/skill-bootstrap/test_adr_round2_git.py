"""Review round 2 tests for the git environment and the commit reader: items 3 and 11."""

from __future__ import annotations

import os
from pathlib import Path

import adr_scan
import pytest
from adr_helpers import commit, new_repo, run_cli, write
from draft_helpers import _cand, _scan_file

# ---------------------------------------------------------------------------
# Item 3: discovery limits in the parent environment do not reach git
# ---------------------------------------------------------------------------


def test_git_env_drops_the_discovery_limit_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/somewhere")
    monkeypatch.setenv("GIT_DISCOVERY_ACROSS_FILESYSTEM", "1")
    env = adr_scan.git_env()
    assert "GIT_CEILING_DIRECTORIES" not in env
    assert "GIT_DISCOVERY_ACROSS_FILESYSTEM" not in env


def test_a_ceiling_at_the_repository_does_not_turn_an_in_repo_folder_into_scratch(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    (repo / "docs" / "other").mkdir()
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _cand())
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(repo)}
    code, payload = run_cli(
        "draft",
        "--scan",
        scan,
        "--id",
        "c-1234567",
        "--out",
        str(repo / "docs" / "other"),
        env=env,
    )
    assert code == 2 and payload["error"] == "config"
    assert not list((repo / "docs" / "other").iterdir())
