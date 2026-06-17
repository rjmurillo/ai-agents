"""Tests for new_issue.py skill script."""

from __future__ import annotations

import importlib.util
import json
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


_mod = _import_script("new_issue")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_create_issue_with_body(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/owner/repo\n"),  # remote
        _completed(stdout="https://github.com/owner/repo/issues/99\n"),  # create
    ]

    rc = main(["--title", "Bug: Something broke", "--body", "Steps to reproduce..."])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["Success"] is True
    assert output["Data"]["issue_number"] == 99


@patch("subprocess.run")
def test_create_issue_with_labels(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout="https://github.com/o/r/issues/5\n"),  # create
        _completed(rc=0),  # edit --add-label
    ]

    rc = main(["--title", "Feature", "--labels", "enhancement,P2"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["Data"]["issue_number"] == 5
    edit_kwargs = mock_run.call_args_list[3].kwargs
    assert edit_kwargs["encoding"] == "utf-8"
    assert edit_kwargs["errors"] == "replace"


@patch("subprocess.run")
def test_missing_label_emits_json_envelope_with_issue_number(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout="https://github.com/o/r/issues/42\n"),  # create succeeds
        _completed(rc=1, stderr="could not add label: 'ci' not found"),  # label fails
    ]

    rc = main(["--title", "Bug", "--labels", "bug,ci", "--output-format", "json"])

    assert rc == 3
    output = json.loads(capsys.readouterr().out)
    assert output["Success"] is False
    assert output["Error"]["Type"] == "ApiError"
    assert output["Data"]["issue_number"] == 42
    assert output["Data"]["url"] == "https://github.com/o/r/issues/42"


@patch("subprocess.run")
def test_empty_title_fails(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
    ]

    rc = main(["--title", "   ", "--output-format", "json"])
    assert rc == 2
    output = json.loads(capsys.readouterr().out)
    assert output["Success"] is False
    assert output["Error"]["Type"] == "InvalidParams"


@patch("subprocess.run")
def test_api_failure(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(rc=1, stderr="API error"),
    ]

    rc = main(["--title", "Test", "--output-format", "json"])
    assert rc == 3
    output = json.loads(capsys.readouterr().out)
    assert output["Success"] is False
    assert output["Error"]["Type"] == "ApiError"
    create_kwargs = mock_run.call_args_list[2].kwargs
    assert create_kwargs["encoding"] == "utf-8"
    assert create_kwargs["errors"] == "replace"


@patch("subprocess.run")
def test_body_file(mock_run, capsys, tmp_path):
    body_file = tmp_path / "body.md"
    body_file.write_text("File-based body content")

    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="https://github.com/o/r/issues/7\n"),
    ]

    rc = main(["--title", "From file", "--body-file", str(body_file)])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["Data"]["issue_number"] == 7


@patch("subprocess.run")
def test_body_file_not_found(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
    ]

    rc = main(["--title", "Test", "--body-file", "/nonexistent/file.md",
               "--output-format", "json"])
    assert rc == 2
    output = json.loads(capsys.readouterr().out)
    assert output["Success"] is False
    assert output["Error"]["Type"] == "NotFound"
