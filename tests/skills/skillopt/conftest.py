"""Shared path setup for the skillopt tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillopt"
_IMPORT_PATHS = (str(SKILL_DIR / "scripts"), str(Path(__file__).parent))
sys.path[:0] = _IMPORT_PATHS
try:
    # Cached in sys.modules so the test modules' top-level imports resolve
    # after the paths are removed again.
    import mine_sessions  # noqa: F401
    import skillopt  # noqa: F401
    import skillopt_helpers  # noqa: F401
finally:
    for _path in _IMPORT_PATHS:
        sys.path.remove(_path)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty fake home so default source discovery never reads the real one."""
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake))
    return fake


@pytest.fixture
def python_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Commands name the interpreter bare, as eval.json does; the runner reads PATH."""
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
