"""Shared fixtures for the skillify tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = str(Path(__file__).resolve().parent)
_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillify" / "scripts"
)
sys.path.insert(0, _TEST_DIR)
sys.path.insert(0, _SCRIPTS_DIR)
try:
    # Cached in sys.modules so test modules can import them after the paths are removed.
    import skill_fixtures  # noqa: F401
    import skillify  # noqa: F401
    import skillify_text  # noqa: F401
    import skillify_verify  # noqa: F401
finally:
    sys.path.remove(_SCRIPTS_DIR)
    sys.path.remove(_TEST_DIR)


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root
