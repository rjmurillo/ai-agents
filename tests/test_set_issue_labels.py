"""Tests for set_issue_labels.py skill script."""

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


_mod = _import_script("set_issue_labels")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_apply_existing_labels(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0),  # label exists check
        _completed(rc=0),  # gh issue edit --add-label
    ]

    rc = main(["--issue", "1", "--labels", "bug"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert "bug" in output["applied"]


@patch("subprocess.run")
def test_create_and_apply_missing_label(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1),  # label does not exist
        _completed(rc=0),  # create label
        _completed(rc=0),  # apply label
    ]

    rc = main(["--issue", "1", "--labels", "new-label"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert "new-label" in output["created"]
    assert "new-label" in output["applied"]


@patch("subprocess.run")
def test_priority_label(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1),  # priority label doesn't exist
        _completed(rc=0),  # create priority label
        _completed(rc=0),  # apply priority label
    ]

    rc = main(["--issue", "1", "--priority", "P1"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert "priority:P1" in output["applied"]


@patch("subprocess.run")
def test_no_labels_exits_early(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
    ]

    rc = main(["--issue", "1"])
    assert rc == 0


@patch("subprocess.run")
def test_apply_failure(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0),  # label exists
        _completed(rc=1),  # apply fails
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--labels", "broken"])
    assert exc_info.value.code == 3
