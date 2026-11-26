"""Negative tests for the fresh review rounds on the ship scripts.

Each test failed, or could not be written, against the code before the fix.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    GITHUB,
    SCRIPTS,
    approved_ado_build,
    invoke,
    publish,
    run_pr,
    values,
)


def _remote_has(tmp_path, branch: str) -> str | None:
    done = subprocess.run(
        [
            "git",
            f"--git-dir={tmp_path / 'remote.git'}",
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.stdout.strip() or None


class TestFreshRoundFindings:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    @pytest.mark.parametrize("script", ["ship_detect.py", "ship_preflight.py", "ship_pr.py"])
    def test_help_is_a_stop_not_a_bare_exit(self, tmp_path, script, flag):
        done = subprocess.run(
            [sys.executable, "-I", str(SCRIPTS / script), flag, "--output-format", "human"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert done.returncode == 2
        assert done.stdout.splitlines()[-1].startswith("STOP: bad-arguments")

    @pytest.mark.parametrize("codepoint", [0x80, 0x9B, 0x9D, 0x9F])
    def test_c1_controls_are_stripped(self, scripts, codepoint):
        assert scripts[0].clean(f"a{chr(codepoint)}b") == "a b"

    @pytest.mark.parametrize(
        "url", ["https://github.com#@evil.com/", "https://github.com?@evil.com/x"]
    )
    def test_query_or_fragment_at_sign_is_not_userinfo(self, scripts, url):
        assert scripts[0].remote_host(url) == "github.com"

    def test_title_rule_matches_the_description_validator(self, scripts):
        import re as _re

        helper = Path(scripts[3].checks_mod._validate_description()).read_text(encoding="utf-8")
        start = helper.index("_CONVENTIONAL_COMMIT_PATTERN = re.compile(")
        block = helper[start : helper.index(")\n", helper.index(".+", start)) + 2]
        parts = _re.findall(r'r"([^"]*)"', block)
        assert "".join(parts) == scripts[3].checks_mod._CONVENTIONAL_RE.pattern

    @pytest.mark.parametrize("title", ["fix(CI): repair the build", "feat(a b): spaced scope"])
    def test_titles_the_helper_accepts_are_accepted(self, scripts, title):
        assert scripts[3].checks_mod.title_problem(title) is None

    def test_title_with_a_control_character_fails(self, scripts):
        assert scripts[3].checks_mod.title_problem("fix: a\rb") == "title has a control character"

    def test_multiline_body_that_mentions_backslash_n_passes(self, scripts):
        body = "## Summary\n\nSplits on `\\n` in the parser.\n"
        assert scripts[3].checks_mod.body_problem(body) is None
        assert scripts[3].checks_mod.body_problem("one\\ntwo\\nthree") is not None

    def test_every_child_timeout_fits_the_run_budget(self, scripts, monkeypatch):
        common = scripts[0]
        monkeypatch.setattr(common, "_RUN_DEADLINE", common.time.monotonic() + 5)
        seen = []
        real = common.subprocess.run

        def spy(argv, **kwargs):
            seen.append(kwargs["timeout"])
            return real(argv, **kwargs)

        monkeypatch.setattr(common.subprocess, "run", spy)
        common.run([sys.executable, "-c", "pass"], timeout=600)
        assert seen and seen[0] <= 5

    @pytest.mark.parametrize(
        ("rc", "stderr", "reason", "code"),
        [
            (2, "Invalid body file: x\n", "pr-create-failed", 2),
            (4, "gh: error\n", "auth-failed", 4),
            (
                1,
                "To get started with GitHub CLI, please run: gh auth login\nexit\n",
                "auth-failed",
                4,
            ),
            (1, "gh: GraphQL error\n", "pr-create-failed", 3),
        ],
    )
    def test_create_failures_name_their_cause(
        self, owner, fakes, scripts, capsys, rc, stderr, reason, code
    ):
        _repo, body = owner
        fakes.rule("new_pr", ["--title"], {"rc": rc, "stderr": stderr})
        exit_code, lines = publish(scripts, capsys, body)
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")


class TestFreshRoundTwoFindings:
    def _open_pr(self, make_repo, fakes, *, author="me", head=None):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {"number": 7, "state": "OPEN", "author": {"login": author}, "url": "u"}
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        fakes.rule(
            "gh",
            ["pr", "view", "7"],
            {
                "stdout": json.dumps(
                    {
                        "headRefName": "feat/ship-change",
                        "headRefOid": head or git(repo, "rev-parse", "HEAD"),
                    }
                )
            },
        )
        return repo

    def test_a_call_without_a_pipeline_wait_never_starts_the_window(
        self, make_repo, fakes, scripts, capsys
    ):
        repo = self._open_pr(make_repo, fakes)
        fakes.marker(0)
        code, _lines = invoke(scripts[2], ["--check", "tree", "--check", "reviewed"], capsys)
        assert code == 0
        scratch = repo / ".project-toolkit" / "scratch"
        assert not list(scratch.glob("ship-deadline-*")) if scratch.exists() else True

    def test_a_late_first_pending_gets_the_full_window(self, make_repo, fakes, scripts, capsys):
        self._open_pr(make_repo, fakes)
        fakes.marker(0)
        invoke(scripts[2], ["--check", "tree"], capsys)
        fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": "{}\n"})
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 0
        assert int(values(lines, "PIPELINE_DEADLINE")[0]) > time.time() + 1700

    def test_contributor_deferred_pipeline_reports_instead_of_publishing(
        self, make_repo, fakes, scripts, capsys
    ):
        self._open_pr(make_repo, fakes, author="alice", head="0" * 40)
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 0
        assert values(lines, "MODE") == ["contributor"]
        assert values(lines, "CHECK")[0].startswith("pipeline=DEFERRED")
        assert lines[-1] == "NEXT: report"

    def test_stored_int_read_only_never_creates_state(self, scripts, tmp_path):
        common = scripts[0]
        assert common.stored_int(tmp_path, "s.txt", 5, store=False) == 5
        assert not (tmp_path / common.SCRATCH_REL).exists()


class TestFreshRoundThreeFindings:
    def test_an_echoed_branch_name_is_not_an_auth_signal(self, scripts):
        detect = scripts[1]
        done = scripts[0].Completed(
            1,
            "",
            'a pull request for branch "feat/authentication-fix" into branch "main" '
            "already exists\n",
        )
        halt = detect.query_halt("pr-create-failed", done)
        assert halt.reason == "pr-create-failed"
        assert halt.code == 3
        assert "already exists" in halt.detail

    def test_create_failure_keeps_the_cause_not_the_footer(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        stderr = "a pull request for branch already exists\nPR creation failed (exit code: 1)\n"
        fakes.rule("new_pr", ["--title"], {"rc": 1, "stderr": stderr})
        code, lines = publish(scripts, capsys, body)
        assert code == 3
        assert lines[-1] == "STOP: pr-create-failed a pull request for branch already exists"

    def test_a_hook_declined_push_names_the_rejection(self, owner, scripts, capsys, monkeypatch):
        _repo, body = owner
        stderr = (
            "remote: policy says no\nTo ../remote.git\n"
            " ! [remote rejected] feat/ship-change -> feat/ship-change"
            " (pre-receive hook declined)\n"
            "error: failed to push some refs to '../remote.git'\n"
        )
        common = scripts[0]
        real_git = common.git

        def failing(args, cwd=None, timeout=60):
            if args[:1] == ["push"]:
                return common.Completed(1, "", stderr)
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", failing)
        code, lines = publish(scripts, capsys, body)
        assert code == 3
        assert "pre-receive hook declined" in lines[-1]

    def test_a_crashing_base_validator_names_its_error(
        self, owner, base_validator, scripts, capsys
    ):
        repo, body = owner
        base_validator(repo, "import missing_module_for_ship_test\n", closure=False)
        code, lines = run_pr(
            scripts,
            capsys,
            "check",
            "--title",
            "feat(ship): add the driver",
            "--body-file",
            str(body),
        )
        assert code == 0
        assert "ModuleNotFoundError" in values(lines, "CHECK")[-1]

    def test_cause_line_falls_back_when_stderr_is_empty(self, scripts):
        assert scripts[0].cause_line("", "exit 9") == "exit 9"
        assert (
            scripts[0].cause_line("PR creation failed (exit code: 1)\n", "x")
            == "PR creation failed (exit code: 1)"
        )


class TestFreshRoundFourFindings:
    def test_user_query_names_the_enterprise_host(self, make_repo, fakes, scripts, capsys):
        make_repo("https://ghe.example.com/o/r.git")
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {"number": 3, "state": "OPEN", "author": {"login": "me"}, "url": "u"}
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 0
        assert values(lines, "MODE") == ["owner"]
        user_call = [call for call in fakes.calls("gh") if call[1:3] == ["api", "user"]][0]
        assert user_call[-2:] == ["--hostname", "ghe.example.com"]

    def test_a_merge_commit_that_moves_during_the_wait_is_pending(
        self, make_repo, fakes, scripts, capsys
    ):
        repo = make_repo("https://dev.azure.com/contoso/p/_git/r")
        fakes.rule(
            "az",
            ["repos", "pr", "list"],
            {"stdout": json.dumps([{"pullRequestId": 77, "createdBy": {"uniqueName": "me"}}])},
        )
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        head = git(repo, "rev-parse", "HEAD")
        first = {"source": "refs/heads/feat/ship-change", "head": head, "merge": "m1" * 20}
        moved = dict(first, merge="m2" * 20)
        fakes.rule(
            "az",
            ["repos", "pr", "show"],
            {"stdout": json.dumps(first)},
            {"stdout": json.dumps(moved)},
        )
        approved_ado_build(fakes, "m2" * 20)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--wait-seconds", "0"], capsys)
        assert code == 0
        assert values(lines, "CHECK") == [
            "pipeline=PENDING pr=77 merge commit moved during the check"
        ]


class TestFreshRoundFiveFindings:
    @pytest.mark.parametrize("value", ["main\n", "develop\n", "feat/x\n"])
    def test_a_trailing_newline_is_not_a_safe_ref(self, scripts, value):
        assert scripts[0].safe_ref(value) is False
        assert scripts[0].safe_ref(value.strip()) is True

    def test_a_base_with_a_newline_never_reaches_the_push(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path
    ):
        repo = make_repo(GITHUB)
        git(repo, "switch", "-q", "-C", "develop")
        fakes.no_pr_github()
        code, lines = publish(
            scripts,
            capsys,
            body_file(repo),
            "--draft",
            "--paths-checked-by-hand",
            "--base",
            "develop\n",
        )
        assert code != 0
        assert lines[-1].startswith("STOP: ")
        assert "PUSH: pushed" not in lines
        assert _remote_has(tmp_path, "develop") is None

    def _github_pr(self, make_repo, fakes):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        fakes.rule(
            "gh",
            ["pr", "view", "41"],
            {
                "stdout": json.dumps(
                    {
                        "headRefName": "feat/ship-change",
                        "headRefOid": git(repo, "rev-parse", "HEAD"),
                    }
                )
            },
        )

    def test_exit_7_with_a_failed_required_check_is_fail(self, make_repo, fakes, scripts, capsys):
        self._github_pr(make_repo, fakes)
        data = {
            "RequiredState": "PENDING",
            "AllPassing": False,
            "FailedRequiredChecks": [{"Name": "lint"}],
            "PendingRequiredChecks": [{"Name": "tests"}],
        }
        fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": json.dumps({"Data": data}) + "\n"})
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 1
        check = values(lines, "CHECK")[-1]
        assert check.startswith("pipeline=FAIL pr=41")
        assert check.endswith("failed=lint pending=tests")

    def test_exit_7_still_running_names_the_pr_and_checks(self, make_repo, fakes, scripts, capsys):
        self._github_pr(make_repo, fakes)
        data = {"RequiredState": "PENDING", "PendingRequiredChecks": [{"Name": "tests"}]}
        fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": json.dumps({"Data": data}) + "\n"})
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 0
        assert values(lines, "CHECK")[-1] == (
            "pipeline=PENDING pr=41 required checks still running pending=tests"
        )

    def test_exit_7_with_an_incomplete_rollup_stays_pending(
        self, make_repo, fakes, scripts, capsys
    ):
        self._github_pr(make_repo, fakes)
        data = {"RequiredState": "UNKNOWN", "ChecksIncomplete": True}
        fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": json.dumps({"Data": data}) + "\n"})
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 0
        assert values(lines, "CHECK")[-1].startswith("pipeline=PENDING pr=41")

    def test_exit_7_without_data_names_the_pr(self, make_repo, fakes, scripts, capsys):
        self._github_pr(make_repo, fakes)
        fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": "not json\n"})
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 0
        assert values(lines, "CHECK")[-1] == "pipeline=PENDING pr=41 required checks still running"

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            (
                "Body file not found: /nonexistent/x.md\n",
                "exit=2: Body file not found: /nonexistent/x.md",
            ),
            ("", "exit=2"),
        ],
    )
    def test_a_description_helper_failure_names_its_cause(self, scripts, stderr, expected):
        assert scripts[3].checks_mod.description_problem(2, "", stderr) == expected

    def test_an_axis_with_a_newline_is_refused(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.no_pr_github()
        code, lines = invoke(
            scripts[2], ["--check", "reviewed", "--require-axis", "security\n"], capsys
        )
        assert code == 2
        assert lines[-1].startswith("STOP: bad-arguments --require-axis")

    def test_a_branch_name_with_a_newline_is_refused(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        code, lines = run_pr(scripts, capsys, "branch", "--name", "feat/ship-x\n")
        assert code == 1
        assert lines[-1].startswith("STOP: bad-branch-name")

    def test_result_keys_and_acts_refuse_a_newline(self, scripts):
        result = scripts[0].Result("t.py", frozenset({"x-failed"}))
        with pytest.raises(ValueError, match="invalid result key"):
            result.add("KEY\n", "v")
        with pytest.raises(ValueError, match="invalid NEXT act"):
            result.next("act\n")
