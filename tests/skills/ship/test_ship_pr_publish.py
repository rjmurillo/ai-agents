"""Behavior tests for ship_pr.py publish on GitHub and Azure DevOps.

Pushes go to a real bare repository through ``pushInsteadOf``. ``gh``, ``az``,
and the helper scripts are fakes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    ADO,
    GITHUB,
    PR_URL,
    TITLE,
    ado_created,
    assert_snapshot,
    run_pr,
    values,
)


class TestPublishGitHub:
    def test_pushes_then_creates_the_pr(self, owner, fakes, scripts, capsys, tmp_path):
        repo, body = owner
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
        assert code == 0, lines
        assert values(lines, "PUSH") == ["pushed"]
        assert values(lines, "PR") == [f"host=github number=501 url={PR_URL}"]
        assert lines[-1] == "NEXT: discharge"
        remote_head = git(tmp_path / "remote.git", "rev-parse", "refs/heads/feat/ship-change")
        assert remote_head == git(repo, "rev-parse", "HEAD")
        create = fakes.calls("new_pr")[0]
        assert create[1:6] == ["--title", TITLE, "--base", "main", "--body-file"]
        assert_snapshot(Path(create[6]), body)

    def test_never_creates_a_commit(self, owner, scripts, capsys):
        repo, body = owner
        before = git(repo, "rev-parse", "HEAD")
        run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
        )
        assert git(repo, "rev-parse", "HEAD") == before

    def test_draft_skips_the_marker_and_opens_a_draft(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.marker(1)
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
            "--draft",
        )
        assert code == 0
        assert not fakes.calls("validate_review_marker")
        assert fakes.calls("new_pr")[0][-1] == "--draft"

    def test_unreviewed_head_stops_before_push(self, owner, fakes, scripts, capsys, tmp_path):
        _repo, body = owner
        fakes.marker(1)
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
        assert code == 1
        assert lines[-1].startswith("STOP: head-not-reviewed")
        assert "PUSH: pushed" not in lines
        assert not fakes.calls("new_pr")
        done = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "refs/heads/feat/ship-change"],
            cwd=tmp_path / "remote.git",
            capture_output=True,
            check=False,
        )
        assert done.returncode != 0

    def test_validator_config_error_stops(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.marker(2)
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
        assert code == 2
        assert lines[-1].startswith("STOP: validator-config")

    def test_dirty_tree_stops(self, owner, scripts, capsys):
        repo, body = owner
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
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
        assert code == 1
        assert lines[-1].startswith("STOP: tree-dirty")

    def test_failed_check_stops_before_push(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            "bad title",
            "--body-file",
            str(body),
        )
        assert code == 1
        assert lines[-1].startswith("STOP: check-failed title")
        assert "PUSH: pushed" not in lines

    def test_contributor_mode_stops(self, make_repo, fakes, scripts, capsys, body_file):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {"number": 3, "state": "OPEN", "author": {"login": "alice"}, "url": "u"}
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "bob\n"})
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body_file(repo)),
        )
        assert code == 1
        assert lines[-1].startswith("STOP: contributor-mode")

    def test_existing_pr_pushes_without_creating(
        self, make_repo, fakes, scripts, capsys, body_file
    ):
        repo = make_repo(GITHUB)
        fakes.rule(
            "gh",
            ["pr", "view"],
            {
                "stdout": json.dumps(
                    {
                        "number": 7,
                        "state": "OPEN",
                        "author": {"login": "me"},
                        "url": "https://x/pull/7",
                    }
                )
            },
        )
        fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
        fakes.marker(0)
        code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body_file(repo)),
        )
        assert code == 0
        assert values(lines, "PR") == ["host=github number=7 url=https://x/pull/7 existing"]
        assert not fakes.calls("new_pr")

    def test_rejected_push_stops_for_a_human_and_never_forces(
        self, owner, fakes, scripts, capsys, tmp_path
    ):
        repo, body = owner
        other = tmp_path / "other"
        subprocess.run(["git", "clone", "-q", str(tmp_path / "remote.git"), str(other)], check=True)
        git(other, "switch", "-q", "-c", "feat/ship-change")
        (other / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "chore: remote change")
        git(other, "commit", "--allow-empty", "-q", "-m", "chore: second remote change")
        (repo / "local.txt").write_text("local\n", encoding="utf-8")
        git(repo, "add", "local.txt")
        git(repo, "commit", "-q", "-m", "chore: local change")
        git(other, "push", "-q", "origin", "feat/ship-change")
        remote_before = git(tmp_path / "remote.git", "rev-parse", "refs/heads/feat/ship-change")
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
        assert code == 1
        assert lines[-1].startswith("STOP: push-rejected")
        assert "force push is a human action" in lines[-1]
        assert (
            git(tmp_path / "remote.git", "rev-parse", "refs/heads/feat/ship-change")
            == remote_before
        )
        assert not fakes.calls("new_pr")

    def test_push_argv_is_fixed_and_never_forced(self, owner, scripts, capsys, monkeypatch):
        repo, body = owner
        common = scripts[0]
        seen: list[list[str]] = []
        real_git = common.git

        def spy(args, cwd=None, timeout=60):
            seen.append(list(args))
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", spy)
        run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
        )
        pushes = [args for args in seen if args[:1] == ["push"]]
        assert pushes == [
            [
                "push",
                "--set-upstream",
                "origin",
                "refs/heads/feat/ship-change:refs/heads/feat/ship-change",
            ]
        ]
        assert not any(arg.startswith(("+", "--force", "-f")) for arg in pushes[0])

    @pytest.mark.parametrize(
        ("stderr", "reason", "code"),
        [
            ("fatal: Authentication failed for 'https://github.com/'\n", "auth-failed", 4),
            ("fatal: unable to access: Could not resolve host\n", "push-failed", 3),
            ("", "push-failed", 3),
        ],
    )
    def test_push_failures_are_classified(
        self, owner, scripts, capsys, monkeypatch, stderr, reason, code
    ):
        _repo, body = owner
        common = scripts[0]
        real_git = common.git

        def failing(args, cwd=None, timeout=60):
            if args[:1] == ["push"]:
                return common.Completed(128, "", stderr)
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", failing)
        exit_code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
        )
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")

    def test_bare_403_in_stderr_is_not_an_auth_failure(self, owner, scripts, capsys, monkeypatch):
        _repo, body = owner
        common = scripts[0]
        real_git = common.git

        def failing(args, cwd=None, timeout=60):
            if args[:1] == ["push"]:
                return common.Completed(128, "", "fatal: connect to host port 2403 refused\n")
            return real_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(common, "git", failing)
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
        assert code == 3
        assert lines[-1].startswith("STOP: push-failed")

    @pytest.mark.parametrize(
        "response",
        [{"rc": 1, "stderr": "gh: GraphQL error\n"}, {"rc": 0, "stdout": "no url here\n"}],
    )
    def test_create_failure_stops_exit_3(self, owner, fakes, scripts, capsys, response):
        _repo, body = owner
        fakes.rule("new_pr", ["--title"], response)
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
        assert code == 3
        assert values(lines, "PUSH") == ["pushed"]
        assert lines[-1].startswith("STOP: pr-create-failed")

    def test_missing_new_pr_stops(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        (fakes.skills / "github" / "scripts" / "pr" / "new_pr.py").unlink()
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
        assert code == 2
        assert lines[-1].startswith("STOP: pr-create-failed")

    def test_windows_passes_the_body_text(self, owner, fakes, scripts, capsys, monkeypatch):
        _repo, body = owner
        monkeypatch.setattr(scripts[3], "_IS_WINDOWS", True)
        code, _lines = run_pr(
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
        create = fakes.calls("new_pr")[0]
        assert create[create.index("--body") + 1] == body.read_text(encoding="utf-8")
        assert "--body-file" not in create


class TestPublishAdo:
    @pytest.fixture
    def ado(self, make_repo, fakes, body_file):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        fakes.marker(0)
        fakes.rule("validate_pr_description", [], {"stdout": ""})
        return repo, body_file(repo)

    def test_create_uses_the_fixed_argument_list(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], ado_created())
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
        assert code == 0, lines
        assert values(lines, "PR") == [
            "host=ado number=88 url=https://dev.azure.com/c/p/_git/r/pullrequest/88"
        ]
        create = [call for call in fakes.calls("az") if call[1:4] == ["repos", "pr", "create"]][0]
        assert create[1:] == [
            "repos",
            "pr",
            "create",
            "--output",
            "json",
            "--title",
            TITLE,
            "--description",
            create[9],
            "--target-branch",
            "main",
            "--draft",
            "false",
        ]
        assert sum(arg.startswith("@") for arg in create) == 1
        assert_snapshot(Path(create[9][1:]), body)

    def test_draft_flag_reaches_az(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.marker(1)
        fakes.rule("az", ["repos", "pr", "create"], ado_created())
        code, _lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
            "--draft",
        )
        assert code == 0
        create = [call for call in fakes.calls("az") if call[1:4] == ["repos", "pr", "create"]][0]
        assert create[-2:] == ["--draft", "true"]

    def test_at_fallback_description_stops_exit_3_and_names_the_pr(
        self, ado, fakes, scripts, capsys
    ):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], ado_created(description=f"@{body}"))
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
        assert code == 3
        assert values(lines, "PR")[0].startswith("host=ado number=88")
        assert lines[-1].startswith("STOP: description-upload-failed PR 88 is open")

    @pytest.mark.parametrize(
        ("response", "reason", "code"),
        [
            ({"rc": 1, "stderr": "TF401019\n"}, "pr-create-failed", 3),
            ({"rc": 1, "stderr": "Please run 'az login'\n"}, "auth-failed", 4),
            ({"stdout": "{}"}, "pr-create-failed", 3),
        ],
    )
    def test_create_failures(self, ado, fakes, scripts, capsys, response, reason, code):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], response)
        exit_code, lines = run_pr(
            scripts,
            capsys,
            "publish",
            "--paths-checked-by-hand",
            "--title",
            TITLE,
            "--body-file",
            str(body),
        )
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")

    def test_missing_web_url_reports_unknown(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.rule(
            "az",
            ["repos", "pr", "create"],
            {"stdout": json.dumps({"pullRequestId": 4, "description": "ok"})},
        )
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
        assert values(lines, "PR") == ["host=ado number=4 url=unknown"]
