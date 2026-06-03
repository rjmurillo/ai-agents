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
    # Neither standalone `act` nor `gh` is on PATH.
    mock_which.return_value = None

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
def test_gh_present_but_no_act_extension(mock_run, mock_which):
    # `gh` is on PATH but the `gh act` extension is not installed.
    # `gh act --version` exits non-zero → falls back to "not found" (rc=2).
    mock_which.side_effect = lambda cmd: "/usr/bin/gh" if cmd == "gh" else None
    mock_run.return_value = _completed(stderr="unknown command \"act\"\n", rc=1)

    rc = main(["--workflow", "pester-tests"])
    assert rc == 2


@patch("shutil.which")
@patch("subprocess.run")
def test_gh_act_extension_fallback_succeeds(mock_run, mock_which, capsys):
    # No standalone `act`, but `gh` is present AND `gh act --version` works.
    # The script must use `gh act ...` for both version probe and execution.
    def which_side(cmd):
        if cmd == "act":
            return None
        return f"/usr/bin/{cmd}"

    mock_which.side_effect = which_side

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["gh", "act"] and len(cmd) >= 3 and cmd[2] == "--version":
            return _completed(stdout="gh act version 0.2.89\n", rc=0)
        if cmd[0] == "docker" and cmd[1] == "info":
            return _completed(rc=0)
        if cmd[:2] == ["gh", "auth"]:
            return _completed(stdout="ghp_token\n", rc=0)
        if cmd[:2] == ["gh", "act"]:
            # Workflow execution via gh act
            return _completed(rc=0)
        return _completed(rc=0)

    mock_run.side_effect = fake_run

    # Use a real workflow path via dry-run to skip resolution failure
    main(["--workflow", "pester-tests", "--dry-run"])
    # We don't assert rc==0 (workflow file may not exist in mocked env),
    # but we MUST have invoked the `gh act` runtime — not `act`.
    invoked_cmds = [c[0] for c in calls]
    assert "gh" in invoked_cmds, f"Expected gh-act invocation; got {calls}"
    # And we must never have tried to invoke standalone `act` directly.
    assert not any(c and c[0] == "act" for c in calls), (
        f"Should not invoke standalone act when only gh act is available; got {calls}"
    )
    out = capsys.readouterr().out
    assert "gh act" in out, "Log output should mention gh act runtime"


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
        _completed(stdout="ghp_secret_token\n", rc=0),  # gh auth token
        _completed(rc=0),  # act run
    ]

    rc = main([
        "--workflow",
        "pester-tests",
        "--secrets",
        '{"API_TOKEN":"user_secret_value"}',
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "API_TOKEN=<redacted>" in out
    assert "GITHUB_TOKEN=<redacted>" in out
    assert "user_secret_value" not in out
    assert "ghp_secret_token" not in out
