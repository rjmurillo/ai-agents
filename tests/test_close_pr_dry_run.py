"""PR lookup and --dry-run tests for close_pr.py."""

from __future__ import annotations

import json

import pytest

from tests.close_pr_test_support import OPEN, pages, run_close, state_reply
from tests.test_close_pr import _completed

pytestmark = pytest.mark.usefixtures("stub_git_probes", "tmp_path_is_temp_root")

_GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
_GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"
_DRY = ["--pull-request", "5", "--dry-run"]


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
    replies = [_completed(rc=1, stdout=stdout, stderr=stderr)]  # any later gh call raises
    with pytest.raises(SystemExit) as exc:
        run_close(["--pull-request", "999999"], replies)
    assert exc.value.code == code


class TestDryRun:
    def test_open_pr_reports_would_close_and_makes_no_write_call(self, capsys):
        rc, run = run_close([*_DRY, "--comment", "superseded"], [OPEN, pages()])
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["action"] == "would_close"
        assert data["dryRun"] is True
        assert data["wouldComment"] is True
        assert data["commentDuplicate"] is False
        assert run.call_count == 2

    def test_open_pr_dry_run_detects_duplicate_closing_comment(self, capsys):
        existing = pages(("superseded", "bot", "User"))
        rc, run = run_close(
            [*_DRY, "--comment", "superseded"], [OPEN, existing, _completed(stdout="bot\n")]
        )
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["wouldComment"] is False
        assert data["commentDuplicate"] is True
        assert data["existingCommentId"] == 100
        assert run.call_count == 3

    @pytest.mark.parametrize("state", ["CLOSED", "MERGED"])
    def test_closed_or_merged_pr_reports_noop_and_skips_the_comment_lookup(self, state, capsys):
        rc, run = run_close([*_DRY, "--comment", "S"], [state_reply(state)])
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["action"] == "none"
        assert data["dryRun"] is True
        assert run.call_count == 1

    def test_dry_run_without_comment_never_would_comment(self, capsys):
        rc, _ = run_close(_DRY, [OPEN])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["wouldComment"] is False

    def test_dry_run_still_fails_when_the_pr_is_missing(self):
        with pytest.raises(SystemExit) as exc:
            run_close(_DRY, [_completed(rc=1, stderr="Could not resolve to a PullRequest")])
        assert exc.value.code == 2

    def test_dry_run_comment_lookup_failure_exits_3(self):
        with pytest.raises(SystemExit) as exc:
            run_close(
                [*_DRY, "--comment", "S"],
                [OPEN, _completed(rc=1, stderr="HTTP 502 Bad Gateway")],
            )
        assert exc.value.code == 3

    def test_default_run_has_no_dry_run_key(self, capsys):
        rc, _ = run_close(["--pull-request", "5"], [OPEN, _completed()])
        assert rc == 0
        assert "dryRun" not in json.loads(capsys.readouterr().out)
