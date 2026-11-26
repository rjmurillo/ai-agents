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
    GITHUB,
    PR_URL,
    TITLE,
    assert_snapshot,
    fail_push,
    publish,
    run_pr,
    values,
)


class TestPublishGitHub:
    def test_pushes_then_creates_the_pr(self, owner, fakes, scripts, capsys, tmp_path):
        repo, body = owner
        code, lines = publish(
            scripts,
            capsys,
            body,
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
        publish(
            scripts,
            capsys,
            body,
        )
        assert git(repo, "rev-parse", "HEAD") == before

    def test_draft_skips_the_marker_and_opens_a_draft(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        fakes.marker(1)
        code, lines = publish(
            scripts,
            capsys,
            body,
            "--draft",
        )
        assert code == 0
        assert not fakes.calls("validate_review_marker")
        assert fakes.calls("new_pr")[0][-1] == "--draft"

    def test_unreviewed_head_stops_before_push(self, owner, fakes, scripts, capsys, tmp_path):
        _repo, body = owner
        fakes.marker(1)
        code, lines = publish(
            scripts,
            capsys,
            body,
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
        code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 2
        assert lines[-1].startswith("STOP: validator-config")

    def test_dirty_tree_stops(self, owner, scripts, capsys):
        repo, body = owner
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        code, lines = publish(
            scripts,
            capsys,
            body,
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
        code, lines = publish(
            scripts,
            capsys,
            body,
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
        publish(
            scripts,
            capsys,
            body,
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
            ("fatal: connect to host port 2403 refused\n", "push-failed", 3),
        ],
    )
    def test_push_failures_are_classified(
        self, owner, scripts, capsys, monkeypatch, stderr, reason, code
    ):
        _repo, body = owner
        fail_push(monkeypatch, scripts[0], stderr)
        exit_code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")

    @pytest.mark.parametrize(
        "response",
        [{"rc": 1, "stderr": "gh: GraphQL error\n"}, {"rc": 0, "stdout": "no url here\n"}],
    )
    def test_create_failure_stops_exit_3(self, owner, fakes, scripts, capsys, response):
        _repo, body = owner
        fakes.rule("new_pr", ["--title"], response)
        code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 3
        assert values(lines, "PUSH") == ["pushed"]
        assert lines[-1].startswith("STOP: pr-create-failed")

    def test_missing_new_pr_stops(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        (fakes.skills / "github" / "scripts" / "pr" / "new_pr.py").unlink()
        code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 2
        assert lines[-1].startswith("STOP: pr-create-failed")

    def test_windows_passes_the_body_text(self, owner, fakes, scripts, capsys, monkeypatch):
        _repo, body = owner
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        code, _lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 0
        create = fakes.calls("new_pr")[0]
        assert create[create.index("--body") + 1] == body.read_text(encoding="utf-8")
        assert "--body-file" not in create

    def test_a_pr_url_in_the_title_never_names_the_created_pr(self, owner, fakes, scripts, capsys):
        _repo, body = owner
        decoy = "https://github.com/o/r/pull/12"
        fakes.rule(
            "new_pr",
            ["--title"],
            {
                "stdout": f"Title: fix: revert {decoy}\n\nCreating PR...\n"
                "https://github.com/rjmurillo/ai-agents/pull/99\nPR created successfully!\n"
            },
        )
        code, lines = publish(scripts, capsys, body)
        assert code == 0
        assert values(lines, "PR") == [
            "host=github number=99 url=https://github.com/rjmurillo/ai-agents/pull/99"
        ]
