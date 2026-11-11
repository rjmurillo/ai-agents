"""Tests for close_pr.py: a failed closing comment must stop the run before the close call."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.test_close_pr import _completed, build_parser, main

pytestmark = pytest.mark.usefixtures("stub_git_probes", "tmp_path_is_temp_root")


class TestClosingCommentOutcome:
    """A failed closing comment must stop the run before the close call (exit 3)."""

    _OPEN = _completed(stdout=json.dumps({"state": "OPEN"}))

    def _run(self, replies, capsys=None):
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", side_effect=replies) as run,
        ):
            try:
                rc = main(["--pull-request", "5", "--comment", "Superseded by #6"])
            except SystemExit as exit_:
                rc = exit_.code
        subcommands = [call.args[0][1:3] for call in run.call_args_list]
        return rc, subcommands

    def test_comment_failure_exits_3_and_never_closes(self, capsys):
        rc, subcommands = self._run([self._OPEN, _completed(rc=1, stderr="HTTP 502 bad gateway")])

        assert rc == 3
        assert ["pr", "close"] not in subcommands
        assert subcommands == [["pr", "view"], ["pr", "comment"]]
        err = capsys.readouterr().err
        assert "HTTP 502 bad gateway" in err
        assert "NOT closed" in err

    def test_comment_failure_prints_no_success_envelope(self, capsys):
        self._run([self._OPEN, _completed(rc=1, stderr="boom")])

        assert capsys.readouterr().out == ""

    def test_comment_success_then_close_success(self, capsys):
        rc, subcommands = self._run([self._OPEN, _completed(), _completed()])

        assert rc == 0
        assert subcommands == [["pr", "view"], ["pr", "comment"], ["pr", "close"]]
        assert json.loads(capsys.readouterr().out)["action"] == "closed"

    def test_comment_success_then_close_failure_exits_3(self, capsys):
        rc, subcommands = self._run(
            [self._OPEN, _completed(), _completed(rc=1, stderr="permission denied")]
        )

        assert rc == 3
        assert subcommands[-1] == ["pr", "close"]
        assert "Failed to close PR #5" in capsys.readouterr().err

    def test_no_comment_skips_the_comment_call(self):
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", side_effect=[self._OPEN, _completed()]) as run,
        ):
            rc = main(["--pull-request", "5"])

        assert rc == 0
        assert [c.args[0][1:3] for c in run.call_args_list] == [["pr", "view"], ["pr", "close"]]

    def test_help_documents_comment_failure_exit_code(self, capsys):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--help"])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "examples:" in out
        assert "closing comment" in out
