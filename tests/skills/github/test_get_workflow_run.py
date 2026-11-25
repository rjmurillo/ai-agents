"""Tests for actions/get_workflow_run.py."""

import json
import sys
from unittest.mock import patch

import pytest
from github_core.api import RepoInfo


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def mod():
    import importlib

    mod_name = "get_workflow_run"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _run_payload():
    return {
        "id": 42,
        "name": "CI",
        "status": "in_progress",
        "conclusion": None,
        "head_branch": "main",
        "head_sha": "abc",
        "event": "push",
        "html_url": "https://example.com",
    }


def _jobs_payload(failed_step=False):
    steps = [{"name": "build", "conclusion": "failure"}] if failed_step else []
    return {
        "jobs": [
            {
                "id": 1,
                "name": "test",
                "status": "completed",
                "conclusion": "failure" if failed_step else "success",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z",
                "steps": steps,
            }
        ]
    }


def _pending(environment="production"):
    return [{"environment": {"name": environment}, "current_user_can_approve": False}]


def _fake_run(run=None, jobs=None, pending=None, run_err=""):
    run = _run_payload() if run is None else run
    jobs = _jobs_payload() if jobs is None else jobs
    pending = [] if pending is None else pending

    def fake_run(cmd, **kwargs):
        endpoint = cmd[-1]
        if run_err and endpoint.endswith("/42"):
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": run_err})()
        if "/jobs" in endpoint:
            return type("R", (), {"returncode": 0, "stdout": json.dumps(jobs), "stderr": ""})()
        if "pending_deployments" in endpoint:
            return type("R", (), {"returncode": 0, "stdout": json.dumps(pending), "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": json.dumps(run), "stderr": ""})()

    return fake_run


def _exec(mod, argv, **kwargs):
    with (
        patch.object(mod, "assert_gh_authenticated"),
        patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
        patch("subprocess.run", side_effect=_fake_run(**kwargs)),
    ):
        return mod.main(argv)


class TestMain:
    def test_happy_path(self, mod, capsys):
        rc = _exec(mod, ["--run-id", "42"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["run_id"] == 42
        assert len(result["Data"]["jobs"]) == 1

    def test_pending_deployment_flagged(self, mod, capsys):
        rc = _exec(mod, ["--run-id", "42"], pending=_pending())
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["waiting_on_environment_approval"] is True

    def test_no_pending_means_false(self, mod, capsys):
        rc = _exec(mod, ["--run-id", "42"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["waiting_on_environment_approval"] is False

    def test_run_not_found_exit_2(self, mod):
        rc = _exec(mod, ["--run-id", "42"], run_err="404 Not Found")
        assert rc == 2

    def test_failed_steps_surface(self, mod, capsys):
        rc = _exec(mod, ["--run-id", "42"], jobs=_jobs_payload(failed_step=True))
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        job = result["Data"]["jobs"][0]
        assert job["conclusion"] == "failure"
        assert job["failed_steps"][0]["name"] == "build"
