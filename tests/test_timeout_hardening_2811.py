"""Subprocess timeout hardening for github skill scripts (issue #2811).

A hung ``gh`` call must not stall an agent hook or a CI step without an upper
bound. These tests assert that the mutating label calls pass a timeout and that
a ``subprocess.TimeoutExpired`` degrades to a failed result rather than
propagating an uncaught exception.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_labels = _import_script("set_issue_labels")


@patch("subprocess.run")
def test_apply_label_passes_timeout(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    assert _labels._apply_label("o", "r", 1, "P1") is True
    assert mock_run.call_args.kwargs["timeout"] == _labels.GH_TIMEOUT_SECONDS


@patch("subprocess.run")
def test_apply_label_timeout_returns_false(mock_run) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=15)
    assert _labels._apply_label("o", "r", 1, "P1") is False


@patch("subprocess.run")
def test_remove_label_passes_timeout(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    assert _labels._remove_label("o", "r", 1, "P1") is True
    assert mock_run.call_args.kwargs["timeout"] == _labels.GH_TIMEOUT_SECONDS


@patch("subprocess.run")
def test_remove_label_timeout_returns_false(mock_run) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=15)
    assert _labels._remove_label("o", "r", 1, "P1") is False
