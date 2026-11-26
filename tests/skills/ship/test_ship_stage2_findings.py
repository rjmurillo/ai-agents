"""Negative tests for the Stage-2 review findings on the ship scripts.

Each test failed, or could not be written, against the code before the fix.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    GITHUB,
    SCRIPTS,
    VALIDATOR_BRANCH_EDIT,
    VALIDATOR_PASS,
    invoke,
    publish,
    run_pr,
    symlink_or_skip,
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


class TestNoPublishFromABaseBranch:
    @pytest.mark.parametrize(
        ("branch", "base"), [("main", "develop"), ("master", None), ("develop", "develop")]
    )
    def test_draft_publish_from_a_base_branch_never_pushes(
        self, make_repo, fakes, scripts, capsys, body_file, tmp_path, branch, base
    ):
        repo = make_repo(GITHUB, branch=branch if branch != "main" else "main")
        if branch not in ("main",):
            git(repo, "switch", "-q", "-C", branch)
        fakes.no_pr_github()
        before = _remote_has(tmp_path, branch)
        extra = ["--draft"] + (["--base", base] if base else [])
        code, lines = publish(scripts, capsys, body_file(repo), *extra)
        assert code == 1
        assert lines[-1].startswith("STOP: on-base-branch")
        assert "PUSH: pushed" not in lines
        assert _remote_has(tmp_path, branch) == before


class TestValidatorRefCannotBeShadowed:
    def test_tag_named_like_the_base_never_supplies_the_validator(
        self, owner, base_validator, scripts, capsys, tmp_path, monkeypatch
    ):
        repo, body = owner
        base_validator(repo, VALIDATOR_PASS)
        branch = git(repo, "branch", "--show-current")
        git(repo, "switch", "-q", "-c", "shadow")
        path = repo / "scripts" / "validation" / "pr_description.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(VALIDATOR_BRANCH_EDIT, encoding="utf-8")
        git(repo, "add", "scripts")
        git(repo, "commit", "-q", "-m", "chore: shadow validator")
        git(repo, "tag", "origin/main")
        git(repo, "switch", "-q", branch)
        sentinel = tmp_path / "shadow-ran.txt"
        monkeypatch.setenv("SHIP_BRANCH_SENTINEL", str(sentinel))
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
        assert "paths=PASS" in values(lines, "CHECK")
        assert not sentinel.exists(), "the tag's validator ran"


class TestDeadlineIsBound:
    def _pending(self, make_repo, fakes):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {"number": 9, "state": "OPEN", "author": {"login": "me"}, "url": "u"}
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        fakes.rule(
            "gh",
            ["pr", "view", "9"],
            {
                "stdout": json.dumps(
                    {
                        "headRefName": "feat/ship-change",
                        "headRefOid": git(repo, "rev-parse", "HEAD"),
                    }
                )
            },
        )
        fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": "{}\n"})
        return repo

    def test_a_rerun_cannot_extend_the_window(self, make_repo, fakes, scripts, capsys):
        self._pending(make_repo, fakes)
        _code, first = invoke(scripts[2], ["--check", "pipeline"], capsys)
        printed = int(values(first, "PIPELINE_DEADLINE")[0])
        code, later = invoke(
            scripts[2], ["--check", "pipeline", "--deadline", str(printed + 600)], capsys
        )
        assert code == 2
        assert later[-1].startswith("STOP: bad-arguments --deadline")
        _code, omitted = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert int(values(omitted, "PIPELINE_DEADLINE")[0]) == printed
        _code, shorter = invoke(
            scripts[2], ["--check", "pipeline", "--deadline", str(printed - 60)], capsys
        )
        assert int(values(shorter, "PIPELINE_DEADLINE")[0]) == printed - 60

    def test_a_stored_deadline_in_the_past_fails(self, make_repo, fakes, scripts, capsys):
        repo = self._pending(make_repo, fakes)
        head = git(repo, "rev-parse", "HEAD")[:12]
        state = repo / ".project-toolkit" / "scratch"
        state.mkdir(parents=True, exist_ok=True)
        (state / f"ship-deadline-github-9-{head}.txt").write_text(
            str(int(time.time()) - 5), encoding="utf-8"
        )
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 1
        assert values(lines, "CHECK")[-1] == "pipeline=FAIL still pending after 30 minutes"

    def test_an_unreadable_state_file_starts_a_fresh_window(
        self, make_repo, fakes, scripts, capsys
    ):
        repo = self._pending(make_repo, fakes)
        head = git(repo, "rev-parse", "HEAD")[:12]
        state = repo / ".project-toolkit" / "scratch"
        state.mkdir(parents=True, exist_ok=True)
        (state / f"ship-deadline-github-9-{head}.txt").write_text("not a number", encoding="utf-8")
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 0
        assert int(values(lines, "PIPELINE_DEADLINE")[0]) > time.time()

    def test_a_corrupt_or_linked_state_file_is_not_trusted(
        self, make_repo, fakes, scripts, capsys, tmp_path
    ):
        repo = self._pending(make_repo, fakes)
        head = git(repo, "rev-parse", "HEAD")[:12]
        state = repo / ".project-toolkit" / "scratch"
        state.mkdir(parents=True, exist_ok=True)
        target = tmp_path / "elsewhere.txt"
        target.write_text("1", encoding="utf-8")
        symlink_or_skip(state / f"ship-deadline-github-9-{head}.txt", target)
        code, lines = invoke(scripts[2], ["--check", "pipeline"], capsys)
        assert code == 0
        assert int(values(lines, "PIPELINE_DEADLINE")[0]) > time.time()


class TestProcessFailuresEndOnStop:
    def test_a_binary_that_cannot_run_is_a_stop(
        self, make_repo, fakes, scripts, capsys, tmp_path, monkeypatch
    ):
        import shutil

        make_repo(GITHUB)
        gh = fakes.root / "bin" / "gh"
        gh.chmod(0o644)
        git_dir = tmp_path / "git-only"
        git_dir.mkdir()
        symlink_or_skip(git_dir / "git", Path(shutil.which("git")))
        monkeypatch.setenv("PATH", f"{fakes.root / 'bin'}{os.pathsep}{git_dir}")
        code, lines = invoke(scripts[1], [], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: pr-query-failed gh: cannot run")

    def test_run_reports_a_non_executable_file(self, scripts, tmp_path):
        target = tmp_path / "not-executable"
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o644)
        done = scripts[0].run([str(target)])
        assert done.returncode == 126
        assert "cannot run" in done.stderr

    def test_a_push_timeout_is_a_stop(self, owner, scripts, capsys, monkeypatch):
        _repo, body = owner
        common = scripts[0]
        real_git = common.git

        def slow(args, cwd=None, timeout=60):
            if args[:1] == ["push"]:
                assert timeout == 540
                return common.Completed(124, "", "git: timed out after 540s")
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", slow)
        code, lines = publish(scripts, capsys, body)
        assert code == 3
        assert lines[-1].startswith("STOP: push-failed push timed out after 540s")


class TestDefaultBase:
    def test_origin_master_is_the_fallback_base(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(GITHUB)
        git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
        git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        fakes.no_pr_github()
        _code, lines = invoke(scripts[1], [], capsys)
        assert values(lines, "BASE") == ["master"]

    def test_no_remote_default_falls_back_to_main(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(GITHUB)
        git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        fakes.no_pr_github()
        _code, lines = invoke(scripts[1], [], capsys)
        assert values(lines, "BASE") == ["main"]


class TestPipelineDetail:
    def _github(self, make_repo, fakes):
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

    def test_pending_without_a_wait_is_pending_not_fail(self, make_repo, fakes, scripts, capsys):
        self._github(make_repo, fakes)
        data = {"RequiredState": "PENDING", "AllPassing": False, "PendingRequiredChecks": ["ci"]}
        fakes.rule("get_pr_checks", [], {"stdout": json.dumps({"Data": data}) + "\n"})
        code, lines = invoke(
            scripts[2], ["--check", "pipeline", "--pr", "41", "--wait-seconds", "0"], capsys
        )
        assert code == 0
        assert values(lines, "CHECK")[0].startswith("pipeline=PENDING")
        assert lines[-1] == "NEXT: rerun-pipeline"

    def test_checks_query_failure_carries_the_helper_message(
        self, make_repo, fakes, scripts, capsys
    ):
        self._github(make_repo, fakes)
        envelope = {
            "Success": False,
            "Data": None,
            "Error": {"Message": "PR 41 not found", "Code": 2},
        }
        fakes.rule("get_pr_checks", [], {"rc": 2, "stdout": json.dumps(envelope) + "\n"})
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 3
        assert lines[-1] == "STOP: checks-query-failed get_pr_checks exit 2: PR 41 not found"

    def test_validator_config_error_carries_its_stderr(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        fakes.no_pr_github()
        fakes.rule(
            "validate_review_marker", [], {"rc": 2, "stderr": "[FAIL] invalid repo root: /x\n"}
        )
        code, lines = invoke(scripts[2], ["--check", "reviewed"], capsys)
        assert code == 2
        assert lines[-1] == "STOP: validator-config validator exit 2: [FAIL] invalid repo root: /x"


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
