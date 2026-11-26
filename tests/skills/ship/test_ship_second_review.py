"""Negative tests for round 1 of the second fresh review on the ship scripts.

Each test failed, or could not be written, against the code before the fix.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    GITHUB,
    SCRIPTS,
    VALIDATOR_PASS,
    invoke,
    pending_github_pr,
    publish,
    run_pr,
    symlink_or_skip,
    values,
)

PR_VALIDATIONS = SCRIPTS.parents[1] / "github" / "scripts" / "pr" / "pr_validations.py"


def _no_scratch_ignore(repo) -> None:
    (repo / ".gitignore").write_text("", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "chore: drop the scratch ignore")


class TestTreeIgnoresScratch:
    def test_scratch_files_never_make_the_tree_dirty(self, make_repo, scripts):
        repo = make_repo(GITHUB)
        _no_scratch_ignore(repo)
        assert scripts[0].write_private(repo, "pr-body", ".md", "x") is not None
        assert scripts[2].check_tree(repo).state == "clean"

    def test_other_untracked_files_still_make_it_dirty(self, make_repo, scripts):
        repo = make_repo(GITHUB)
        _no_scratch_ignore(repo)
        scripts[0].write_private(repo, "pr-body", ".md", "x")
        (repo / "stray.txt").write_text("y", encoding="utf-8")
        assert scripts[2].check_tree(repo).detail == "files=1"

    def test_publish_with_a_body_and_no_ignore_rule_is_not_dirty(self, owner, scripts, capsys):
        repo, body = owner
        _no_scratch_ignore(repo)
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            "feat(ship): add the driver",
            "--body-file",
            str(body),
        )
        assert "STOP: tree-dirty" not in lines[-1]
        assert code == 0

    @pytest.mark.parametrize(("rc", "code"), [(124, 3), (127, 3), (128, 2)])
    def test_a_failed_status_keeps_its_cause(self, make_repo, scripts, monkeypatch, rc, code):
        repo = make_repo(GITHUB)
        common = scripts[0]
        monkeypatch.setattr(
            common, "git", lambda args, cwd=None, timeout=60: common.Completed(rc, "", "git: why")
        )
        halt = scripts[2].check_tree(repo)
        assert (halt.reason, halt.code, halt.detail) == ("no-repo", code, "git: why")


class TestDeadlineFailsClosed:
    def _pending(self, make_repo, fakes):
        repo = make_repo(GITHUB)
        pending_github_pr(fakes, git(repo, "rev-parse", "HEAD"))
        return repo

    def test_an_unsafe_scratch_dir_stops_instead_of_restarting_the_window(
        self, make_repo, fakes, scripts, capsys, tmp_path
    ):
        repo = self._pending(make_repo, fakes)
        outside = tmp_path / "outside"
        outside.mkdir()
        (repo / ".project-toolkit").mkdir()
        symlink_or_skip(repo / ".project-toolkit" / "scratch", outside)
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 2
        assert lines[-1].startswith("STOP: deadline-unstored cannot store the pipeline deadline")
        assert list(outside.iterdir()) == []

    def test_a_corrupt_state_file_is_replaced_so_a_rerun_keeps_the_window(
        self, make_repo, fakes, scripts, capsys
    ):
        repo = self._pending(make_repo, fakes)
        head = git(repo, "rev-parse", "HEAD")[:12]
        state = repo / ".project-toolkit" / "scratch"
        state.mkdir(parents=True)
        (state / f"ship-deadline-github-9-{head}.txt").write_text("junk", encoding="utf-8")
        _code, first = invoke(scripts[2], ["--check", "pipeline"], capsys)
        _code, again = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert values(first, "PIPELINE_DEADLINE") == values(again, "PIPELINE_DEADLINE")


class TestDetectRefusesProtectedBranches:
    @pytest.mark.parametrize("branch", ["main", "master"])
    def test_owner_on_a_protected_branch_stops_in_detect(
        self, make_repo, fakes, scripts, capsys, branch
    ):
        repo = make_repo(GITHUB, branch="main")
        if branch != "main":
            git(repo, "switch", "-q", "-C", branch)
        fakes.no_pr_github()
        code, lines = invoke(scripts[1], ["--base", "develop"], capsys)
        assert code == 1
        assert lines[-1] == f"STOP: on-base-branch on {branch}; create a feature branch"

    def test_publish_still_refuses_a_protected_branch_with_an_open_pr(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(GITHUB, branch="main")
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {
                        "number": 5,
                        "state": "OPEN",
                        "author": {"login": "me"},
                        "url": "u",
                        "baseRefName": "main",
                    }
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        code, lines = publish(scripts, capsys, body_file(repo))
        assert code == 1
        assert lines[-1] == "STOP: on-base-branch main is a base branch; create a feature branch"
        assert "PUSH: pushed" not in lines

    def test_a_feature_branch_with_another_base_still_proceeds(
        self, make_repo, fakes, scripts, capsys
    ):
        make_repo(GITHUB)
        fakes.no_pr_github()
        code, lines = invoke(scripts[1], ["--base", "develop"], capsys)
        assert code == 0
        assert lines[-1] == "NEXT: preflight"


class TestCopyFailureNamesItsCause:
    def test_a_failed_git_show_names_the_file_and_cause(
        self, owner, base_validator, scripts, capsys, monkeypatch
    ):
        repo, body = owner
        base_validator(repo, VALIDATOR_PASS)
        common = scripts[0]
        real_git = common.git

        def failing_show(args, cwd=None, timeout=60):
            if args[:1] == ["show"]:
                return common.Completed(128, "", "fatal: bad object\n")
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", failing_show)
        _code, lines = run_pr(
            scripts, capsys, "check", "--title", "feat(ship): x", "--body-file", str(body)
        )
        check = values(lines, "CHECK")[-1]
        assert "(scripts/validation/pr_description.py: fatal: bad object)" in check

    def test_a_path_outside_scripts_names_the_path(self, owner, base_validator, scripts):
        repo, _body = owner
        ctx = scripts[1].detect()
        failure = scripts[3].checks_mod._write_private_tree(ctx, "HEAD", ["other/x.py"], repo)
        assert failure == "other/x.py: path outside scripts/"


@pytest.fixture(scope="module")
def helper():
    spec = importlib.util.spec_from_file_location("_ship_test_pr_validations", PR_VALIDATIONS)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


class TestEscapedNewlineRuleMatchesTheHelper:
    @pytest.mark.parametrize(
        "body",
        [
            "## Summary\\n\\nOne line",
            "## Summary\n\nMentions \\n in prose",
            "plain body",
            "  \\n  ",
            "\\n\n",
        ],
    )
    def test_both_rules_agree(self, scripts, helper, body, capsys):
        try:
            helper.validate_no_escaped_newlines(body)
            helper_rejects = False
        except SystemExit:
            helper_rejects = True
        capsys.readouterr()
        ours = scripts[3].checks_mod.body_problem(body) == "body has an escaped newline"
        assert ours is helper_rejects


class TestWindowsProgramResolution:
    @pytest.fixture
    def windows(self, scripts, monkeypatch, tmp_path):
        """A Windows host whose PATH holds az.cmd and git.exe, with a decoy az.cmd in the cwd."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "az.cmd").write_text("@echo off\n", encoding="utf-8")
        (bin_dir / "git.exe").write_text("", encoding="utf-8")
        cwd = tmp_path / "repo"
        cwd.mkdir()
        (cwd / "az.cmd").write_text("decoy\n", encoding="utf-8")
        monkeypatch.chdir(cwd)
        monkeypatch.setattr(scripts[0].os, "name", "nt")
        monkeypatch.setenv("PATH", os.pathsep.join([".", "relative", str(bin_dir)]))
        monkeypatch.setenv("PATHEXT", ".exe;.cmd")  # this host matches case
        return sys.modules["_ship_windows"], bin_dir

    def test_a_batch_target_gets_every_argument_quoted(self, windows):
        module, bin_dir = windows
        built = module.command(["az", "repos", "pr", "list", "--query", "[?a && b]"])
        assert built == f'"{bin_dir / "az.cmd"}" "repos" "pr" "list" "--query" "[?a && b]"'

    def test_the_cwd_and_relative_entries_are_never_searched(self, windows):
        module, bin_dir = windows
        assert module.find_program("az") == str(bin_dir / "az.cmd")

    def test_an_exe_target_stays_an_argument_list(self, windows):
        module, bin_dir = windows
        assert module.command(["git", "status"]) == [str(bin_dir / "git.exe"), "status"]

    @pytest.mark.parametrize(
        "arg", ["feat: %AZURE_DEVOPS_EXT_PAT%", "feat: hi!", 'a"b', "a\nb", "C:\\dir\\"]
    )
    def test_an_argument_cmd_would_rewrite_is_refused(self, windows, scripts, arg):
        module, _bin = windows
        assert module.command(["az", "--title", arg]) is None
        done = scripts[0].run(["az", "--title", arg])
        assert (done.returncode, done.stderr) == (
            126,
            "az: refused an argument cmd.exe would rewrite",
        )

    def test_a_path_is_unchanged(self, windows):
        module, _bin = windows
        assert module.command([sys.executable, "-I"]) == [sys.executable, "-I"]

    def test_an_unfound_name_is_refused_not_left_to_a_cwd_search(self, scripts, windows, tmp_path):
        module, _bin = windows
        with pytest.raises(FileNotFoundError):
            module.command(["gh", "x"])
        (tmp_path / "gh.exe").write_text("planted\n", encoding="utf-8")
        done = scripts[0].run(["gh", "x"], cwd=tmp_path)
        assert (done.returncode, done.stderr) == (127, "gh: not found")

    def test_posix_hosts_are_unchanged(self, scripts, monkeypatch):
        monkeypatch.setattr(scripts[0].os, "name", "posix")
        assert sys.modules["_ship_windows"].command(["az", "%x%"]) == ["az", "%x%"]


class TestPrivateDirectoryFailure:
    def test_a_temp_dir_failure_is_not_run(
        self, owner, base_validator, scripts, capsys, monkeypatch
    ):
        repo, body = owner
        base_validator(repo, VALIDATOR_PASS)
        checks = scripts[3].checks_mod

        def refuse(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(checks.tempfile, "TemporaryDirectory", refuse)
        code, lines = run_pr(
            scripts, capsys, "check", "--title", "feat(ship): x", "--body-file", str(body)
        )
        assert code == 0
        assert values(lines, "CHECK")[-1].startswith(
            "paths=NOT-RUN could not create a private directory (Permission denied)"
        )
        assert lines[-1] == "NEXT: compare-paths-by-hand"


class TestWindowsAdoTitleFailsBeforeThePush:
    ADO = "https://dev.azure.com/contoso/p/_git/r"

    @pytest.mark.parametrize(
        "title", ["feat(ship)!: drop the old flag", "perf: cut 50% latency", "fix: path C:\\x\\"]
    )
    def test_publish_stops_on_the_title_and_never_pushes(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, monkeypatch, title
    ):
        repo = make_repo(self.ADO)
        fakes.no_pr_ado()
        fakes.marker(0)
        body = body_file(repo)
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            title,
            "--body-file",
            str(body),
        )
        assert code == 1
        assert (
            "CHECK: title=FAIL title has %, !, a quote, or a trailing backslash, "
            "which cmd.exe rewrites for az" in lines
        )
        assert lines[-1].startswith("STOP: check-failed title")
        assert "PUSH: pushed" not in lines
        assert not fakes.calls("validate_pr_description")
        assert not [c for c in fakes.calls("az") if c[1:4] == ["repos", "pr", "create"]]

    def test_a_body_path_cmd_would_rewrite_fails_the_body_check(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        repo = make_repo(self.ADO)
        fakes.no_pr_ado()
        scratch = repo / ".project-toolkit" / "scratch"
        scratch.mkdir(parents=True)
        body = scratch / "pr-body-50%.md"
        body.write_text("## Summary\n\nChanges the ship skill.\n", encoding="utf-8")
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        _code, lines = run_pr(
            scripts, capsys, "check", "--title", "feat(ship): x", "--body-file", str(body)
        )
        assert (
            "CHECK: body=FAIL body file path has %, !, or a quote, which cmd.exe rewrites for az"
            in lines
        )

    def test_github_and_posix_titles_are_not_restricted(self, scripts, monkeypatch):
        checks = scripts[3].checks_mod
        assert checks.title_problem("perf: cut 50% latency") is None
        assert scripts[0].cmd_rewrites("perf: cut 50% latency") is True
        assert scripts[0].cmd_rewrites("feat: a & b | c") is False


class TestLabelledFailGroups:
    def test_failed_missing_and_pending_are_named_apart(self, scripts):
        data = {
            "RequiredState": "FAILURE",
            "FailedRequiredChecks": ["build"],
            "MissingRequiredChecks": ["docs"],
            "PendingRequiredChecks": [{"Name": "lint"}],
        }
        ctx = type("Ctx", (), {"head": "a" * 40})()
        check = sys.modules["_ship_pipeline"]._github_verdict(ctx, 3, 1, data)
        assert check.state == "FAIL"
        assert check.detail.endswith("failed=build missing=docs pending=lint")


class TestMissingBaseRef:
    def test_a_base_ref_that_was_never_fetched_says_so(self, owner, scripts, capsys):
        repo, body = owner
        git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        _code, lines = run_pr(
            scripts, capsys, "check", "--title", "feat(ship): x", "--body-file", str(body)
        )
        assert any(
            v.startswith("paths=NOT-RUN origin/main not found; fetch it")
            for v in values(lines, "CHECK")
        )


class TestRoundFiveFindings:
    @pytest.mark.parametrize("output_format", ["human", "json"])
    def test_a_narrow_code_page_still_prints_the_terminal_line(
        self, scripts, monkeypatch, tmp_path, output_format
    ):
        import io

        common = scripts[0]
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        monkeypatch.setattr(common.sys, "stdout", stream)
        result = common.Result("t.py", frozenset({"x-failed"}))
        result.add("PR_AUTHOR", "\u5c71\u7530")
        result.stop("x-failed", 3, "cause \u592a\u90ce")
        assert common.emit(result, output_format, tmp_path) == 3
        text = raw.getvalue().decode("cp1252")
        assert "x-failed cause ??" in text
        if output_format == "human":
            assert text.splitlines()[-1] == "STOP: x-failed cause ??"

    def test_a_stream_without_reconfigure_still_prints(self, scripts, monkeypatch, tmp_path):
        import io

        common = scripts[0]
        stream = io.StringIO()
        monkeypatch.setattr(common.sys, "stdout", stream)
        result = common.Result("t.py", frozenset({"x-failed"}))
        result.next("report")
        assert common.emit(result, "human", tmp_path) == 0
        assert stream.getvalue().splitlines()[-1] == "NEXT: report"

    def test_a_conflicting_pr_names_the_merge_state(self, scripts):
        data = {
            "RequiredState": "UNKNOWN",
            "AllPassing": False,
            "MergeRefUsable": False,
            "MergeState": "DIRTY",
            "MergeStateWarning": "the merge ref cannot be built: conflicts",
        }
        ctx = type("Ctx", (), {"head": "a" * 40})()
        check = sys.modules["_ship_pipeline"]._github_verdict(ctx, 12, 1, data)
        assert check.state == "FAIL"
        assert check.detail.endswith("merge_state=DIRTY (the merge ref cannot be built: conflicts)")

    def test_a_usable_merge_ref_adds_no_merge_state(self, scripts):
        data = {"RequiredState": "FAILURE", "MergeRefUsable": True, "MergeState": "CLEAN"}
        ctx = type("Ctx", (), {"head": "a" * 40})()
        check = sys.modules["_ship_pipeline"]._github_verdict(ctx, 12, 1, data)
        assert "merge_state" not in check.detail

    def test_a_merge_state_without_a_warning_still_names_the_state(self, scripts):
        data = {"RequiredState": "UNKNOWN", "MergeRefUsable": False, "MergeState": "DIRTY"}
        ctx = type("Ctx", (), {"head": "a" * 40})()
        check = sys.modules["_ship_pipeline"]._github_verdict(ctx, 12, 1, data)
        assert check.detail.endswith("merge_state=DIRTY")

    def test_ship_pr_has_one_windows_seam(self, scripts):
        assert not hasattr(scripts[3], "_IS_WINDOWS")
