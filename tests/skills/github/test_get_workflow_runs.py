"""Tests for actions/get_workflow_runs.py."""

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

    mod_name = "get_workflow_runs"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _run_payload(n=2):
    return {
        "total_count": n,
        "workflow_runs": [
            {
                "id": 1000 + i,
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "abc",
                "event": "push",
                "created_at": "2026-01-01T00:00:00Z",
                "html_url": "https://example.com",
                "pull_requests": [],
            }
            for i in range(n)
        ],
    }


def _fake_run(payload, err=""):
    def fake_run(cmd, **kwargs):
        if err:
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": err})()
        return type("R", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    return fake_run


def _run(mod, argv, payload=None, err=""):
    payload = _run_payload() if payload is None else payload
    with (
        patch.object(mod, "assert_gh_authenticated"),
        patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
        patch("subprocess.run", side_effect=_fake_run(payload, err)),
    ):
        return mod.main(argv)


class TestNormalizeRun:
    def test_shape(self, mod):
        out = mod.normalize_run(_run_payload(1)["workflow_runs"][0])
        assert out["id"] == 1000
        assert out["conclusion"] == "success"


class TestMain:
    def test_happy_path_lists_runs(self, mod, capsys):
        rc = _run(mod, [])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert len(result["Data"]["runs"]) == 2

    def test_invalid_status_exit_2(self, mod):
        rc = _run(mod, ["--status", "bogus"])
        assert rc == 2

    def test_zero_limit_rejected(self, mod):
        rc = _run(mod, ["--limit", "0"])
        assert rc == 2

    def test_pull_request_filter_client_side(self, mod, capsys):
        payload = _run_payload(2)
        payload["workflow_runs"][0]["pull_requests"] = [{"number": 7}]
        rc = _run(mod, ["--pull-request", "7"], payload=payload)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert len(result["Data"]["runs"]) == 1
        assert result["Data"]["runs"][0]["id"] == 1000

    def test_api_error_exit_3(self, mod):
        rc = _run(mod, [], err="connection reset")
        assert rc == 3


class TestEncodingAndPrFilter:
    def test_branch_filter_is_url_encoded(self, mod):
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(" ".join(cmd))
            payload = {"total_count": 0, "workflow_runs": []}
            return type("R", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--branch", "feature/x&y"])
        assert "branch=feature%2Fx%26y" in captured[0]

    def test_pr_filter_scans_beyond_limit(self, mod, capsys):
        # 20 non-matching runs fill the default page; the matching run is 21st.
        runs = [
            {
                "id": i,
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "abc",
                "event": "push",
                "created_at": "2026-01-01T00:00:00Z",
                "html_url": "https://example.com",
                "pull_requests": [],
            }
            for i in range(20)
        ]
        match = dict(runs[0])
        match["id"] = 9999
        match["pull_requests"] = [{"number": 7, "head": {"ref": "b"}}]
        payload = {"total_count": 21, "workflow_runs": runs + [match]}

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=_fake_run(payload)),
        ):
            rc = mod.main(["--pull-request", "7"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        ids = [r["id"] for r in result["Data"]["runs"]]
        assert ids == [9999]
