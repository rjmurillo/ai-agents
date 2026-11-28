"""Tests for dismiss_pr_review.py."""

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

    mod_name = "dismiss_pr_review"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _review(state="CHANGES_REQUESTED", commit="oldsha"):
    return {
        "id": 100,
        "state": state,
        "commit_id": commit,
        "user": {"login": "coderabbitai[bot]"},
    }


def _graphql_threads(unresolved=0, head="newsha"):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": head,
                    "reviewThreads": {
                        "nodes": [{"isResolved": False}] * unresolved,
                        "pageInfo": {"hasNextPage": False},
                    },
                }
            }
        }
    }


def _make_run(review, gql, fail_dismiss=False, record=None):
    def fake_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "dismissals" in joined:
            if record is not None:
                record.append(cmd)
            if fail_dismiss:
                return type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
            return type(
                "R", (), {"returncode": 0, "stdout": json.dumps({"id": 100}), "stderr": ""}
            )()
        if "reviews/100" in joined:
            return type("R", (), {"returncode": 0, "stdout": json.dumps(review), "stderr": ""})()
        if joined.endswith("--jq .head.sha") or ".head.sha" in joined:
            return type("R", (), {"returncode": 0, "stdout": "newsha\n", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": json.dumps(gql), "stderr": ""})()

    return fake_run


def _run(mod, argv, review=None, gql=None, fail_dismiss=False, record=None):
    review = _review() if review is None else review
    gql = _graphql_threads() if gql is None else gql
    with (
        patch.object(mod, "assert_gh_authenticated"),
        patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
        patch.object(
            mod.subprocess, "run", side_effect=_make_run(review, gql, fail_dismiss, record)
        ),
    ):
        return mod.main(argv)


_ARGV = ["--pull-request", "7", "--review-id", "100", "--message", "stale"]


class TestDismissPrReview:
    def test_happy_path_dismisses(self, mod, capsys):
        rc = _run(mod, _ARGV)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["action"] == "dismissed"
        assert result["Data"]["review_on_current_head"] is False

    def test_wrong_state_refuses(self, mod, capsys):
        rc = _run(mod, _ARGV, review=_review(state="APPROVED"))
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is False

    def test_already_dismissed_is_noop_success(self, mod, capsys):
        rc = _run(mod, _ARGV, review=_review(state="DISMISSED"))
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["action"] == "no-op"

    def test_unresolved_threads_refuse(self, mod, capsys):
        rc = _run(mod, _ARGV, gql=_graphql_threads(unresolved=2))
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert (
            "unresolved" in json.dumps(result["Error"]).lower()
            or "unresolved" in str(result).lower()
        )

    def test_dry_run_makes_no_write(self, mod, capsys):
        record = []
        rc = _run(mod, [*_ARGV, "--dry-run"], record=record)
        assert rc == 0
        assert record == []
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["action"] == "dry-run"

    def test_blank_message_rejected_exit_2(self, mod, capsys):
        rc = _run(mod, ["--pull-request", "7", "--review-id", "100", "--message", "  "])
        assert rc == 2

    def test_skip_thread_check_proceeds_and_audits(self, mod, capsys):
        rc = _run(mod, [*_ARGV, "--skip-thread-check"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["audit"]["thread_check"] == "skipped"

    def test_dismiss_api_failure_exit_3(self, mod, capsys):
        rc = _run(mod, _ARGV, fail_dismiss=True)
        assert rc == 3

    def test_review_not_found_exit_3(self, mod, capsys):
        def fake_run(cmd, **kwargs):
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": "404 Not Found"})()

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=fake_run),
        ):
            rc = mod.main(_ARGV)
        assert rc == 3
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["Error"]["Type"] == "NotFound"
        assert envelope["Error"]["Code"] == 3

    def test_review_fetch_server_error_is_api_error_not_not_found(self, mod, capsys):
        def fake_run(cmd, **kwargs):
            return type(
                "R", (), {"returncode": 1, "stdout": "", "stderr": "HTTP 502 Bad Gateway"}
            )()

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=fake_run),
        ):
            rc = mod.main(_ARGV)
        assert rc == 3
        assert json.loads(capsys.readouterr().out)["Error"]["Type"] == "ApiError"


class TestNullPullRequest:
    def test_null_pull_request_reports_not_found_not_decode_failure(self, mod, capsys):
        gql = {"data": {"repository": {"pullRequest": None}}}
        rc = _run(mod, _ARGV, gql=gql)
        assert rc == 3
        err = capsys.readouterr().out
        assert "not found" in err
        assert "decode" not in err.lower()

    def test_timeout_in_thread_gate_is_exit_3_not_crash(self, mod, capsys):
        import subprocess as sp

        review = _review()

        def fake_run(cmd, **kwargs):
            joined = " ".join(cmd)
            if "reviews/100" in joined:
                out = {"returncode": 0, "stdout": json.dumps(review), "stderr": ""}
                return type("R", (), out)()
            if "graphql" in joined:
                raise sp.TimeoutExpired(cmd=["gh"], timeout=60)
            return type("R", (), {"returncode": 0, "stdout": "newsha\n", "stderr": ""})()

        with (
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=_mock_repo()),
            patch.object(mod.subprocess, "run", side_effect=fake_run),
        ):
            rc = mod.main(_ARGV)
        assert rc == 3
        assert "timed out" in capsys.readouterr().out
