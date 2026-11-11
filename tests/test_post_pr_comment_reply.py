"""Tests for post_pr_comment_reply.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("post_pr_comment_reply")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@pytest.fixture
def no_prior_comment():
    """Stub the duplicate check so tests of the post path see one gh call per step.

    TestIdempotentPost exercises the real check with the I/O mocked.
    """
    with patch("post_pr_comment_reply._find_duplicate", return_value=None):
        yield


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--body", "test"])

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                [
                    "--pull-request",
                    "1",
                    "--body",
                    "text",
                    "--body-file",
                    "f.md",
                ]
            )

    def test_valid_inline_body(self):
        args = build_parser().parse_args(
            [
                "--pull-request",
                "50",
                "--comment-id",
                "123",
                "--body",
                "Fixed.",
            ]
        )
        assert args.pull_request == 50
        assert args.comment_id == 123
        assert args.body == "Fixed."


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_prior_comment")
class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", "test"])
            assert exc.value.code == 4

    def test_empty_body_exits_1(self):
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", ""])
            assert exc.value.code == 2

    def test_body_file_not_found_exits_2(self):
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body-file", "/nonexistent/file.md"])
            assert exc.value.code == 2

    def test_body_file_path_traversal_exits_2(self):
        """CWE-22: Path traversal in body-file is rejected."""
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body-file", "../../etc/passwd"])
            assert exc.value.code == 2

    def test_review_comment_reply_success(self, capsys):
        response = json.dumps(
            {
                "id": 999,
                "html_url": "https://example.com",
                "created_at": "now",
            }
        )
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=response, rc=0),
            ),
        ):
            rc = main(
                [
                    "--pull-request",
                    "50",
                    "--comment-id",
                    "123",
                    "--body",
                    "Fixed.",
                ]
            )
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["in_reply_to"] == 123

    def test_top_level_comment_success(self, capsys):
        response = json.dumps(
            {
                "id": 888,
                "html_url": "https://example.com",
                "created_at": "now",
            }
        )
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=response, rc=0),
            ),
        ):
            rc = main(["--pull-request", "50", "--body", "All addressed."])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["in_reply_to"] is None

    def test_api_error_exits_3(self):
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr="API error"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", "test"])
            assert exc.value.code == 3

    def test_body_from_file(self, stub_git_probes, tmp_path_is_temp_root, capsys):
        # The strict reader needs a temp root; CI puts basetemp outside /tmp.
        tmp_path = tmp_path_is_temp_root
        body_file = tmp_path / "body.md"
        body_file.write_text("hello from file")
        response = json.dumps(
            {
                "id": 777,
                "html_url": "https://example.com",
                "created_at": "now",
            }
        )
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=response, rc=0),
            ),
            patch(
                "github_core.validation.assert_valid_body_file",
            ),
        ):
            rc = main(
                [
                    "--pull-request",
                    "1",
                    "--body-file",
                    str(body_file),
                ]
            )
        assert rc == 0


@pytest.mark.usefixtures("no_prior_comment")
class TestNotFound:
    """A 404 from the replies endpoint exits 2 with a one-line message (D29)."""

    _GH_BODY = (
        '{"message":"Not Found","documentation_url":"https://docs.github.com","status":"404"}'
    )

    def _run(self, argv, stdout="", stderr=""):
        with (
            patch("post_pr_comment_reply.assert_gh_authenticated"),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=stdout, stderr=stderr, rc=1),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        return exc.value.code

    def test_missing_review_comment_exits_2_with_one_line(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "123", "--body", "x"],
            stdout=self._GH_BODY,
            stderr="gh: Not Found (HTTP 404)",
        )
        assert code == 2
        err = capsys.readouterr().err
        assert err.strip() == "Comment 123 not found on o/r#50"
        assert "}" not in err

    def test_missing_pull_request_exits_2(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--body", "x"],
            stderr="gh: Not Found (HTTP 404)",
        )
        assert code == 2
        assert capsys.readouterr().err.strip() == "Pull request o/r#50 not found"

    def test_404_detected_from_json_body_alone(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "9", "--body", "x"],
            stdout=self._GH_BODY,
        )
        assert code == 2
        assert "Comment 9 not found" in capsys.readouterr().err

    def test_non_404_failure_still_exits_3(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "9", "--body", "x"],
            stderr="gh: Server Error (HTTP 500)",
        )
        assert code == 3
        assert "Failed to post comment" in capsys.readouterr().err

    def test_forbidden_is_not_reported_as_not_found(self):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "9", "--body", "x"],
            stderr="gh: Forbidden (HTTP 403)",
        )
        assert code == 3


@pytest.mark.usefixtures("no_prior_comment")
class TestDryRun:
    @staticmethod
    def _comment_on(pr):
        body = {"id": 77, "pull_request_url": f"https://api.github.com/repos/o/r/pulls/{pr}"}
        return _completed(stdout=json.dumps(body))

    @staticmethod
    def _run(argv, target=None):
        with (
            patch("post_pr_comment_reply.assert_gh_authenticated"),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", return_value=target or _completed(stdout="{}")) as run,
        ):
            rc = main(argv)
        return rc, run

    def test_top_level_comment_reports_endpoint_and_posts_nothing(self, capsys):
        rc, run = self._run(["--pull-request", "5", "--body", "hello", "--dry-run"])

        output = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert output["dryRun"] is True
        assert output["action"] == "would_post"
        assert output["endpoint"] == "repos/o/r/issues/5/comments"
        assert output["body_chars"] == 5
        assert run.call_args.args[0] == ["gh", "api", "repos/o/r/pulls/5"]
        assert run.call_count == 1

    def test_threaded_reply_reports_reply_endpoint(self, capsys):
        rc, run = self._run(
            ["--pull-request", "5", "--comment-id", "77", "--body", "hi", "--dry-run"],
            target=self._comment_on(5),
        )

        output = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert output["endpoint"] == "repos/o/r/pulls/5/comments/77/replies"
        assert output["in_reply_to"] == 77
        assert run.call_args.args[0] == ["gh", "api", "repos/o/r/pulls/comments/77"]
        assert run.call_count == 1

    def test_dry_run_still_rejects_an_empty_body(self):
        with pytest.raises(SystemExit) as exc:
            self._run(["--pull-request", "5", "--body", "", "--dry-run"])

        assert exc.value.code == 2

    def test_missing_pull_request_exits_2_like_a_real_run(self, capsys):
        missing = _completed(rc=1, stderr="gh: Not Found (HTTP 404)")
        with pytest.raises(SystemExit) as exc:
            self._run(["--pull-request", "5", "--body", "hi", "--dry-run"], target=missing)

        assert exc.value.code == 2
        assert "Pull request o/r#5 not found" in capsys.readouterr().err

    def test_missing_comment_exits_2_naming_the_comment(self, capsys):
        missing = _completed(rc=1, stderr="gh: Not Found (HTTP 404)")
        with pytest.raises(SystemExit) as exc:
            self._run(
                ["--pull-request", "5", "--comment-id", "77", "--body", "hi", "--dry-run"],
                target=missing,
            )

        assert exc.value.code == 2
        assert "Comment 77 not found" in capsys.readouterr().err

    def test_api_failure_while_reading_the_target_exits_3(self):
        broken = _completed(rc=1, stderr="HTTP 502: Bad Gateway")
        with pytest.raises(SystemExit) as exc:
            self._run(["--pull-request", "5", "--body", "hi", "--dry-run"], target=broken)

        assert exc.value.code == 3

    def test_comment_on_another_pull_request_exits_2_like_the_scoped_post(self, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(
                ["--pull-request", "5", "--comment-id", "77", "--body", "hi", "--dry-run"],
                target=self._comment_on(6),
            )

        assert exc.value.code == 2
        assert "Comment 77 not found" in capsys.readouterr().err

    def test_pull_request_number_is_matched_exactly_not_by_suffix(self, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(
                ["--pull-request", "5", "--comment-id", "77", "--body", "hi", "--dry-run"],
                target=self._comment_on(15),
            )

        assert exc.value.code == 2

    def test_unparseable_comment_body_is_treated_as_not_belonging(self):
        with pytest.raises(SystemExit) as exc:
            self._run(
                ["--pull-request", "5", "--comment-id", "77", "--body", "hi", "--dry-run"],
                target=_completed(stdout="not json"),
            )

        assert exc.value.code == 2

    def test_timeout_reading_the_target_exits_3_not_a_traceback(self, capsys):
        with (
            patch("post_pr_comment_reply.assert_gh_authenticated"),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30)),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "5", "--body", "hi", "--dry-run"])

        assert exc.value.code == 3
        assert "Timed out after 30s" in capsys.readouterr().err


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
