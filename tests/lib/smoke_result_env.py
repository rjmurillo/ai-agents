"""Shared environment for the smoke_result.py preset tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FORK_MESSAGE = (
    "Untrusted context: this change touches smoke paths from a fork pull request or a "
    "non-default ref. Forks get no secrets, so the CLI smoke cannot run. A maintainer "
    "must rerun it from a same-repo branch."
)

GREEN = {
    "RUN": "true",
    "CHANGES_RESULT": "success",
    "AUTHORIZE_RESULT": "success",
    "TRUSTED": "true",
    "SMOKE_RESULT": "success",
    "CODEX_RESULT": "success",
}


def apply_green(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """Set every job result to green and run from an empty directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    for key, value in GREEN.items():
        monkeypatch.setenv(key, value)
    return monkeypatch
