"""Shared fixtures for the CLI smoke tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard


@pytest.fixture(autouse=True)
def _refuse_copilot_in_local_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any Copilot launch when the pre-push gate runs the local smoke."""
    if local_smoke_guard.guard_active():
        local_smoke_guard.install(monkeypatch.setattr)
