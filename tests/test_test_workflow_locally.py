"""Tests for test_workflow_locally.py skill script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("test_workflow_locally")
main = _mod.main
WORKFLOW_MAP = _mod.WORKFLOW_MAP


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class TestWorkflowMap:
    def test_known_workflows(self):
        assert "pester-tests" in WORKFLOW_MAP
        assert "validate-paths" in WORKFLOW_MAP


@patch("shutil.which")
def test_act_not_found(mock_which):
    mock_which.return_value = None

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
def test_docker_not_found(mock_run, mock_which):
    mock_which.side_effect = lambda cmd: "/usr/bin/act" if cmd == "act" else None
    mock_run.return_value = _completed(stdout="act version 0.2.0\n")

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
def test_workflow_not_found(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/act"
    mock_run.side_effect = [
        _completed(stdout="act version 0.2.0\n"),  # act --version
        _completed(rc=0),  # docker info
    ]

    rc = main(["--workflow", "nonexistent-workflow"])
    assert rc == 1


@patch("shutil.which")
@patch("subprocess.run")
@patch("os.path.exists")
def test_successful_run(mock_exists, mock_run, mock_which, capsys):
    mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
    mock_exists.return_value = True
    mock_run.side_effect = [
        _completed(stdout="act version 0.2.0\n"),  # act --version
        _completed(rc=0),  # docker info
        _completed(rc=0),  # gh auth token
        _completed(rc=0),  # act run
    ]

    rc = main(["--workflow", "pester-tests"])
    assert rc == 0
