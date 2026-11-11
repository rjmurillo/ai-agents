"""Tests for post_pr_comment_reply.py idempotency: a retried post must not duplicate."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.test_post_pr_comment_reply import _completed, build_parser, main

# ---------------------------------------------------------------------------
# Tests: idempotency (a retried post must not duplicate)
# ---------------------------------------------------------------------------

_ME = "rjmurillo-bot"


def _comment(cid, body, login=_ME, in_reply_to=None, url=None):
    return {
        "id": cid,
        "body": body,
        "user": {"login": login},
        "in_reply_to_id": in_reply_to,
        "html_url": url or f"https://example.com/c/{cid}",
    }


class _FakeGh:
    """Route `gh api` calls by argv so each test names the reads it expects.

    ``pages`` maps an endpoint to the slurped pages the paginated read returns.
    """

    def __init__(self, pages=None, login=_ME, login_rc=0, list_result=None, post_id=900):
        self.pages = pages or {}
        self.login = login
        self.login_rc = login_rc
        self.list_result = list_result
        self.post_id = post_id
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if "--slurp" in argv:
            if self.list_result is not None:
                return self.list_result
            endpoint = argv[-1].split("?")[0]
            return _completed(stdout=json.dumps(self.pages.get(endpoint, [[]])))
        if argv[2:3] == ["user"]:
            return _completed(stdout=f"{self.login}\n", rc=self.login_rc, stderr="denied")
        if "-X" in argv:
            body = {"id": self.post_id, "html_url": "https://example.com/new", "created_at": "t"}
            return _completed(stdout=json.dumps(body))
        return _completed(stdout=json.dumps({"pull_request_url": "x/pulls/5"}))

    @property
    def posted(self):
        return [c for c in self.calls if "-X" in c]

    @property
    def user_lookups(self):
        return [c for c in self.calls if c[2:3] == ["user"]]


def _run_main(fake, argv):
    with (
        patch("post_pr_comment_reply.assert_gh_authenticated"),
        patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ),
        patch("subprocess.run", side_effect=fake),
    ):
        return main(argv)


_ISSUE = "repos/o/r/issues/5/comments"
_REVIEW = "repos/o/r/pulls/5/comments"
_TOP = ["--pull-request", "5", "--body", "Fixed in abc1234"]
_THREAD = ["--pull-request", "5", "--comment-id", "10", "--body", "Fixed in abc1234"]


class TestIdempotentPost:
    def test_top_level_duplicate_is_skipped(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "Fixed in abc1234")]]})

        rc = _run_main(fake, _TOP)

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["action"] == "SKIP"
        assert out["reason"] == "duplicate"
        assert out["comment_id"] == 41
        assert out["html_url"] == "https://example.com/c/41"
        assert fake.posted == []

    def test_top_level_non_duplicate_is_posted(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "Something else")]]})

        rc = _run_main(fake, _TOP)

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["comment_id"] == 900
        assert "action" not in out
        assert len(fake.posted) == 1

    def test_same_body_from_another_author_is_posted(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "Fixed in abc1234", login="someone-else")]]})

        rc = _run_main(fake, _TOP)

        assert rc == 0
        assert len(fake.posted) == 1
        assert len(fake.user_lookups) == 1

    def test_no_user_lookup_when_no_body_matches(self):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "unrelated")]]})

        _run_main(fake, _TOP)

        assert fake.user_lookups == []

    def test_login_comparison_ignores_case(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "Fixed in abc1234", login="RJMurillo-Bot")]]})

        _run_main(fake, _TOP)

        assert json.loads(capsys.readouterr().out)["action"] == "SKIP"

    def test_body_compare_ignores_crlf_and_edge_whitespace(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "line one\nline two")]]})

        _run_main(fake, ["--pull-request", "5", "--body", "line one\r\nline two\n"])

        assert json.loads(capsys.readouterr().out)["action"] == "SKIP"

    def test_duplicate_on_a_later_page_is_found(self, capsys):
        fake = _FakeGh(
            pages={
                _ISSUE: [[_comment(1, "a")], [_comment(2, "b")], [_comment(3, "Fixed in abc1234")]]
            }
        )

        _run_main(fake, _TOP)

        assert json.loads(capsys.readouterr().out)["comment_id"] == 3
        listing = [c for c in fake.calls if "--slurp" in c][0]
        assert "--paginate" in listing
        assert listing[-1].endswith("?per_page=100")

    def test_thread_duplicate_is_skipped(self, capsys):
        fake = _FakeGh(
            pages={
                _REVIEW: [
                    [
                        _comment(10, "Please fix", login="reviewer"),
                        _comment(77, "Fixed in abc1234", in_reply_to=10),
                    ]
                ]
            }
        )

        rc = _run_main(fake, _THREAD)

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert (out["action"], out["reason"], out["comment_id"]) == ("SKIP", "duplicate", 77)
        assert out["in_reply_to"] == 10
        assert fake.posted == []

    def test_reply_to_a_reply_checks_the_whole_thread(self, capsys):
        fake = _FakeGh(
            pages={
                _REVIEW: [
                    [
                        _comment(10, "Please fix", login="reviewer"),
                        _comment(77, "Fixed in abc1234", in_reply_to=10),
                        _comment(78, "Thanks", login="reviewer", in_reply_to=10),
                    ]
                ]
            }
        )

        _run_main(fake, ["--pull-request", "5", "--comment-id", "78", "--body", "Fixed in abc1234"])

        assert json.loads(capsys.readouterr().out)["comment_id"] == 77
        assert fake.posted == []

    def test_same_body_in_another_thread_is_posted(self, capsys):
        fake = _FakeGh(
            pages={
                _REVIEW: [
                    [
                        _comment(10, "Please fix", login="reviewer"),
                        _comment(20, "Other thread", login="reviewer"),
                        _comment(88, "Fixed in abc1234", in_reply_to=20),
                    ]
                ]
            }
        )

        rc = _run_main(fake, _THREAD)

        assert rc == 0
        assert len(fake.posted) == 1
        assert fake.posted[0][2] == "repos/o/r/pulls/5/comments/10/replies"

    def test_unknown_comment_id_exits_2(self, capsys):
        fake = _FakeGh(pages={_REVIEW: [[_comment(20, "x", login="reviewer")]]})

        with pytest.raises(SystemExit) as exc:
            _run_main(fake, _THREAD)

        assert exc.value.code == 2
        assert fake.posted == []
        assert "Comment 10 not found on o/r#5" in capsys.readouterr().err

    def test_listing_404_exits_2(self, capsys):
        fake = _FakeGh(list_result=_completed(rc=1, stderr="gh: Not Found (HTTP 404)"))

        with pytest.raises(SystemExit) as exc:
            _run_main(fake, _TOP)

        assert exc.value.code == 2
        assert fake.posted == []

    def test_listing_failure_exits_3_and_posts_nothing(self, capsys):
        fake = _FakeGh(list_result=_completed(rc=1, stderr="HTTP 502 page 2"))

        with pytest.raises(SystemExit) as exc:
            _run_main(fake, _TOP)

        assert exc.value.code == 3
        assert fake.posted == []
        err = capsys.readouterr().err
        assert "HTTP 502 page 2" in err
        assert "Nothing was posted" in err

    def test_unreadable_listing_exits_3_and_posts_nothing(self):
        fake = _FakeGh(list_result=_completed(stdout='{"message": "oops"}'))

        with pytest.raises(SystemExit) as exc:
            _run_main(fake, _TOP)

        assert exc.value.code == 3
        assert fake.posted == []

    def test_listing_timeout_exits_3_and_posts_nothing(self):
        def _timeout(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=120)

        with pytest.raises(SystemExit) as exc:
            _run_main(_timeout, _TOP)

        assert exc.value.code == 3

    def test_user_lookup_failure_exits_3_and_posts_nothing(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "Fixed in abc1234")]]}, login_rc=1, login="")

        with pytest.raises(SystemExit) as exc:
            _run_main(fake, _TOP)

        assert exc.value.code == 3
        assert fake.posted == []
        assert "authenticated user" in capsys.readouterr().err

    def test_user_lookup_timeout_exits_3(self):
        base = _FakeGh(pages={_ISSUE: [[_comment(41, "Fixed in abc1234")]]})

        def _router(argv, **kwargs):
            if argv[2:3] == ["user"]:
                raise subprocess.TimeoutExpired(cmd=argv, timeout=30)
            return base(argv, **kwargs)

        with pytest.raises(SystemExit) as exc:
            _run_main(_router, _TOP)

        assert exc.value.code == 3

    def test_dry_run_reports_would_skip_for_a_duplicate(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "Fixed in abc1234")]]})

        rc = _run_main(fake, [*_TOP, "--dry-run"])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert (out["action"], out["reason"], out["dryRun"]) == ("would_skip", "duplicate", True)
        assert out["comment_id"] == 41
        assert fake.posted == []

    def test_dry_run_reports_would_post_when_not_a_duplicate(self, capsys):
        fake = _FakeGh(pages={_ISSUE: [[_comment(41, "unrelated")]]})

        rc = _run_main(fake, [*_TOP, "--dry-run"])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert (out["action"], out["dryRun"]) == ("would_post", True)
        assert fake.posted == []

    def test_help_documents_skip_and_exit_codes(self, capsys):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--help"])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "examples:" in out
        assert "SKIP" in out
        assert "duplicate" in out
        assert "exit codes:" in out
