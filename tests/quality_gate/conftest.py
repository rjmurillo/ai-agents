"""Shared pytest setup for quality-gate script tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality_gate import path_utils


@pytest.fixture(autouse=True)
def isolate_repository_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(path_utils, "REPOSITORY_ROOT", tmp_path)
