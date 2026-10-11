"""Shared setup for the CLI smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard

_ORIGINAL_POPEN = subprocess.Popen


def pytest_configure(config: pytest.Config) -> None:
    """Refuse any Copilot launch when the pre-push gate runs the local smoke.

    This runs when pytest loads this conftest, before it imports or collects
    the test modules here, so a launch at import time is refused too.
    """
    if local_smoke_guard.guard_active():
        local_smoke_guard.install(lambda target, name, value: setattr(target, name, value))


def pytest_unconfigure(config: pytest.Config) -> None:
    """Put the real ``subprocess.Popen`` back when the session ends."""
    setattr(subprocess, "Popen", _ORIGINAL_POPEN)  # noqa: B010
