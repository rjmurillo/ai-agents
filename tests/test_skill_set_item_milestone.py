"""Tests for set_item_milestone.py skill script (milestone/ directory)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "milestone"
)


def _import_script(name: str, module_alias: str = ""):
    alias = module_alias or name
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("set_item_milestone", "skill_set_item_milestone")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_assign_auto_detected(mock_run, capsys):
    item_data = json.dumps({"milestone": None})
    milestones = json.dumps([{"title": "0.3.0", "number": 5}])

    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=item_data),  # get item
        _completed(stdout=milestones),  # list milestones
        _completed(rc=0),  # assign milestone
    ]

    rc = main(["--item-type", "pr", "--item-number", "42"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "0.3.0" in out


@patch("subprocess.run")
def test_skip_existing_milestone(mock_run, capsys):
    item_data = json.dumps({"milestone": {"title": "0.2.0"}})

    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=item_data),
    ]

    rc = main(["--item-type", "issue", "--item-number", "10"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "skipped" in out


@patch("subprocess.run")
def test_explicit_milestone(mock_run, capsys):
    item_data = json.dumps({"milestone": None})

    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=item_data),
        _completed(rc=0),  # assign
    ]

    rc = main(["--item-type", "pr", "--item-number", "5", "--milestone-title", "1.0.0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1.0.0" in out


@patch("subprocess.run")
def test_no_semantic_milestone(mock_run):
    item_data = json.dumps({"milestone": None})
    milestones = json.dumps([{"title": "Backlog", "number": 1}])

    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=item_data),
        _completed(stdout=milestones),  # no semantic
    ]

    rc = main(["--item-type", "pr", "--item-number", "1"])
    assert rc == 2
