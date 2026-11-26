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
                    {"number": 5, "state": "OPEN", "author": {"login": "me"}, "url": "u"}
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

    def test_an_unfound_name_or_a_path_is_unchanged(self, windows):
        module, _bin = windows
        assert module.command(["gh", "x"]) == ["gh", "x"]
        assert module.command([sys.executable, "-I"]) == [sys.executable, "-I"]

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
