from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ci import main_pytest_failure_alert as alert

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(needs: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        "NEEDS_JSON": json.dumps(needs),
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_RUN_ID": "123",
        "GITHUB_SHA": "abcdef1234567890",
        "GITHUB_SERVER_URL": "https://github.com",
    }


def _completed(stdout: str = "{}", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(["gh"], rc, stdout, stderr)


def test_no_failed_needs_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(alert, "_run_gh", lambda args: calls.append(args))

    rc = alert.run(_env({"test": {"result": "success"}}))

    assert rc == 0
    assert calls == []


@pytest.mark.parametrize("result", ["failure", "cancelled", "timed_out"])
def test_failing_need_states_trigger_issue(monkeypatch, result):
    calls = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["api", "search/issues"]:
            return _completed(stdout=json.dumps({"items": []}))
        return _completed(stdout=json.dumps({"number": 77}))

    monkeypatch.setattr(alert, "_run_gh", fake_gh)

    rc = alert.run(_env({"test": {"result": result}}))

    assert rc == 0
    assert calls[1][:4] == ["api", "repos/o/r/issues", "-X", "POST"]


def test_failed_need_creates_issue(monkeypatch):
    calls = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["api", "search/issues"]:
            return _completed(stdout=json.dumps({"items": []}))
        return _completed(stdout=json.dumps({"number": 77}))

    monkeypatch.setattr(alert, "_run_gh", fake_gh)

    rc = alert.run(_env({"test": {"result": "failure"}}))

    assert rc == 0
    assert calls[1][:4] == ["api", "repos/o/r/issues", "-X", "POST"]
    assert any("Python Tests failed on main" in arg for arg in calls[1])


def test_existing_issue_gets_comment(monkeypatch):
    calls = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["api", "search/issues"]:
            return _completed(stdout=json.dumps({"items": [{"number": 77}]}))
        return _completed(stdout=json.dumps({"id": 1}))

    monkeypatch.setattr(alert, "_run_gh", fake_gh)

    rc = alert.run(_env({"test": {"result": "failure"}}))

    assert rc == 0
    assert calls[1][:4] == ["api", "repos/o/r/issues/77/comments", "-X", "POST"]


def test_gh_failure_exits_external(monkeypatch):
    monkeypatch.setattr(alert, "_run_gh", lambda args: _completed(stderr="api down", rc=1))

    rc = alert.run(_env({"test": {"result": "failure"}}))

    assert rc == 3


def test_main_gh_failure_exits_external(monkeypatch):
    for key, value in _env({"test": {"result": "failure"}}).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(alert, "_run_gh", lambda args: _completed(stderr="api down", rc=1))

    rc = alert.main()

    assert rc == 3


def test_run_gh_returns_completed_process_on_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = alert._run_gh(["api", "search/issues"])

    assert result.returncode == 1
    assert "timed out" in result.stderr.lower()


def test_run_gh_returns_completed_process_when_gh_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = alert._run_gh(["api", "search/issues"])

    assert result.returncode == 1
    assert "gh not found" in result.stderr


def test_pytest_workflow_wires_main_failure_alert():
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["main-failure-alert"]

    assert "test" in job["needs"]
    assert "security" in job["needs"]
    assert "test-windows-pwsh" in job["needs"]
    assert "github.ref_name == github.event.repository.default_branch" in job["if"]
    assert any(
        step.get("run") == "python scripts/ci/main_pytest_failure_alert.py"
        for step in job["steps"]
    )
