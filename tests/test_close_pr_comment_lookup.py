"""Closing-comment dedupe tests for close_pr.py and pr_comment_lookup.py."""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.close_pr_test_support import DENIED, OPEN, pages, run_close, subcommands
from tests.test_close_pr import _completed

pytestmark = pytest.mark.usefixtures("stub_git_probes", "tmp_path_is_temp_root")

_ARGV = ["--pull-request", "5", "--comment", "Superseded by #6"]
_OK = _completed(rc=0)
_SAME = ("Superseded by #6\n", "BotUser", "User")


@pytest.mark.parametrize(
    ("existing", "user_reply", "skipped"),
    [
        pytest.param(
            [_SAME], _completed(stdout="botuser\n"), True, id="same-author-case-and-crlf-differ"
        ),
        pytest.param(
            [("Superseded by #6", "other-user", "User")],
            _completed(stdout="botuser\n"),
            False,
            id="other-author-posts",
        ),
        pytest.param(
            [("Superseded by #6", "x[bot]", "Bot")],
            _completed(rc=1, stderr=DENIED),
            True,
            id="denied-user-identical-bot-skips",
        ),
        pytest.param(
            [("Superseded by #6", "other-app[bot]", "Bot")],
            _completed(rc=1, stderr=DENIED),
            True,
            id="denied-user-different-bot-skips-by-design",
        ),
        pytest.param(
            [("Superseded by #6", "alice", "User")],
            _completed(rc=1, stderr=DENIED),
            False,
            id="denied-user-human-posts",
        ),
        pytest.param([("Other text", "x[bot]", "Bot")], None, False, id="no-body-match-posts"),
        pytest.param([], None, False, id="no-comments-posts"),
    ],
)
def test_duplicate_decision(existing, user_reply, skipped, capsys):
    replies = [OPEN, pages(*existing)]
    replies += [user_reply] if user_reply is not None else []
    replies += [] if skipped else [_OK]
    replies += [_OK]
    rc, run = run_close(_ARGV, replies)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert subcommands(run)[-1] == ["pr", "close"]
    assert (["pr", "comment"] in subcommands(run)) is not skipped
    assert out["action"] == "closed"
    assert out["commentSkipped"] is skipped
    assert out["commentPosted"] is not skipped
    assert ("existingCommentId" in out) is skipped


def test_denied_user_lookup_notes_the_fallback_on_stderr(capsys):
    existing = pages(("Superseded by #6", "x[bot]", "Bot"))
    run_close(_ARGV, [OPEN, existing, _completed(rc=1, stderr=DENIED), _OK])
    assert "matching identical comments by bot" in capsys.readouterr().err


@pytest.mark.parametrize(
    "lookup_replies",
    [
        pytest.param([_completed(rc=1, stderr="HTTP 502 Bad Gateway")], id="list-502"),
        pytest.param([_completed(stdout="not-json")], id="list-not-json"),
        pytest.param([_completed(stdout='{"not": "pages"}')], id="list-not-pages"),
        pytest.param([subprocess.TimeoutExpired(cmd="gh", timeout=120)], id="list-timeout"),
        pytest.param(
            [pages(_SAME), _completed(rc=1, stderr="HTTP 502 Bad Gateway")], id="user-502"
        ),
        pytest.param(
            [pages(_SAME), subprocess.TimeoutExpired(cmd="gh", timeout=30)], id="user-timeout"
        ),
        pytest.param([pages(_SAME), _completed(rc=0, stdout="\n")], id="user-empty-login"),
    ],
)
def test_lookup_failure_fails_closed_with_exit_3(lookup_replies, capsys):
    with pytest.raises(SystemExit) as exc:
        run_close(_ARGV, [OPEN, *lookup_replies])
    assert exc.value.code == 3
    assert "NOT closed" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("comments", "expected"),
    [
        pytest.param(
            [
                {"id": 1, "user": {"login": "alice", "type": "User"}},
                {"id": 2, "user": {"login": "ci[bot]", "type": "Bot"}},
                {"id": 3, "user": {"login": "other[bot]", "type": "Bot"}},
            ],
            2,
            id="first-bot-wins",
        ),
        pytest.param([], None, id="empty"),
        pytest.param([{"id": 1, "user": {"login": "a", "type": "User"}}], None, id="human-only"),
        pytest.param([{"id": 1}, {"user": None}], None, id="no-user"),
    ],
)
def test_first_bot_comment(comments, expected):
    import pr_comment_dedupe

    found = pr_comment_dedupe.first_bot_comment(comments)
    assert (found["id"] if found else None) == expected
