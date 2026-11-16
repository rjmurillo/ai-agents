"""Shared fixture for the pr_wait.py tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_helpers = sys.modules.get("_pr_wait_helpers")
if _helpers is None:
    _spec = importlib.util.spec_from_file_location(
        "_pr_wait_helpers", Path(__file__).with_name("_pr_wait_helpers.py")
    )
    assert _spec and _spec.loader
    _helpers = importlib.util.module_from_spec(_spec)
    sys.modules["_pr_wait_helpers"] = _helpers
    _spec.loader.exec_module(_helpers)
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
