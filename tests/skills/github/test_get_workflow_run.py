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


def _pending(environment="production", reviewers=True):
    entry = {"environment": {"name": environment}, "current_user_can_approve": False}
    if reviewers:
        entry["reviewers"] = [{"type": "User", "reviewer": {"login": "octocat"}}]
    return [entry]


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

    def test_timer_only_wait_is_not_an_approval_wait(self, mod, capsys):
        rc = _exec(mod, ["--run-id", "42"], pending=_pending(reviewers=False))
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["waiting_on_environment_approval"] is False
        assert len(result["Data"]["pending_deployments"]) == 1

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


class TestJobsReadFailure:
    def test_failed_jobs_fetch_is_warning_not_pass(self, mod, capsys):
        run_payload = {"id": 5, "status": "completed", "conclusion": "success", "name": "CI"}

        def fake_get(path):
            if path.endswith("/jobs?per_page=100"):
                return None, "403 forbidden"
            if "pending_deployments" in path:
                return [], ""
            return run_payload, ""

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch.object(mod, "gh_api_get", side_effect=fake_get),
        ):
            rc = mod.main(["--run-id", "5"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["jobs_read"] is False
        assert result["Data"]["jobs_error"]
        assert result["Data"]["jobs"] == []

    def test_jobs_read_is_bool_and_capped_is_separate(self, mod, capsys):
        run_payload = {"id": 5, "status": "completed", "conclusion": "success", "name": "CI"}
        jobs = {"jobs": [{"id": i, "name": f"j{i}", "steps": []} for i in range(100)]}

        def fake_get(path):
            if path.endswith("/jobs?per_page=100"):
                return jobs, ""
            if "pending_deployments" in path:
                return [], ""
            return run_payload, ""

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch.object(mod, "gh_api_get", side_effect=fake_get),
        ):
            rc = mod.main(["--run-id", "5"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["jobs_read"] is True
        assert result["Data"]["jobs_capped"] is True
