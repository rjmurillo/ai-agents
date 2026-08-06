"""Regression tests for the Validate Plugin Manifests action test runtime."""

from __future__ import annotations

import re
from pathlib import Path

import tomllib
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_PATH = _REPO_ROOT / ".github" / "actions" / "validate-plugin-manifests" / "action.yml"
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"


def _action_steps(action_text: str) -> list[dict[str, object]]:
    parsed = yaml.safe_load(action_text)
    runs = parsed.get("runs", {})
    return runs.get("steps", [])


def _install_commands(action_text: str) -> list[str]:
    return [
        str(step.get("run", ""))
        for step in _action_steps(action_text)
        if "pip install" in str(step.get("run", ""))
    ]


def _pytest_addopts(pyproject_text: str) -> str:
    parsed = tomllib.loads(pyproject_text)
    return str(parsed["tool"]["pytest"]["ini_options"].get("addopts", ""))


def _missing_required_pytest_plugins(action_text: str, pyproject_text: str) -> list[str]:
    required: list[str] = []
    if "--timeout" in _pytest_addopts(pyproject_text):
        required.append("pytest-timeout")

    install_text = "\n".join(_install_commands(action_text))
    return [package for package in required if not re.search(rf"\b{package}\b", install_text)]


def test_validate_plugin_manifests_action_installs_pytest_timeout_plugin() -> None:
    """Positive: the action installs the plugin required by pytest addopts."""
    missing = _missing_required_pytest_plugins(
        _ACTION_PATH.read_text(encoding="utf-8"),
        _PYPROJECT_PATH.read_text(encoding="utf-8"),
    )

    assert missing == []


def test_action_missing_pytest_timeout_is_reported_when_addopts_uses_timeout() -> None:
    """Negative: pytest exits before tests when --timeout has no plugin."""
    action = """
runs:
  steps:
    - name: Install pytest
      run: python3 -m pip install 'pytest==9.0.3'
"""
    pyproject = """
[tool.pytest.ini_options]
addopts = "-v --timeout=120"
"""

    assert _missing_required_pytest_plugins(action, pyproject) == ["pytest-timeout"]


def test_action_without_timeout_addopts_does_not_require_pytest_timeout() -> None:
    """Edge: the dependency is required only when addopts names the plugin."""
    action = """
runs:
  steps:
    - name: Install pytest
      run: python3 -m pip install 'pytest==9.0.3'
"""
    pyproject = """
[tool.pytest.ini_options]
addopts = "-v"
"""

    assert _missing_required_pytest_plugins(action, pyproject) == []
