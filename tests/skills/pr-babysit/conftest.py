"""Shared fixture for the pr_wait.py tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.skills.claude_skills_import import import_cached_module

_helpers: Any = import_cached_module(
    "tests/skills/pr-babysit/_pr_wait_helpers.py", "_pr_wait_helpers"
)
pw = _helpers.pw


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    clock = {"now": 1_000_000.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(pw, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(pw.time, "sleep", sleep)
    monkeypatch.setattr(pw.time, "time", lambda: clock["now"])
    return tmp_path
