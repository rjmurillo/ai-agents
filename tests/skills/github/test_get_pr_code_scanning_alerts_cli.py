"""CLI tests for get_pr_code_scanning_alerts.py: exit codes, JSON envelope, flags."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from code_scanning_fakes import (
    HEAD_SHA,
    OWNER,
    REPO,
    FakeGitHub,
    alert,
    analysis,
    sarif_result,
    standard_pr,
)
from test_helpers import import_skill_script

mod = import_skill_script("get_pr_code_scanning_alerts", "pr")
from github_core.api import RepoInfo


class TestCli:
    ARGS = ["--pull-request", "7", "--head-sha", HEAD_SHA, "--output-format", "json"]

    def _main(self, argv, fake=None, capsys=None):
        fake = fake or standard_pr(FakeGitHub())
        with (
            patch.object(mod, "gh_get", fake),
            patch.object(mod, "assert_gh_authenticated"),
            patch.object(mod, "resolve_repo_params", return_value=RepoInfo(OWNER, REPO)),
        ):
            code = mod.main(argv)
        return code, json.loads(capsys.readouterr().out)

    def test_help_exits_zero_with_examples_and_exit_codes(self, capsys):
        with pytest.raises(SystemExit) as caught:
            mod.main(["--help"])
        out = capsys.readouterr().out
        assert caught.value.code == 0
        assert "examples:" in out
        assert "exit codes:" in out
        assert "--pull-request 123 --head-sha" in out

    def test_current_outcome_is_json_on_stdout_with_exit_zero(self, capsys):
        fake = standard_pr(FakeGitHub(), results=[sarif_result(5)])
        fake.alerts([alert(5)])
        code, body = self._main(
            self.ARGS + ["--tree-state", "clean", "--changed-file", "src/a.py"], fake, capsys
        )
        assert code == 0
        assert body["Success"] is True
        assert body["Data"]["outcome"] == "CURRENT"
        assert body["Data"]["alerts"][0]["path"] == "src/a.py"

    def test_tree_state_defaults_to_dirty_so_the_default_is_never_current(self, capsys):
        code, body = self._main(self.ARGS, None, capsys)
        assert code == 0
        assert body["Data"]["outcome"] == "STALE"

    def test_not_analyzed_exits_zero(self, capsys):
        fake = FakeGitHub()
        fake.analyses([])
        code, body = self._main(self.ARGS, fake, capsys)
        assert (code, body["Data"]["outcome"]) == (0, "NOT ANALYZED")

    def test_skipped_reports_the_outcome_in_json_and_exits_with_the_class_code(self, capsys):
        fake = FakeGitHub()
        fake.analyses([analysis(1)])
        fake.fail_page["code-scanning/analyses"] = (
            1,
            mod.SkipError("authorization or not-found error (HTTP 403)", 4),
        )
        code, body = self._main(self.ARGS, fake, capsys)
        assert code == 4
        assert body["Success"] is False
        assert body["Data"]["outcome"] == "SKIPPED"
        assert body["Data"]["status_line"].startswith("CodeQL: SKIPPED (")

    def test_a_pagination_failure_exits_three_and_is_skipped(self, capsys):
        fake = standard_pr(FakeGitHub())
        fake.alerts([alert(1)], [alert(2)])
        fake.fail_page["code-scanning/alerts"] = (2, mod.SkipError("GitHub request failed"))
        code, body = self._main(self.ARGS + ["--tree-state", "clean"], fake, capsys)
        assert (code, body["Data"]["outcome"]) == (3, "SKIPPED")

    @pytest.mark.parametrize("sha_arg", ["abc", "A" * 40, "g" * 40, ""])
    def test_a_bad_head_sha_is_a_usage_error(self, sha_arg, capsys):
        with pytest.raises(SystemExit) as caught:
            mod.main(["--pull-request", "7", "--head-sha", sha_arg, "--output-format", "json"])
        assert caught.value.code == 2
        assert json.loads(capsys.readouterr().out)["Error"]["Code"] == 2

    @pytest.mark.parametrize("number", ["0", "-3"])
    def test_a_non_positive_pull_request_is_a_usage_error(self, number, capsys):
        with pytest.raises(SystemExit) as caught:
            mod.main(["--pull-request", number, "--head-sha", HEAD_SHA, "--output-format", "json"])
        assert caught.value.code == 2

    def test_an_unknown_flag_exits_two_with_empty_stdout(self, capsys):
        with pytest.raises(SystemExit) as caught:
            mod.main(self.ARGS + ["--bogus"])
        captured = capsys.readouterr()
        assert caught.value.code == 2
        assert captured.out == ""
        assert "unrecognized arguments" in captured.err

    def test_changed_files_come_from_a_file(self, tmp_path, capsys):
        listing = tmp_path / "changed.txt"
        listing.write_text("src/a.py\n\n../escape.py\n", encoding="utf-8")
        fake = standard_pr(FakeGitHub(), results=[sarif_result(5)])
        fake.alerts([alert(5)])
        code, body = self._main(
            self.ARGS + ["--tree-state", "clean", "--changed-files-from", str(listing)],
            fake,
            capsys,
        )
        assert code == 0
        assert [a["path"] for a in body["Data"]["alerts"]] == ["src/a.py"]

    def test_changed_files_come_from_stdin(self, capsys):
        fake = standard_pr(FakeGitHub(), results=[sarif_result(5)])
        fake.alerts([alert(5)])
        with patch.object(mod.sys, "stdin", io.StringIO("src/a.py\n")):
            code, body = self._main(
                self.ARGS + ["--tree-state", "clean", "--changed-files-from", "-"], fake, capsys
            )
        assert (code, len(body["Data"]["alerts"])) == (0, 1)

    def test_a_terminal_stdin_is_refused_without_reading(self, capsys):
        class Tty(io.StringIO):
            def isatty(self):
                return True

            def read(self, *args):
                raise AssertionError("must not read a terminal")

        with patch.object(mod.sys, "stdin", Tty()):
            with pytest.raises(SystemExit) as caught:
                mod.main(self.ARGS + ["--changed-files-from", "-"])
        assert caught.value.code == 2

    def test_a_non_utf8_changed_files_list_is_a_usage_error_not_a_crash(self, tmp_path, capsys):
        listing = tmp_path / "changed.txt"
        listing.write_bytes(b"src/a.py\n\xff\xfe.py\n")
        with pytest.raises(SystemExit) as caught:
            mod.main(self.ARGS + ["--changed-files-from", str(listing)])
        body = json.loads(capsys.readouterr().out)
        assert caught.value.code == 2
        assert body["Error"]["Message"] == "cannot read --changed-files-from: not valid UTF-8"

    def test_non_utf8_bytes_on_stdin_are_a_usage_error_not_a_crash(self, capsys):
        class Bad(io.StringIO):
            def isatty(self):
                return False

            def read(self, *args):
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        with patch.object(mod.sys, "stdin", Bad()):
            with pytest.raises(SystemExit) as caught:
                mod.main(self.ARGS + ["--changed-files-from", "-"])
        assert caught.value.code == 2
        assert json.loads(capsys.readouterr().out)["Error"]["Code"] == 2

    def test_an_unreadable_changed_files_list_is_a_usage_error(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as caught:
            mod.main(self.ARGS + ["--changed-files-from", str(tmp_path / "missing.txt")])
        assert caught.value.code == 2

    def test_an_unauthenticated_gh_still_emits_one_json_outcome(self, capsys):
        with (
            patch.object(mod, "assert_gh_authenticated", side_effect=SystemExit(4)),
            patch.object(mod, "resolve_repo_params"),
        ):
            code = mod.main(self.ARGS)
        body = json.loads(capsys.readouterr().out)
        assert code == 4
        assert body["Data"]["outcome"] == "SKIPPED"

    def test_an_unexpected_exit_code_from_a_helper_is_treated_as_an_auth_class_skip(self, capsys):
        with (
            patch.object(mod, "assert_gh_authenticated", side_effect=SystemExit(1)),
            patch.object(mod, "resolve_repo_params"),
        ):
            assert mod.main(self.ARGS) == 4
