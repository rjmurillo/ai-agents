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
    assert output["Success"] is True
    assert "bug" in output["Data"]["applied"]


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
    assert "new-label" in output["Data"]["created"]
    assert "new-label" in output["Data"]["applied"]


@patch("subprocess.run")
def test_priority_label(mock_run, capsys):
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1),  # priority label doesn't exist
        _completed(rc=0),  # create priority label
        _completed(rc=0),  # apply priority label
        _completed(stdout='{"labels": []}', rc=0),  # _get_issue_labels for reconcile
    ]

    rc = main(["--issue", "1", "--priority", "P1"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert "priority:P1" in output["Data"]["applied"]


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


@patch("subprocess.run")
def test_create_failure_skips_apply(mock_run, capsys):
    """When label creation fails, the label is marked failed and apply is skipped."""
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1),  # label does not exist
        _completed(rc=1),  # create fails
    ]

    with pytest.raises(SystemExit) as exc_info:
        main(["--issue", "1", "--labels", "fail-to-create"])
    assert exc_info.value.code == 3
    output = json.loads(capsys.readouterr().out)
    assert "fail-to-create" in output["Data"]["failed"]
    assert output["Data"]["applied"] == []


@patch("subprocess.run")
def test_no_create_missing_skips_label(mock_run, capsys):
    """With --no-create-missing, missing labels are silently skipped."""
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=1),  # label does not exist
    ]

    rc = main(["--issue", "1", "--labels", "missing", "--no-create-missing"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["Data"]["applied"] == []
    assert output["Data"]["failed"] == []
    assert output["Success"] is True


@patch("subprocess.run")
def test_mixed_existing_and_missing_labels(mock_run, capsys):
    """Multiple labels: one exists, one is created, both applied."""
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(rc=0),  # "bug" exists
        _completed(rc=0),  # apply "bug"
        _completed(rc=1),  # "new-one" does not exist
        _completed(rc=0),  # create "new-one"
        _completed(rc=0),  # apply "new-one"
    ]

    rc = main(["--issue", "1", "--labels", "bug", "new-one"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["Data"]["applied"] == ["bug", "new-one"]
    assert output["Data"]["created"] == ["new-one"]
    assert output["Data"]["total_applied"] == 2


@patch("subprocess.run")
def test_whitespace_labels_stripped(mock_run, capsys):
    """Whitespace-only labels are filtered out."""
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
    ]

    rc = main(["--issue", "1", "--labels", "  ", ""])
    assert rc == 0


def _view(*names: str):
    return _completed(stdout=json.dumps({"labels": [{"name": n} for n in names]}))


_PRE = [_completed(rc=0), _completed(stdout="https://github.com/o/r\n")]


@patch("subprocess.run")
def test_remove_label_present(mock_run, capsys):
    mock_run.side_effect = [*_PRE, _view("bug", "blocked:human"), _completed(rc=0)]

    rc = main(["--issue", "7", "--remove-labels", "blocked:human"])

    assert rc == 0
    data = json.loads(capsys.readouterr().out)["Data"]
    assert data["removed"] == ["blocked:human"]
    assert data["absent"] == []
    assert "--remove-label" in mock_run.call_args_list[-1].args[0]


@patch("subprocess.run")
def test_remove_label_absent_is_noop(mock_run, capsys):
    mock_run.side_effect = [*_PRE, _view("bug")]

    rc = main(["--issue", "7", "--remove-labels", "gone"])

    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)["Data"]
    assert data["absent"] == ["gone"]
    assert data["removed"] == []
    assert "not on #7" in captured.err
    assert mock_run.call_count == 3  # no edit call


@patch("subprocess.run")
def test_remove_label_case_insensitive(mock_run, capsys):
    mock_run.side_effect = [*_PRE, _view("Bug"), _completed(rc=0)]

    rc = main(["--issue", "7", "--remove-labels", "bug"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["Data"]["removed"] == ["Bug"]
    assert mock_run.call_args_list[-1].args[0][-1] == "Bug"


@patch("subprocess.run")
def test_remove_comma_and_repeat_syntax(mock_run, capsys):
    mock_run.side_effect = [
        *_PRE,
        _view("a", "b", "c"),
        _completed(rc=0),
        _completed(rc=0),
        _completed(rc=0),
    ]

    rc = main(["--issue", "7", "--remove-labels", "a,b", "--remove-labels", "c"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["Data"]["removed"] == ["a", "b", "c"]


@patch("subprocess.run")
def test_mixed_add_and_remove(mock_run, capsys):
    mock_run.side_effect = [
        *_PRE,
        _view("old"),  # strict fetch
        _completed(rc=0),  # label exists
        _completed(rc=0),  # add
        _completed(rc=0),  # remove
    ]

    rc = main(["--issue", "7", "--labels", "new", "--remove-labels", "old"])

    assert rc == 0
    data = json.loads(capsys.readouterr().out)["Data"]
    assert data["applied"] == ["new"]
    assert data["removed"] == ["old"]


@patch("subprocess.run")
def test_remove_empty_list_is_noop(mock_run, capsys):
    mock_run.side_effect = list(_PRE)

    rc = main(["--issue", "7", "--remove-labels", " , "])

    assert rc == 0
    assert "No labels to apply" in capsys.readouterr().err
    assert mock_run.call_count == 2


@patch("subprocess.run")
def test_remove_nonexistent_issue_exits_3(mock_run, capsys):
    mock_run.side_effect = [*_PRE, _completed(rc=1, stderr="Could not resolve")]

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "999999", "--remove-labels", "bug"])

    assert exc.value.code == 3


@patch("subprocess.run")
def test_remove_view_timeout_exits_3(mock_run):
    mock_run.side_effect = [*_PRE, subprocess.TimeoutExpired(cmd="gh", timeout=15)]

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "7", "--remove-labels", "bug"])

    assert exc.value.code == 3


@patch("subprocess.run")
def test_remove_view_bad_json_exits_3(mock_run):
    mock_run.side_effect = [*_PRE, _completed(stdout="not json")]

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "7", "--remove-labels", "bug"])

    assert exc.value.code == 3


@patch("subprocess.run")
def test_remove_edit_failure_exits_3(mock_run):
    mock_run.side_effect = [*_PRE, _view("bug"), _completed(rc=1)]

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "7", "--remove-labels", "bug"])

    assert exc.value.code == 3


@patch("subprocess.run")
def test_add_and_remove_same_label_exits_1(mock_run):
    mock_run.side_effect = list(_PRE)

    with pytest.raises(SystemExit) as exc:
        main(["--issue", "7", "--labels", "Bug", "--remove-labels", "bug"])

    assert exc.value.code == 1
    assert mock_run.call_count == 2


@patch("subprocess.run")
def test_remove_skips_label_already_removed_by_priority(mock_run, capsys):
    mock_run.side_effect = [
        *_PRE,
        _view("priority:P2"),  # strict snapshot
        _completed(rc=0),  # priority exists
        _completed(rc=0),  # add priority:P1
        _view("priority:P2", "priority:P1"),  # reconcile fetch
        _completed(rc=0),  # remove priority:P2
    ]

    rc = main(["--issue", "7", "--priority", "P1", "--remove-labels", "priority:P2"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["Data"]["removed"] == ["priority:P2"]
