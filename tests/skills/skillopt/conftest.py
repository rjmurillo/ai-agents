"""Shared path setup for the skillopt tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillopt"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty fake home so default source discovery never reads the real one."""
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake))
    return fake
