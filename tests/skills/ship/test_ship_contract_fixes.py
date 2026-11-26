"""Negative tests for the ADR-127 contract gaps the scripts PR review found.

- Decision 3 item 4: a remote URL must match an allowed scheme list.
- Decision 4 item 12: --output-format must hold wherever it appears.
- Decision 4 item 8: a paths check that could not run is not a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.skills.ship.ship_helpers import (
    GITHUB,
    SCRIPTS,
    TITLE,
    VALIDATOR_PASS,
    invoke,
    run_pr,
    values,
)


class TestRemoteSchemes:
    @pytest.mark.parametrize(
        "url",
        [
            "ext::sh -c id",
            "file://dev.azure.com/x",
            "git://github.com/o/r.git",
            "ftp://dev.azure.com/x",
            "http://github.com/o/r.git",
            "fd::17",
            "host::path",
            "C:\\repo",
            "c:/repo",
            "-oProxyCommand=x:y",
            "https://-h/x",
            "ssh://-oProxyCommand=x/y",
            "https://[::1]/x",
            "@h:p",
            "ssh://git@[2001:db8::1]/a",
            "https://dev.azure.com./o/p/_git/r",
            "https://a..b/x",
        ],
    )
    def test_disallowed_remote_forms_have_no_host(self, scripts, url):
        assert scripts[0].remote_host(url) is None

    @pytest.mark.parametrize(
        ("url", "host"),
        [
            ("HTTPS://github.com/o/r.git", "github.com"),
            ("ssh://git@ssh.dev.azure.com/v3/o/p/r", "ssh.dev.azure.com"),
            ("git@github.com:o/r.git", "github.com"),
        ],
    )
    def test_allowed_remote_forms_keep_their_host(self, scripts, url, host):
        assert scripts[0].remote_host(url) == host

    def test_transport_remote_stops_detect(self, make_repo, fakes, scripts, capsys):
        make_repo("ext::sh -c id")
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 2
        assert lines[-1].startswith("STOP: unsupported-remote")
        assert not fakes.calls()


class TestOutputFormatPosition:
    def test_flag_before_the_subcommand_is_honored(self, make_repo, fakes):
        repo = make_repo(GITHUB)
        done = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPTS / "ship_pr.py"),
                "--output-format",
                "human",
                "branch",
                "--name",
                "BAD",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert done.returncode == 1
        assert done.stdout.splitlines()[-1].startswith("STOP: bad-branch-name")

    def test_flag_after_the_subcommand_still_wins(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        code = scripts[3].main(["branch", "--name", "BAD", "--output-format", "json"])
        assert code == 1
        assert json.loads(capsys.readouterr().out)["Error"]["Code"] == 1

    def test_captured_output_without_the_flag_is_json(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        scripts[3].main(["branch", "--name", "BAD"])
        assert json.loads(capsys.readouterr().out)["Success"] is False


class TestPathsNotRun:
    def test_check_asks_for_a_hand_comparison(self, owner, scripts, capsys):
        _repo, body = owner
        code, lines = run_pr(scripts, capsys, "check", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        assert any(value.startswith("paths=NOT-RUN") for value in values(lines, "CHECK"))
        assert lines[-1] == "NEXT: compare-paths-by-hand"

    def test_publish_stops_without_the_hand_check(self, owner, fakes, scripts, capsys, tmp_path):
        _repo, body = owner
        code, lines = run_pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 1
        assert lines[-1].startswith("STOP: paths-not-checked")
        assert "PUSH: pushed" not in lines
        assert not fakes.calls("new_pr")[1:] and not [
            c for c in fakes.calls("new_pr") if "--title" in c
        ]

    def test_publish_records_the_hand_check(self, owner, scripts, capsys):
        _repo, body = owner
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
        )
        assert code == 0
        assert "CHECK: paths=CHECKED-BY-HAND" in lines

    def test_validator_pass_needs_no_hand_check(self, owner, base_validator, scripts, capsys):
        repo, body = owner
        base_validator(repo, VALIDATOR_PASS)
        code, lines = run_pr(scripts, capsys, "publish", "--title", TITLE, "--body-file", str(body))
        assert code == 0
        assert "CHECK: paths=PASS" in lines
        assert "CHECK: paths=CHECKED-BY-HAND" not in lines


class TestStopDetailCap:
    @pytest.mark.parametrize("output_format", ["human", "json"])
    @pytest.mark.parametrize("script", ["ship_detect.py", "ship_preflight.py", "ship_pr.py"])
    def test_oversized_argument_keeps_stdout_under_the_cap(
        self, make_repo, fakes, script, output_format
    ):
        repo = make_repo(GITHUB)
        done = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPTS / script),
                "--output-format",
                output_format,
                "--bogus",
                "x" * 50000,
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert done.returncode == 2
        assert len(done.stdout.encode("utf-8")) <= 32000

    def test_oversized_stderr_detail_is_truncated(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.rule("gh", ["pr", "view"], {"rc": 1, "stderr": "HTTP 502 " + "y" * 50000 + "\n"})
        code = scripts[1].main(["--output-format", "json"])
        out = capsys.readouterr().out
        envelope = json.loads(out)
        assert code == 3
        assert len(out.encode("utf-8")) <= 32000
        assert envelope["Data"]["STOP"].endswith("...")
        assert len(envelope["Error"]["Message"]) <= 520

    @pytest.mark.parametrize("output_format", ["json", "human"])
    @pytest.mark.parametrize("unit", ['"', "\U0001f600", "\u00e9"])
    def test_near_budget_lines_plus_a_long_stop_stay_under_the_cap(
        self, scripts, tmp_path, output_format, unit
    ):
        common = scripts[0]
        result = common.Result("t.py", frozenset({"x-failed"}))
        for _index in range(59):
            result.add("ITEM", unit * 435)
        result.stop("x-failed", 1, unit * 500)
        text = common.render(result, output_format, tmp_path)
        assert len(text.encode("utf-8")) <= common.MAX_BYTES
        assert len(text.splitlines()) <= common.MAX_LINES
        if output_format == "json":
            assert "DETAIL_FILE" in json.loads(text)["Data"]


class TestAdoDescriptionAfterTitleFailure:
    def test_bad_title_never_reaches_the_description_helper(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo("https://dev.azure.com/contoso/p/_git/r")
        fakes.no_pr_ado()
        fakes.rule(
            "validate_pr_description",
            [],
            {"stdout": json.dumps({"ErrorCount": 0, "WarningCount": 1, "Validations": {}})},
        )
        code, lines = run_pr(
            scripts, capsys, "check", "--title=-x: injected", "--body-file", str(body_file(repo))
        )
        assert code == 1
        assert not fakes.calls("validate_pr_description")
        assert not any(value.startswith("description=") for value in values(lines, "CHECK"))


class TestDeadlineBound:
    def test_far_future_deadline_is_refused(self, make_repo, fakes, scripts, capsys):
        import time

        make_repo(GITHUB)
        code, lines = invoke(
            scripts[2], ["--check", "tree", "--deadline", str(int(time.time()) + 86400)], capsys
        )
        assert code == 2
        assert lines[-1].startswith("STOP: bad-arguments --deadline")
