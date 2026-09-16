"""Pytest fixtures for the gate_latency test modules.

Only fixtures live here. The captured lefthook output, the subprocess fakes,
and the shared invocation helpers are ordinary functions, so they live in
``gate_latency_helpers.py`` beside this file and are imported by name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.metrics.gate_latency_classes import CHANGE_CLASSES
from tests.gc_real_git import git
from tests.metrics.gate_latency_helpers import _LEFTHOOK_YML


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small git repo with a real lefthook.yml and every change-class path."""
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    _write(root, "lefthook.yml", _LEFTHOOK_YML)
    for rel in CHANGE_CLASSES.values():
        for path in rel:
            _write(root, path, "placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


