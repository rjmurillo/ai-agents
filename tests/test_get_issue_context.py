"""Tests for get_issue_context.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.mock_fidelity import assert_mock_keys_match

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


_mod = _import_script("get_issue_context")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _issue_data(**overrides):
    """Build a mock issue dict matching the canonical fixture shape."""
    data = {
        "number": 42,
        "title": "Test Issue",
        "body": "Issue body text",
        "state": "OPEN",
        "author": {"login": "testuser"},
        "labels": [{"name": "bug"}, {"name": "P1"}],
        "milestone": {"title": "v1.0.0"},
        "assignees": [{"login": "dev1"}],
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-02T00:00:00Z",
    }
    data.update(overrides)
    return data


def _issue_json(**overrides):
    return json.dumps(_issue_data(**overrides))


def test_mock_shape_matches_fixture():
    """Validate that the test mock shape matches the canonical API fixture."""
    assert_mock_keys_match(_issue_data(), "issue")


@patch("subprocess.run")
def test_happy_path(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # gh auth status
        _completed(stdout="https://github.com/owner/repo\n"),  # git remote
        _completed(stdout=_issue_json()),  # gh issue view
    ]

    rc = main(["--issue", "42"])
    assert rc == 0

    output = json.loads(capsys.readouterr().out)
    assert isinstance(output, dict)
    assert output["success"] is True
    assert isinstance(output["number"], int)
    assert output["number"] == 42
    assert isinstance(output["title"], str)
    assert output["title"] == "Test Issue"
    assert isinstance(output["labels"], list)
    assert output["labels"] == ["bug", "P1"]
    assert output["milestone"] == "v1.0.0"
    assert isinstance(output["assignees"], list)
    assert output["assignees"] == ["dev1"]


@patch("subprocess.run")
def test_issue_not_found(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),  # gh auth status
        _completed(stdout="https://github.com/owner/repo\n"),  # git remote
        _completed(rc=1, stderr="not found"),  # gh issue view
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "999"])
    assert exc_info.value.code == 2


@patch("subprocess.run")
def test_no_milestone(mock_run, capsys):
    issue = json.dumps({
        "number": 10,
        "title": "No milestone",
        "body": "",
        "state": "OPEN",
        "author": {"login": "u"},
        "labels": [],
        "milestone": None,
        "assignees": [],
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-01T00:00:00Z",
    })
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=issue),
    ]

    rc = main(["--issue", "10"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["milestone"] is None


@patch("subprocess.run")
def test_auth_failure(mock_run):
    mock_run.return_value = _completed(rc=1)

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1"])
    assert exc_info.value.code == 4
