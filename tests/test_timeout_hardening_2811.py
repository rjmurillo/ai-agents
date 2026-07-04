"""Subprocess timeout hardening for github skill scripts (issue #2811).

A hung ``gh`` call must not stall an agent hook or a CI step without an upper
bound. These tests assert that the mutating label calls pass a timeout and that
a ``subprocess.TimeoutExpired`` degrades to a failed result rather than
propagating an uncaught exception.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

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


_ctx = _import_script("get_issue_context")
_milestone = _import_script("set_issue_milestone")


@patch("subprocess.run")
def test_get_issue_context_timeout_exits_3(mock_run) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
    with (
        patch.object(_ctx, "assert_gh_authenticated", lambda: None),
        patch.object(
            _ctx,
            "resolve_repo_params",
            lambda o, r: types.SimpleNamespace(owner="o", repo="r"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        _ctx.main(["--issue", "1", "--owner", "o", "--repo", "r"])
    assert exc.value.code == 3


@patch("subprocess.run")
def test_current_milestone_timeout_returns_none(mock_run) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
    with pytest.raises(_milestone._MilestoneQueryError, match="current milestone"):
        _milestone._get_current_milestone("o", "r", 1)


@patch("subprocess.run")
def test_milestone_titles_timeout_returns_empty(mock_run) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
    with pytest.raises(_milestone._MilestoneQueryError, match="listing milestones"):
        _milestone._get_milestone_titles("o", "r")


@patch("subprocess.run")
def test_get_issue_labels_filters_empty_names(mock_run) -> None:
    payload = {"labels": [{"name": "P1"}, {"name": ""}, {"name": None}, {}]}
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload), stderr=""
    )
    assert _labels._get_issue_labels("o", "r", 1) == ["P1"]


def test_env_timeout_falls_back_on_bad_value(monkeypatch) -> None:
    monkeypatch.setenv("GH_TIMEOUT_SECONDS", "not-a-number")
    assert _ctx._env_timeout_seconds() == 30
    assert _milestone._env_timeout_seconds() == 30


def test_env_timeout_honors_valid_override(monkeypatch) -> None:
    monkeypatch.setenv("GH_TIMEOUT_SECONDS", "7")
    assert _ctx._env_timeout_seconds() == 7
