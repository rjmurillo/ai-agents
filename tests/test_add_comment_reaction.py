"""Tests for add_comment_reaction.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "reactions"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("add_comment_reaction")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_single_reaction(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0, stdout="{}"),  # add reaction
    ]

    rc = main(["--comment-id", "123", "--reaction", "eyes"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["succeeded"] == 1
    assert output["failed"] == 0


@patch("subprocess.run")
def test_batch_reactions(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0, stdout="{}"),  # first
        _completed(rc=0, stdout="{}"),  # second
        _completed(rc=0, stdout="{}"),  # third
    ]

    rc = main(["--comment-id", "1", "2", "3", "--reaction", "+1"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_count"] == 3
    assert output["succeeded"] == 3


@patch("subprocess.run")
def test_partial_failure(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(rc=0, stdout="{}"),
        _completed(rc=1, stderr="error"),
    ]

    rc = main(["--comment-id", "1", "2", "--reaction", "heart"])
    assert rc == 3
    output = json.loads(capsys.readouterr().out)
    assert output["succeeded"] == 1
    assert output["failed"] == 1


@patch("subprocess.run")
def test_issue_comment_type(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(rc=0, stdout="{}"),
    ]

    rc = main(["--comment-id", "99", "--comment-type", "issue", "--reaction", "rocket"])
    assert rc == 0
    # Verify endpoint used "issues/comments" not "pulls/comments"
    call_args = mock_run.call_args_list[2][0][0]
    assert "issues/comments" in call_args[2]
