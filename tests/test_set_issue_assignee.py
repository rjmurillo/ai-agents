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
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "issue"
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
    assert output["Success"] is True
    assert output["Data"]["applied"] == ["@me"]
    assert output["Data"]["failed"] == []


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
    assert output["Data"]["total_applied"] == 2


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
    assert output["Success"] is False
    assert output["Data"]["applied"] == []
    assert output["Data"]["failed"] == ["bad1", "bad2"]
    assert output["Data"]["total_applied"] == 0


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
    assert output["Data"]["issue"] == 99
    assert isinstance(output["Data"]["applied"], list)
    assert isinstance(output["Data"]["failed"], list)
    assert isinstance(output["Data"]["total_applied"], int)


@patch("subprocess.run")
def test_dry_run_reports_assignees_and_makes_no_edit_call(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout='{"number": 42}'),  # issue view
    ]

    rc = main(["--issue", "42", "--assignees", "@me", "octocat", "--dry-run"])

    data = json.loads(capsys.readouterr().out)["Data"]
    assert rc == 0
    assert data["dryRun"] is True
    assert data["action"] == "would_assign"
    assert data["wouldAssign"] == ["@me", "octocat"]
    assert all(c.args[0][:3] != ["gh", "issue", "edit"] for c in mock_run.call_args_list)
    assert mock_run.call_args_list[-1].args[0][:3] == ["gh", "issue", "view"]


@patch("subprocess.run")
def test_dry_run_still_requires_assignees(mock_run):
    with pytest.raises(SystemExit) as exc:
        main(["--issue", "42", "--dry-run"])

    assert exc.value.code == 2
    mock_run.assert_not_called()


@patch("subprocess.run")
def test_default_run_has_no_dry_run_key(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(rc=0),
    ]

    rc = main(["--issue", "42", "--assignees", "octocat"])

    assert rc == 0
    assert "dryRun" not in json.loads(capsys.readouterr().out)["Data"]


@patch("subprocess.run")
def test_dry_run_on_a_missing_issue_exits_3_like_a_real_assignment(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(rc=1, stderr="Could not resolve to an Issue"),
    ]

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "4242", "--assignees", "octocat", "--dry-run"])

    output = json.loads(capsys.readouterr().out)
    assert exc.value.code == 3
    assert output["Success"] is False
    assert "Failed to read issue #4242 in o/r" in output["Error"]["Message"]
    assert all(c.args[0][:3] != ["gh", "issue", "edit"] for c in mock_run.call_args_list)


@patch("subprocess.run")
def test_dry_run_issue_read_timeout_exits_3_with_an_envelope(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        subprocess.TimeoutExpired("gh", 30),
    ]

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "42", "--assignees", "octocat", "--dry-run"])

    output = json.loads(capsys.readouterr().out)
    assert exc.value.code == 3
    assert output["Error"]["Type"] == "Timeout"
    assert mock_run.call_args_list[-1].kwargs["timeout"] == 30


@patch("subprocess.run")
def test_dry_run_issue_read_has_a_timeout(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout='{"number": 42}'),
    ]

    assert main(["--issue", "42", "--assignees", "octocat", "--dry-run"]) == 0
    assert mock_run.call_args_list[-1].kwargs["timeout"] == 30
