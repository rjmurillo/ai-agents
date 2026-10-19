"""Fixtures for tests that install or uninstall the local smoke guard (issue #6506).

Import ``isolated_guard`` into the test module that needs it.
"""

from __future__ import annotations

from collections.abc import Iterator

import local_smoke_guard
import local_smoke_shim
import pytest


@pytest.fixture
def isolated_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Let a test install or uninstall the guard without touching the session's own.

    Under the pre-push gate this conftest armed the real guard and the PATH shim for the
    whole session. A test that calls ``uninstall`` or ``remove_path_shim`` would strip them
    from every test after it. This fixture gives the test empty shim state and puts back
    ``subprocess.Popen``, the ``os`` spawn functions, and ``PATH`` when it ends.
    """
    state = local_smoke_guard.snapshot()
    monkeypatch.setattr(local_smoke_shim, "_shim_dir", None)
    monkeypatch.setattr(local_smoke_shim, "_saved_path", None)
    try:
        yield
    finally:
        local_smoke_shim.remove_path_shim()
        local_smoke_guard.restore(state)
