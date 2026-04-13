"""Tests for get_latest_semantic_milestone.py skill script."""

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


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_latest_semantic_milestone")
main = _mod.main


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@patch("subprocess.run")
def test_finds_latest_milestone(mock_run, capsys):
    milestones = json.dumps([
        {"title": "0.2.0", "number": 1},
        {"title": "0.10.0", "number": 2},
        {"title": "0.3.0", "number": 3},
    ])
    mock_run.side_effect = [
        _completed(rc=0),  # auth
        _completed(stdout="https://github.com/o/r\n"),  # remote
        _completed(stdout=milestones),  # milestones API
    ]

    rc = main([])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["found"] is True
    assert output["title"] == "0.10.0"
    assert output["number"] == 2


@patch("subprocess.run")
def test_no_milestones(mock_run):
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout="[]"),
    ]

    rc = main([])
    assert rc == 2


@patch("subprocess.run")
def test_no_semantic_milestones(mock_run):
    milestones = json.dumps([
        {"title": "Future", "number": 1},
        {"title": "Backlog", "number": 2},
    ])
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=milestones),
    ]

    rc = main([])
    assert rc == 2


@patch("subprocess.run")
def test_single_milestone(mock_run, capsys):
    milestones = json.dumps([{"title": "1.0.0", "number": 5}])
    mock_run.side_effect = [
        _completed(rc=0),
        _completed(stdout="https://github.com/o/r\n"),
        _completed(stdout=milestones),
    ]

    rc = main([])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["title"] == "1.0.0"
