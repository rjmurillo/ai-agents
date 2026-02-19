"""Tests for set_issue_milestone.py skill script."""

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


_mod = _import_script("set_issue_milestone")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_assign_milestone(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout="null\n"),  # current milestone
        _completed(stdout="v1.0.0\nv2.0.0\n"),  # list milestones
        _completed(rc=0),  # gh issue edit --milestone
    ]

    rc = main(["--issue", "1", "--milestone", "v1.0.0"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["action"] == "assigned"


@patch("subprocess.run")
def test_already_has_same_milestone(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout="v1.0.0\n"),  # current milestone
        _completed(stdout="v1.0.0\n"),  # list milestones
    ]

    rc = main(["--issue", "1", "--milestone", "v1.0.0"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["action"] == "no_change"


@patch("subprocess.run")
def test_has_different_milestone_no_force(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="v0.9.0\n"),  # different milestone
        _completed(stdout="v0.9.0\nv1.0.0\n"),
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--milestone", "v1.0.0"])
    assert exc_info.value.code == 5


@patch("subprocess.run")
def test_force_replace_milestone(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="v0.9.0\n"),
        _completed(stdout="v0.9.0\nv1.0.0\n"),
        _completed(rc=0),  # set milestone
    ]

    rc = main(["--issue", "1", "--milestone", "v1.0.0", "--force"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["action"] == "replaced"


@patch("subprocess.run")
def test_clear_milestone(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="v1.0.0\n"),  # has milestone
        _completed(rc=0),  # clear via PATCH
    ]

    rc = main(["--issue", "1", "--clear"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["action"] == "cleared"


@patch("subprocess.run")
def test_clear_no_milestone(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="null\n"),  # no milestone
    ]

    rc = main(["--issue", "1", "--clear"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["action"] == "no_change"


@patch("subprocess.run")
def test_milestone_not_found(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="null\n"),
        _completed(stdout="other-milestone\n"),  # doesn't match
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--milestone", "nonexistent"])
    assert exc_info.value.code == 2
