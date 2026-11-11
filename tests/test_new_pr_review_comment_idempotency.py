"""Tests for new_pr_review_comment.py idempotency: a retried post must not duplicate."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.test_new_pr_review_comment import (
    BASE_ARGS,
    HEAD_SHA,
    _completed,
    _created,
    _envelope,
    build_parser,
    main,
)


@pytest.fixture
def repo_ready_real_check():
    """Repo ready; the duplicate check runs for real against mocked gh calls."""
    with (
        patch("new_pr_review_comment.assert_gh_authenticated"),
        patch(
            "new_pr_review_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Tests: idempotency (a retried post must not duplicate)
# ---------------------------------------------------------------------------

_ME = "rjmurillo-bot"
_LISTING = "repos/o/r/pulls/123/comments"


def _review_comment(cid, body="Please rename this.", login=_ME, **overrides):
    comment = {
        "id": cid,
        "body": body,
        "user": {"login": login},
        "path": "src/app.py",
        "line": 47,
        "original_line": 47,
        "side": "RIGHT",
        "in_reply_to_id": None,
        "html_url": f"https://github.com/o/r/pull/123#discussion_r{cid}",
    }
    comment.update(overrides)
    return comment


class _FakeGh:
    """Route `gh api` calls by argv so each test names the reads it expects."""

    def __init__(self, pages=None, login=_ME, login_rc=0, list_result=None):
        self.pages = pages if pages is not None else [[]]
        self.login = login
        self.login_rc = login_rc
        self.list_result = list_result
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if "--slurp" in argv:
            return self.list_result or _completed(stdout=json.dumps(self.pages))
        if argv[2:3] == ["user"]:
            return _completed(stdout=f"{self.login}\n", rc=self.login_rc, stderr="denied")
        if "-X" in argv:
            return _created(500)
        return _completed(stdout=f"{HEAD_SHA}\n")

    @property
    def posted(self):
        return [c for c in self.calls if "-X" in c]

    @property
    def user_lookups(self):
        return [c for c in self.calls if c[2:3] == ["user"]]


def _run(fake, argv=BASE_ARGS):
    with patch("new_pr_review_comment.subprocess.run", side_effect=fake):
        return main(argv)


class TestIdempotentPost:
    def test_duplicate_is_skipped(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41)]])

        assert _run(fake) == 0

        data = _envelope(capsys)["Data"]
        assert data["action"] == "SKIP"
        assert data["reason"] == "duplicate"
        assert data["comment_id"] == 41
        assert data["html_url"].endswith("discussion_r41")
        assert fake.posted == []

    def test_non_duplicate_is_posted(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41, body="Another note")]])

        assert _run(fake) == 0

        assert _envelope(capsys)["Data"]["comment_id"] == 500
        assert len(fake.posted) == 1
        assert fake.user_lookups == []

    def test_same_body_from_another_author_is_posted(self, repo_ready_real_check):
        fake = _FakeGh(pages=[[_review_comment(41, login="someone-else")]])

        assert _run(fake) == 0

        assert len(fake.posted) == 1
        assert len(fake.user_lookups) == 1

    @pytest.mark.parametrize(
        "overrides",
        [
            {"path": "src/other.py"},
            {"line": 48, "original_line": 48},
            {"side": "LEFT"},
            {"in_reply_to_id": 7},
        ],
        ids=["other-path", "other-line", "other-side", "reply-not-root"],
    )
    def test_same_body_elsewhere_is_posted(self, repo_ready_real_check, overrides):
        fake = _FakeGh(pages=[[_review_comment(41, **overrides)]])

        assert _run(fake) == 0

        assert len(fake.posted) == 1

    def test_outdated_comment_matches_on_original_line(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41, line=None, original_line=47)]])

        _run(fake)

        assert _envelope(capsys)["Data"]["action"] == "SKIP"

    def test_duplicate_on_a_later_page_is_found(self, repo_ready_real_check, capsys):
        fake = _FakeGh(
            pages=[
                [_review_comment(1, body="a")],
                [_review_comment(2, body="b")],
                [_review_comment(3)],
            ]
        )

        _run(fake)

        assert _envelope(capsys)["Data"]["comment_id"] == 3
        listing = [c for c in fake.calls if "--slurp" in c][0]
        assert "--paginate" in listing
        assert listing[-1] == f"{_LISTING}?per_page=100"

    def test_body_compare_ignores_crlf(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41, body="one\ntwo")]])
        argv = [*BASE_ARGS[:-1], "one\r\ntwo\n"]

        _run(fake, argv)

        assert _envelope(capsys)["Data"]["action"] == "SKIP"

    def test_listing_failure_exits_3_and_posts_nothing(self, repo_ready_real_check, capsys):
        fake = _FakeGh(list_result=_completed(rc=1, stderr="gh: Bad Gateway (HTTP 502)"))

        assert _run(fake) == 3

        err = _envelope(capsys)["Error"]
        assert "Nothing was posted" in err["Message"]
        assert "to check for a duplicate" in err["Message"]
        assert fake.posted == []

    def test_listing_404_exits_2(self, repo_ready_real_check, capsys):
        fake = _FakeGh(list_result=_completed(rc=1, stderr="gh: Not Found (HTTP 404)"))

        assert _run(fake) == 2

        assert _envelope(capsys)["Error"]["Type"] == "NotFound"
        assert fake.posted == []

    def test_unreadable_listing_exits_3(self, repo_ready_real_check):
        fake = _FakeGh(list_result=_completed(stdout='{"message": "oops"}'))

        assert _run(fake) == 3
        assert fake.posted == []

    def test_listing_timeout_exits_3(self, repo_ready_real_check, capsys):
        def _router(argv, **kwargs):
            if "--slurp" in argv:
                raise subprocess.TimeoutExpired(cmd=argv, timeout=120)
            return _completed(stdout=f"{HEAD_SHA}\n")

        assert _run(_router) == 3
        assert _envelope(capsys)["Error"]["Type"] == "Timeout"

    def test_user_lookup_failure_exits_3_and_posts_nothing(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41)]], login_rc=1, login="")

        assert _run(fake) == 3

        assert "authenticated user" in _envelope(capsys)["Error"]["Message"]
        assert fake.posted == []

    def test_empty_login_exits_3(self, repo_ready_real_check):
        fake = _FakeGh(pages=[[_review_comment(41)]], login="")

        assert _run(fake) == 3
        assert fake.posted == []

    def test_dry_run_reports_would_skip_for_a_duplicate(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41)]])

        assert _run(fake, [*BASE_ARGS, "--dry-run"]) == 0

        data = _envelope(capsys)["Data"]
        assert (data["action"], data["reason"], data["dryRun"]) == ("would_skip", "duplicate", True)
        assert fake.posted == []

    def test_dry_run_reports_would_post_when_not_a_duplicate(self, repo_ready_real_check, capsys):
        fake = _FakeGh(pages=[[_review_comment(41, body="other")]])

        assert _run(fake, [*BASE_ARGS, "--dry-run"]) == 0

        data = _envelope(capsys)["Data"]
        assert (data["action"], data["dryRun"]) == ("would_post", True)
        assert fake.posted == []

    def test_help_documents_skip_and_exit_codes(self, capsys):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--help"])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "examples:" in out
        assert "SKIP" in out
        assert "exit codes:" in out
