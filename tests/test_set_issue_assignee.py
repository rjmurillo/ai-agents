"""Tests for set_issue_assignee.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


_mod = _import_script("set_issue_assignee")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_assign_single_user(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # gh auth status
        _completed(stdout="https://github.com/owner/repo\n"),  # git remote
        _completed(rc=0),  # gh issue edit --add-assignee
    ]

    rc = main(["--issue", "42", "--assignees", "@me"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["applied"] == ["@me"]
    assert output["failed"] == []


@patch("subprocess.run")
def test_assign_multiple_users(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0),  # first assignee
        _completed(rc=0),  # second assignee
    ]

    rc = main(["--issue", "1", "--assignees", "user1", "user2"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_applied"] == 2


@patch("subprocess.run")
def test_partial_failure(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0),  # first succeeds
        _completed(rc=1),  # second fails
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--assignees", "good", "bad"])
    assert exc_info.value.code == 3


@patch("subprocess.run")
def test_auth_failure(mock_run):
    mock_run.return_value = _completed(rc=1)

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--assignees", "user"])
    assert exc_info.value.code == 4


@patch("subprocess.run")
def test_all_assignees_fail(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1),  # first fails
        _completed(rc=1),  # second fails
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--assignees", "bad1", "bad2"])
    assert exc_info.value.code == 3
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is False
    assert output["applied"] == []
    assert output["failed"] == ["bad1", "bad2"]
    assert output["total_applied"] == 0


@patch("subprocess.run")
def test_output_structure(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0),  # assign
    ]

    rc = main(["--issue", "99", "--assignees", "alice"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["issue"] == 99
    assert isinstance(output["applied"], list)
    assert isinstance(output["failed"], list)
    assert isinstance(output["total_applied"], int)
