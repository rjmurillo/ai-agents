"""The live-head fetch and forged-record defense in orphaned_commits.py (issue #7032).

The fetch runs only for an escalated record in a named worktree, and only when git
lacks the live head. A commit subject is author text, so it must not start a record.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from test_orphaned_commits import LIVE, FakeGit

from scripts.github_core import orphaned_commits as oc


def _commit(*files: tuple[str, str]) -> oc.Commit:
    return oc.Commit(sha="b" * 40, subject="s", files=files)


class _Fetching:
    """A runner that scripts the presence probe and the fetch, and records calls."""

    def __init__(self, probe: int = 1, fetch: int = 0) -> None:
        self.probe, self.fetch = probe, fetch
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(args)
        if args[0] == "cat-file":
            return self.probe, ""
        if "fetch" in args:
            return self.fetch, ""
        return 0, ""

    def fetches(self) -> list[list[str]]:
        return [call for call in self.calls if "fetch" in call]


class TestFetchMissingHead:
    def test_absent_head_is_fetched_by_exact_sha(self) -> None:
        git = _Fetching()
        oc.scan_if_escalated(True, LIVE, git, pr_checkout=True)
        assert git.fetches() == [
            [
                "-c",
                f"core.hooksPath={os.devnull}",
                "fetch",
                "--quiet",
                "--no-tags",
                "--no-write-fetch-head",
                "--no-auto-maintenance",
                "--no-recurse-submodules",
                "--",
                "origin",
                LIVE,
            ]
        ]

    def test_present_head_is_not_fetched(self) -> None:
        git = _Fetching(probe=0)
        oc.scan_if_escalated(True, LIVE, git, pr_checkout=True)
        assert git.fetches() == []

    def test_no_named_worktree_never_fetches(self) -> None:
        git = _Fetching()
        oc.scan_if_escalated(True, LIVE, git, pr_checkout=False)
        assert git.calls and git.fetches() == []

    def test_a_value_that_is_not_a_sha_never_reaches_git(self) -> None:
        git = _Fetching()
        refspec = "+refs/heads/f:refs/heads/planted"
        report = oc.scan_if_escalated(True, refspec, git, pr_checkout=True)
        assert git.calls == []
        assert report["status"] == "unverified"

    def test_failed_fetch_is_reported_with_its_exit_code(self) -> None:
        report = oc.scan_if_escalated(True, LIVE, _Fetching(fetch=128), pr_checkout=True)
        assert report["status"] == "unverified"
        assert "git fetch exited 128" in str(report["reason"])
        assert "Fetch it by hand first" in str(report["warning"])

    def test_invalid_worktree_is_left_for_the_scan_to_report(self) -> None:
        git = _Fetching(probe=126)
        oc.scan_if_escalated(True, LIVE, git, pr_checkout=True)
        assert git.fetches() == []

    def test_stalled_fetch_ends_at_the_timeout(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            assert kwargs["timeout"] == 30
            if "fetch" in cmd:
                raise subprocess.TimeoutExpired(cmd, 30)
            return subprocess.CompletedProcess(cmd, 1, b"", b"")

        with patch("subprocess.run", side_effect=run):
            runner = oc.worktree_runner(str(tmp_path))
            report = oc.scan_if_escalated(True, LIVE, runner, pr_checkout=True)
        assert "git fetch timed out or could not start" in str(report["reason"])

    def test_worktree_runner_refuses_credential_prompts(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        done = subprocess.CompletedProcess(["git"], 0, b"", b"")
        with patch("subprocess.run", return_value=done) as run:
            oc.worktree_runner(str(tmp_path))(["status"])
        assert run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


class TestForgedRecords:
    """A commit subject is author text, so it must not start a record (CWE-88)."""

    def test_separator_in_a_subject_does_not_start_a_record(self) -> None:
        text = f"\x1e{'b' * 40}\tx\x1e--output=/tmp/f\n\nM\ttests/test_a.py\n"
        commits = oc.parse_log(text)
        assert [c.sha for c in commits] == ["b" * 40]
        assert commits[0].files == (("M", "tests/test_a.py"),)
        assert "\x1e" not in commits[0].subject

    def test_subject_shaped_like_a_record_stays_in_its_commit(self) -> None:
        forged = f"x\x1e{'c' * 40}\ttidy"
        commits = oc.parse_log(f"\x1e{'b' * 40}\t{forged}\n\nM\ttests/test_a.py\n")
        assert [c.sha for c in commits] == ["b" * 40]
        assert commits[0].files == (("M", "tests/test_a.py"),)

    def test_git_show_ends_options_before_the_sha(self) -> None:
        git = FakeGit(show=(0, ""))
        oc.classify(_commit(("M", "tests/test_a.py")), git)
        show = next(call for call in git.calls if call[0] == "show")
        assert show.index("--end-of-options") == show.index("b" * 40) - 1

    def test_carriage_return_subject_keeps_the_risk_flag_on_a_real_repo(
        self, tmp_path: Path
    ) -> None:
        # ``git commit`` cleans a message, so ``commit-tree`` is the path to prove here.
        def git(*args: str, stdin: str | None = None) -> str:
            ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
            done = subprocess.run(
                ["git", "-C", str(tmp_path), *ident, *args],
                check=True,
                capture_output=True,
                input=stdin,
                encoding="utf-8",
                errors="replace",
            )
            return done.stdout.strip()

        tests = tmp_path / "tests"
        tests.mkdir()
        git("init", "-q", "-b", "main")
        (tests / "test_x.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "base")
        base = git("rev-parse", "HEAD")
        (tests / "test_x.py").write_text("# none\n", encoding="utf-8")
        git("add", ".")
        tree = git("write-tree")
        forged = git("commit-tree", tree, "-p", base, stdin=f"x\r\x1e{base}\tfake\n")
        git("reset", "-q", "--hard", forged)

        report = oc.scan_unpushed_commits(base, oc.worktree_runner(str(tmp_path)))

        commits = report["commits"]
        assert isinstance(commits, list)
        assert [c["sha"] for c in commits] == [forged]
        assert commits[0]["risks"] == [oc.RISK_TEST_DEFS_REMOVED]

    def test_forged_subject_writes_no_file_on_a_real_repo(self, tmp_path: Path) -> None:
        def git(*args: str) -> str:
            ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
            done = subprocess.run(
                ["git", "-C", str(tmp_path), *ident, *args],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
            return done.stdout.strip()

        target = tmp_path / "planted.txt"
        tests = tmp_path / "tests"
        tests.mkdir()
        git("init", "-q", "-b", "main")
        (tests / "test_x.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "base")
        base = git("rev-parse", "HEAD")
        (tests / "test_x.py").write_text("def test_b():\n    pass\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", f"x\x1e--output={target}")

        report = oc.scan_unpushed_commits(base, oc.worktree_runner(str(tmp_path)))

        assert not target.exists()
        commits = report["commits"]
        assert isinstance(commits, list)
        assert [c["risks"] for c in commits] == [[oc.RISK_TEST_DEFS_REMOVED]]


def test_diverged_warning_keeps_the_truncation_label() -> None:
    warning = oc.render_warning(LIVE, [_commit()], True, diverged=True)
    assert f"(latest {oc.MAX_COMMITS} shown)" in warning
