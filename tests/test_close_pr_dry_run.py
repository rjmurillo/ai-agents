"""Dry-run and closing-comment dedupe tests for close_pr.py."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.test_close_pr import _completed, main

pytestmark = pytest.mark.usefixtures("stub_git_probes", "tmp_path_is_temp_root")


_GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
_GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"


@pytest.mark.parametrize(
    ("stdout", "stderr", "code"),
    [
        pytest.param("", _GH_MISSING_PR, 2, id="gh-missing-pr"),
        pytest.param(_GH_MISSING_PR, "", 2, id="marker-on-stdout-fallback"),
        pytest.param("", "not found", 2, id="legacy-wording"),
        pytest.param("", "gh: Not Found (HTTP 404)", 2, id="legacy-any-case"),
        pytest.param("", "HTTP 502: Bad Gateway", 3, id="external-error"),
        pytest.param("", _GH_MISSING_REPO, 3, id="missing-repo"),
    ],
)
def test_failed_pr_view_exit_code(stdout, stderr, code):
    """A failed PR lookup maps to the ADR-035 code and never closes the PR."""
    with (
        patch("close_pr.assert_gh_authenticated"),
        patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
        patch(
            "subprocess.run",
            return_value=_completed(rc=1, stdout=stdout, stderr=stderr),
        ) as run,
    ):
        with pytest.raises(SystemExit) as exc:
            main(["--pull-request", "999999"])
    assert exc.value.code == code
    assert all(call.args[0][:3] != ["gh", "pr", "close"] for call in run.call_args_list)


def _run_dry(argv, responses):
    with (
        patch("close_pr.assert_gh_authenticated"),
        patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
        patch("subprocess.run", side_effect=responses) as run,
    ):
        rc = main(argv)
    return rc, run


class TestDryRun:
    def test_open_pr_reports_would_close_and_makes_no_write_call(self, capsys):
        rc, run = _run_dry(
            ["--pull-request", "5", "--comment", "superseded", "--dry-run"],
            [
                _completed(stdout=json.dumps({"state": "OPEN"})),
                _completed(stdout="[[]]"),
            ],
        )

        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["action"] == "would_close"
        assert data["dryRun"] is True
        assert data["wouldComment"] is True
        assert data["commentDuplicate"] is False
        assert run.call_count == 2

    def test_open_pr_dry_run_detects_duplicate_closing_comment(self, capsys):
        existing_pages = json.dumps([[{"id": 901, "body": "superseded", "user": {"login": "bot"}}]])
        rc, run = _run_dry(
            ["--pull-request", "5", "--comment", "superseded", "--dry-run"],
            [
                _completed(stdout=json.dumps({"state": "OPEN"})),
                _completed(stdout=existing_pages),
                _completed(stdout="bot\n"),
            ],
        )

        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["action"] == "would_close"
        assert data["dryRun"] is True
        assert data["wouldComment"] is False
        assert data["commentDuplicate"] is True
        assert data["existingCommentId"] == 901
        assert run.call_count == 3

    def test_closed_pr_reports_the_same_noop_action_with_the_marker(self, capsys):
        rc, run = _run_dry(
            ["--pull-request", "5", "--dry-run"],
            [_completed(stdout=json.dumps({"state": "CLOSED"}))],
        )

        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["action"] == "none"
        assert data["dryRun"] is True
        assert run.call_count == 1

    def test_dry_run_without_comment_never_would_comment(self, capsys):
        rc, _ = _run_dry(
            ["--pull-request", "5", "--dry-run"],
            [_completed(stdout=json.dumps({"state": "OPEN"}))],
        )

        assert rc == 0
        assert json.loads(capsys.readouterr().out)["wouldComment"] is False

    def test_dry_run_still_fails_when_the_pr_is_missing(self):
        with pytest.raises(SystemExit) as exc:
            _run_dry(
                ["--pull-request", "5", "--dry-run"],
                [_completed(rc=1, stderr="Could not resolve to a PullRequest")],
            )

        assert exc.value.code == 2

    def test_default_run_has_no_dry_run_key(self, capsys):
        rc, _ = _run_dry(
            ["--pull-request", "5"],
            [_completed(stdout=json.dumps({"state": "OPEN"})), _completed()],
        )

        assert rc == 0
        assert "dryRun" not in json.loads(capsys.readouterr().out)


class TestClosingCommentDedupe:
    """Retry after a close failure must skip re-posting an identical closing comment."""

    def test_skips_duplicate_comment_by_same_author_and_closes_pr(self, capsys):
        existing_pages = json.dumps(
            [[{"id": 777, "body": "Superseded by #6\n", "user": {"login": "BotUser"}}]]
        )
        replies = [
            _completed(stdout=json.dumps({"state": "OPEN"})),
            _completed(stdout=existing_pages),
            _completed(stdout="botuser\n"),
            _completed(rc=0),
        ]
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", side_effect=replies) as run,
        ):
            rc = main(["--pull-request", "5", "--comment", "Superseded by #6\r\n"])

        assert rc == 0
        subcommands = [c.args[0][1:3] for c in run.call_args_list]
        assert ["pr", "comment"] not in subcommands
        assert subcommands[-1] == ["pr", "close"]
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "closed"
        assert out["commentPosted"] is False
        assert out["commentSkipped"] is True
        assert out["existingCommentId"] == 777

    def test_posts_comment_when_matching_body_belongs_to_another_author(self, capsys):
        existing_pages = json.dumps(
            [[{"id": 777, "body": "Superseded by #6", "user": {"login": "other-user"}}]]
        )
        replies = [
            _completed(stdout=json.dumps({"state": "OPEN"})),
            _completed(stdout=existing_pages),
            _completed(stdout="botuser\n"),
            _completed(rc=0),
            _completed(rc=0),
        ]
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", side_effect=replies) as run,
        ):
            rc = main(["--pull-request", "5", "--comment", "Superseded by #6"])

        assert rc == 0
        subcommands = [c.args[0][1:3] for c in run.call_args_list]
        assert ["pr", "comment"] in subcommands
        assert subcommands[-1] == ["pr", "close"]
        out = json.loads(capsys.readouterr().out)
        assert out["commentPosted"] is True
        assert out["commentSkipped"] is False

    @pytest.mark.parametrize(
        "lookup_reply",
        [
            _completed(rc=1, stderr="HTTP 502 Bad Gateway"),
            _completed(rc=0, stdout="not-json"),
            _completed(rc=0, stdout='{"not": "pages"}'),
        ],
    )
    def test_comment_lookup_failure_fails_closed_with_exit_3(self, lookup_reply, capsys):
        replies = [
            _completed(stdout=json.dumps({"state": "OPEN"})),
            lookup_reply,
        ]
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", side_effect=replies) as run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "5", "--comment", "Superseded by #6"])

        assert exc.value.code == 3
        subcommands = [c.args[0][1:3] for c in run.call_args_list]
        assert ["pr", "comment"] not in subcommands
        assert ["pr", "close"] not in subcommands
        assert "NOT closed" in capsys.readouterr().err


_DENIED = "gh: Resource not accessible by integration (HTTP 403)"


def _run_close(argv, replies):
    with (
        patch("close_pr.assert_gh_authenticated"),
        patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
        patch("subprocess.run", side_effect=replies) as run,
    ):
        rc = main(argv)
    return rc, [c.args[0][1:3] for c in run.call_args_list]


class TestInstallationTokenRetry:
    """An Actions installation token cannot call GET /user; the retry must still close."""

    def test_denied_user_lookup_skips_identical_bot_comment_and_closes(self, capsys):
        pages = json.dumps(
            [
                [
                    {
                        "id": 5,
                        "body": "Superseded",
                        "user": {"login": "github-actions[bot]", "type": "Bot"},
                    }
                ]
            ]
        )
        rc, subcommands = _run_close(
            ["--pull-request", "5", "--comment", "Superseded"],
            [
                _completed(stdout=json.dumps({"state": "OPEN"})),
                _completed(stdout=pages),
                _completed(rc=1, stderr=_DENIED),
                _completed(rc=0),
            ],
        )
        assert rc == 0
        assert ["pr", "comment"] not in subcommands
        assert subcommands[-1] == ["pr", "close"]
        out = json.loads(capsys.readouterr().out)
        assert out["commentSkipped"] is True
        assert out["existingCommentId"] == 5

    def test_denied_user_lookup_posts_when_identical_body_is_from_a_human(self, capsys):
        pages = json.dumps(
            [[{"id": 5, "body": "Superseded", "user": {"login": "alice", "type": "User"}}]]
        )
        rc, subcommands = _run_close(
            ["--pull-request", "5", "--comment", "Superseded"],
            [
                _completed(stdout=json.dumps({"state": "OPEN"})),
                _completed(stdout=pages),
                _completed(rc=1, stderr=_DENIED),
                _completed(rc=0),
                _completed(rc=0),
            ],
        )
        assert rc == 0
        assert ["pr", "comment"] in subcommands
        assert subcommands[-1] == ["pr", "close"]
        assert json.loads(capsys.readouterr().out)["commentPosted"] is True

    def test_denied_user_lookup_with_no_matching_body_posts_and_closes(self):
        rc, subcommands = _run_close(
            ["--pull-request", "5", "--comment", "Superseded"],
            [
                _completed(stdout=json.dumps({"state": "OPEN"})),
                _completed(stdout="[[]]"),
                _completed(rc=0),
                _completed(rc=0),
            ],
        )
        assert rc == 0
        assert subcommands[-2:] == [["pr", "comment"], ["pr", "close"]]

    def test_other_user_lookup_failure_still_fails_closed(self, capsys):
        pages = json.dumps(
            [[{"id": 5, "body": "Superseded", "user": {"login": "x[bot]", "type": "Bot"}}]]
        )
        with pytest.raises(SystemExit) as exc:
            _run_close(
                ["--pull-request", "5", "--comment", "Superseded"],
                [
                    _completed(stdout=json.dumps({"state": "OPEN"})),
                    _completed(stdout=pages),
                    _completed(rc=1, stderr="HTTP 502 Bad Gateway"),
                ],
            )
        assert exc.value.code == 3
        assert "NOT closed" in capsys.readouterr().err
