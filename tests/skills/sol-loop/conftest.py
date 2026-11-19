"""Fixtures shared by the sol-loop tests.

The skill directory name has a hyphen, so it is not an importable package.
``_sol_loop_helpers`` is loaded from its file path and registered in
``sys.modules``, which lets test modules write ``from _sol_loop_helpers import ...``
without putting any directory on ``sys.path``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_HELPERS = "_sol_loop_helpers"


def _load_helpers() -> Any:
    """Load the helpers module by path once and register it by name."""
    if _HELPERS in sys.modules:
        return sys.modules[_HELPERS]
    path = Path(__file__).resolve().with_name(f"{_HELPERS}.py")
    spec = importlib.util.spec_from_file_location(_HELPERS, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_HELPERS] = module
    spec.loader.exec_module(module)
    return module


CRITIC_TEXT = _load_helpers().CRITIC_TEXT


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("AI_AGENTS_ARTIFACT_ROOT", "AI_AGENTS_SOL_PASS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def critic_file(tmp_path):
    path = tmp_path / "critic.md"
    path.write_text(CRITIC_TEXT, encoding="utf-8")
    return path
