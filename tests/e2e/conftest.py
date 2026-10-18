"""Shared setup for the CLI smoke tests."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard


def pytest_configure(config: pytest.Config) -> None:
    """Refuse any Copilot launch when the pre-push gate runs the local smoke.

    This runs when pytest loads this conftest, before it imports or collects
    the test modules here, so a launch at import time is refused too.
    """
    if local_smoke_guard.guard_active():
        local_smoke_guard.install(lambda target, name, value: setattr(target, name, value))
        local_smoke_guard.install_path_shim()


def pytest_unconfigure(config: pytest.Config) -> None:
    """Put the real ``subprocess.Popen``, ``os`` spawns, and ``PATH`` back at session end."""
    local_smoke_guard.uninstall()


@pytest.fixture
def isolated_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Let a test install or uninstall the guard without touching the session's own.

    Under the pre-push gate this conftest armed the real guard and the PATH shim for the
    whole session. A test that calls ``uninstall`` or ``remove_path_shim`` would strip them
    from every test after it. This fixture gives the test empty shim state and puts back
    ``subprocess.Popen``, the ``os`` spawn functions, and ``PATH`` when it ends.
    """
    state = local_smoke_guard.snapshot()
    monkeypatch.setattr(local_smoke_guard, "_shim_dir", None)
    monkeypatch.setattr(local_smoke_guard, "_saved_path", None)
    try:
        yield
    finally:
        local_smoke_guard.remove_path_shim()
        local_smoke_guard.restore(state)
