"""Tests for github_core.orphaned_commits (issue #5447).

A pr-autofix session that escalates at the round cap can leave unpushed local
commits. PR #5344 carried three; one deleted a lefthook pre-push job and the
test that guarded it. These tests pin the read-only scan that names such
commits for a resuming session.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core import orphaned_commits as oc

LIVE = "a" * 40
SEP = "\x1e"


def _record(sha: str, subject: str, *files: tuple[str, ...]) -> str:
    body = "".join("\n" + "\t".join(fields) for fields in files)
    return f"{SEP}{sha}\t{subject}{body}\n"


class FakeGit:
    """Scripted git runner keyed on the subcommand."""

    def __init__(self, ancestor=0, log=(0, ""), show=(0, "")):
        self.ancestor, self.log, self.show = ancestor, log, show
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "merge-base":
            return self.ancestor, ""
        if args[0] == "log":
            return self.log
        return self.show


class TestParseLog:
    def test_parses_sha_subject_and_files(self):
        text = _record("b" * 40, "fix: thing", ("M", "a.py"), ("D", "b.py"))
        (commit,) = oc.parse_log(text)
        assert commit.sha == "b" * 40
        assert commit.subject == "fix: thing"
        assert commit.files == (("M", "a.py"), ("D", "b.py"))

    def test_empty_and_blank_records_are_skipped(self):
        assert oc.parse_log("") == []
        assert oc.parse_log(f"{SEP}\n{SEP}  \n") == []

    def test_commit_with_no_files(self):
        (commit,) = oc.parse_log(_record("c" * 40, "chore: empty"))
        assert commit.files == ()

    def test_malformed_file_line_is_ignored(self):
        text = f"{SEP}{'d' * 40}\tsubject\nnotabs\nM\tok.py\n"
        (commit,) = oc.parse_log(text)
        assert commit.files == (("M", "ok.py"),)

    def test_control_characters_in_subject_are_neutralized(self):
        (commit,) = oc.parse_log(_record("e" * 40, "bad\x1b[31m subject\r"))
        assert "\x1b" not in commit.subject
        assert "\r" not in commit.subject

    def test_rename_keeps_destination_path(self):
        text = _record("f" * 40, "mv", ("R100", "old.py", "new.py"))
        (commit,) = oc.parse_log(text)
        assert commit.files == (("R100", "new.py"),)


class TestClassify:
    def _commit(self, *files):
        return oc.Commit("1" * 40, "s", tuple(files))

    def test_lefthook_edit_is_wiring(self):
        result = oc.classify(self._commit(("M", "lefthook.yml")), FakeGit())
        assert result.risks == (oc.RISK_WIRING,)

    def test_workflow_edit_is_wiring(self):
        result = oc.classify(self._commit(("M", ".github/workflows/ci.yml")), FakeGit())
        assert oc.RISK_WIRING in result.risks

    def test_nested_pre_commit_config_is_wiring(self):
        result = oc.classify(self._commit(("A", "sub/.pre-commit-config.yaml")), FakeGit())
        assert oc.RISK_WIRING in result.risks

    def test_deleted_test_file_is_flagged(self):
        result = oc.classify(self._commit(("D", "tests/test_gate.py")), FakeGit())
        assert result.risks == (oc.RISK_TEST_FILE_DELETED,)

    def test_added_test_file_is_not_flagged(self):
        result = oc.classify(self._commit(("A", "tests/test_gate.py")), FakeGit())
        assert result.risks == ()

    def test_deleted_non_test_file_is_not_flagged(self):
        result = oc.classify(self._commit(("D", "src/app.py")), FakeGit())
        assert result.risks == ()

    def test_removed_test_definition_is_flagged(self):
        patch_text = (
            "--- a/tests/test_wiring.py\n+++ b/tests/test_wiring.py\n"
            "@@ -10,4 +9,0 @@\n"
            "-def test_a_named_pre_push_job_runs_the_zero_collection_guard():\n"
            "-    assert True\n"
        )
        git = FakeGit(show=(0, patch_text))
        result = oc.classify(self._commit(("M", "tests/test_wiring.py")), git)
        assert result.risks == (oc.RISK_TEST_DEFS_REMOVED,)
        assert git.calls[0][-2:] == ["--", "tests/test_wiring.py"]

    def test_renamed_test_definition_is_not_flagged(self):
        patch_text = "-def test_old():\n+def test_new():\n"
        git = FakeGit(show=(0, patch_text))
        result = oc.classify(self._commit(("M", "tests/test_wiring.py")), git)
        assert result.risks == ()

    def test_js_and_csharp_test_markers_count(self):
        patch_text = "-  it('works', () => {\n-  [Fact]\n+  it('new', () => {\n"
        git = FakeGit(show=(0, patch_text))
        result = oc.classify(self._commit(("M", "web/app.test.ts")), git)
        assert result.risks == (oc.RISK_TEST_DEFS_REMOVED,)

    def test_failed_show_is_not_flagged(self):
        git = FakeGit(show=(1, "-def test_x():\n"))
        result = oc.classify(self._commit(("M", "tests/test_wiring.py")), git)
        assert result.risks == ()

    def test_modified_non_test_file_skips_show(self):
        git = FakeGit()
        oc.classify(self._commit(("M", "src/app.py")), git)
        assert git.calls == []

    def test_incident_commit_gets_both_flags(self):
        patch_text = "-def test_a_named_pre_push_job_runs():\n"
        git = FakeGit(show=(0, patch_text))
        commit = self._commit(("M", "lefthook.yml"), ("M", "tests/test_wiring.py"))
        result = oc.classify(commit, git)
        assert result.risks == (oc.RISK_WIRING, oc.RISK_TEST_DEFS_REMOVED)


class TestScanUnpushed:
    def test_no_commits_ahead_is_clean(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, "")))
        assert report["status"] == "clean"
        assert report["commits"] == []
        assert report["warning"] == ""

    def test_commits_ahead_are_listed_with_warning(self):
        log = _record("b" * 40, "fix: threads", ("M", "src/a.py")) + _record(
            "c" * 40, "drop duplicate gate", ("M", "lefthook.yml")
        )
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, log)))
        assert report["status"] == "ahead"
        assert [c["sha"] for c in report["commits"]] == ["b" * 40, "c" * 40]
        assert report["commits"][1]["risks"] == [oc.RISK_WIRING]
        warning = str(report["warning"])
        assert "2 local commit(s) ahead of live PR head aaaaaaaaa" in warning
        assert "ccccccccc drop duplicate gate [touches CI or pre-push wiring]" in warning
        assert "bbbbbbbbb fix: threads\n" in warning
        assert "unverified input" in warning
        assert "with and without the commit" in warning

    def test_log_range_uses_live_head_and_bounded_count(self):
        git = FakeGit(log=(0, ""))
        oc.scan_unpushed_commits(LIVE, git)
        log_args = next(c for c in git.calls if c[0] == "log")
        assert log_args[-1] == f"{LIVE}..HEAD"
        assert f"--max-count={oc.MAX_COMMITS + 1}" in log_args

    def test_more_than_max_commits_is_truncated_to_newest(self):
        log = "".join(_record(f"{i:040x}", f"c{i}") for i in range(oc.MAX_COMMITS + 1))
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, log)))
        assert report["truncated"] is True
        assert len(report["commits"]) == oc.MAX_COMMITS
        assert report["commits"][0]["sha"] == f"{1:040x}"
        assert f"latest {oc.MAX_COMMITS} shown" in str(report["warning"])

    def test_exactly_max_commits_is_not_truncated(self):
        log = "".join(_record(f"{i:040x}", f"c{i}") for i in range(oc.MAX_COMMITS))
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(0, log)))
        assert report["truncated"] is False

    def test_diverged_branch_is_unverified(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(ancestor=1))
        assert report["status"] == "unverified"
        assert "not an ancestor" in str(report["reason"])
        assert "git log <live head>..HEAD" in str(report["warning"])

    def test_unknown_sha_locally_is_unverified(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(ancestor=128))
        assert report["status"] == "unverified"
        assert "exited 128" in str(report["reason"])

    def test_git_log_failure_is_unverified(self):
        report = oc.scan_unpushed_commits(LIVE, FakeGit(log=(128, "")))
        assert report["status"] == "unverified"
        assert "git log exited 128" in str(report["reason"])

    def test_non_sha_input_never_reaches_git(self):
        git = FakeGit()
        report = oc.scan_unpushed_commits("--output=/tmp/x", git)
        assert report["status"] == "unverified"
        assert git.calls == []

    @pytest.mark.parametrize(
        "value",
        [LIVE + "\n", "\n" + LIVE, LIVE + "\r\n", LIVE + " ", "a" * 6, "a" * 65, "g" * 40, ""],
    )
    def test_malformed_sha_never_reaches_git(self, value):
        git = FakeGit()
        report = oc.scan_unpushed_commits(value, git)
        assert report["status"] == "unverified"
        assert "not a commit SHA" in str(report["reason"])
        assert git.calls == []

    @pytest.mark.parametrize("value", ["a" * 7, "A" * 40, "0123456789abcdefABCDEF", "f" * 64])
    def test_well_formed_sha_reaches_git(self, value):
        git = FakeGit()
        oc.scan_unpushed_commits(value, git)
        assert git.calls[0][:2] == ["merge-base", "--is-ancestor"]


class TestScanIfEscalated:
    def test_not_escalated_is_not_checked_and_runs_no_git(self):
        git = FakeGit()
        report = oc.scan_if_escalated(False, LIVE, git)
        assert report["status"] == "not_checked"
        assert report["warning"] == ""
        assert git.calls == []

    def test_not_escalated_without_head_is_not_checked(self):
        assert oc.scan_if_escalated(False, None, FakeGit())["live_head"] == ""

    def test_escalated_without_live_head_is_unverified(self):
        report = oc.scan_if_escalated(True, None, FakeGit())
        assert report["status"] == "unverified"
        assert "unavailable" in str(report["reason"])
        assert "unknown" in str(report["warning"])

    def test_escalated_with_head_scans(self):
        log = _record("b" * 40, "x", ("M", "a.py"))
        report = oc.scan_if_escalated(True, LIVE, FakeGit(log=(0, log)))
        assert report["status"] == "ahead"


def _checkout(path):
    """Make ``path`` look like a git checkout to the worktree validator."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return str(path)


class TestWorktreeRunner:
    def test_runs_git_inside_the_given_worktree(self, tmp_path):
        worktree = _checkout(tmp_path / "pr-7")
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="out", stderr="")
        with patch.object(oc.subprocess, "run", return_value=done) as run:
            assert oc.worktree_runner(worktree)(["status"]) == (0, "out")
        assert run.call_args.args[0] == ["git", "-C", worktree, "status"]

    def test_launch_failure_maps_to_127(self, tmp_path):
        worktree = _checkout(tmp_path / "pr-7")
        with patch.object(oc.subprocess, "run", side_effect=FileNotFoundError("git")):
            assert oc.worktree_runner(worktree)(["status"]) == (127, "")

    def test_repository_selecting_variables_are_dropped_from_the_child_env(
        self, tmp_path, monkeypatch
    ):
        worktree = _checkout(tmp_path / "pr-7")
        for key in oc._GIT_ENV_KEYS:
            monkeypatch.setenv(key, "/shared/checkout")
        monkeypatch.setenv("HOME", "/home/keep")
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(oc.subprocess, "run", return_value=done) as run:
            oc.worktree_runner(worktree)(["status"])
        env = run.call_args.kwargs["env"]
        assert not set(oc._GIT_ENV_KEYS) & set(env)
        assert env["HOME"] == "/home/keep"

    def test_git_config_injection_variables_are_dropped_from_the_child_env(
        self, tmp_path, monkeypatch
    ):
        worktree = _checkout(tmp_path / "pr-7")
        injected = {
            "GIT_CONFIG_PARAMETERS": "'core.fsmonitor=evil'",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/tmp/evil",
            "GIT_CEILING_DIRECTORIES": "/",
        }
        for key, value in injected.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/home/keep/.gitconfig")
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/etc/keep-gitconfig")
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(oc.subprocess, "run", return_value=done) as run:
            oc.worktree_runner(worktree)(["status"])
        env = run.call_args.kwargs["env"]
        assert not set(injected) & set(env)
        assert env["GIT_CONFIG_GLOBAL"] == "/home/keep/.gitconfig"
        assert env["GIT_CONFIG_SYSTEM"] == "/etc/keep-gitconfig"

    def test_default_runner_keeps_the_inherited_environment(self):
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(oc.subprocess, "run", return_value=done) as run:
            oc.default_runner(["status"])
        assert run.call_args.kwargs["env"] is None

    def test_a_linked_worktree_git_file_is_accepted(self, tmp_path):
        worktree = tmp_path / "linked"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch.object(oc.subprocess, "run", return_value=done):
            assert oc.worktree_runner(str(worktree))(["status"]) == (0, "ok")

    def test_invalid_worktree_never_launches_git(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        a_file = tmp_path / "file"
        a_file.write_text("x", encoding="utf-8")
        bad = [
            "",
            "-C",
            "--upload-pack=evil",
            "bad\x00path",
            str(tmp_path / "missing"),
            str(plain),
            str(a_file),
        ]
        with patch.object(oc.subprocess, "run") as run:
            for value in bad:
                assert oc.worktree_runner(value)(["status"]) == (126, "")
        run.assert_not_called()

    def test_invalid_worktree_ends_the_scan_unverified_with_a_clear_reason(self, tmp_path):
        report = oc.scan_unpushed_commits(LIVE, oc.worktree_runner(str(tmp_path / "missing")))
        assert report["status"] == "unverified"
        assert "not a git checkout" in str(report["reason"])
        assert report["commits"] == []

    def test_scans_the_worktree_head_not_the_callers(self, tmp_path):
        def git(cwd, *args):
            return subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=cwd,
                capture_output=True,
                encoding="utf-8",
                check=True,
            ).stdout.strip()

        repo = tmp_path / "repo"
        shared = tmp_path / "shared"
        repo.mkdir()
        shared.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(shared, "init", "-q", "-b", "main")
        (repo / "a.txt").write_text("a")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "base")
        live = git(repo, "rev-parse", "HEAD")
        (repo / "b.txt").write_text("b")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "orphan")
        (shared / "z.txt").write_text("z")
        git(shared, "add", ".")
        git(shared, "commit", "-q", "-m", "unrelated")

        report = oc.scan_unpushed_commits(live, oc.worktree_runner(str(repo)))

        assert report["status"] == "ahead"
        assert [c["subject"] for c in report["commits"]] == ["orphan"]
        assert "orphan" in str(report["warning"])

    def test_inherited_git_dir_does_not_redirect_the_scan(self, tmp_path, monkeypatch):
        """GIT_DIR overrides ``-C``; the runner must drop it (issue #6506)."""

        def git(cwd, *args):
            return subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=cwd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout.strip()

        repo = tmp_path / "repo"
        shared = tmp_path / "shared"
        repo.mkdir()
        shared.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(shared, "init", "-q", "-b", "main")
        (repo / "a.txt").write_text("a")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "base")
        live = git(repo, "rev-parse", "HEAD")
        (repo / "b.txt").write_text("b")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "orphan")
        (shared / "z.txt").write_text("z")
        git(shared, "add", ".")
        git(shared, "commit", "-q", "-m", "unrelated")
        monkeypatch.setenv("GIT_DIR", str(shared / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(shared))

        report = oc.scan_unpushed_commits(live, oc.worktree_runner(str(repo)))

        assert report["status"] == "ahead"
        assert [c["subject"] for c in report["commits"]] == ["orphan"]

    def test_every_rev_parse_local_env_var_is_dropped(self):
        """``_GIT_ENV_KEYS`` must cover what git itself reports as repo-local."""
        reported = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.split()
        assert reported
        assert set(reported) <= set(oc._GIT_ENV_KEYS)

    def test_inherited_graft_file_does_not_shrink_the_commit_list(self, tmp_path, monkeypatch):
        """GIT_GRAFT_FILE rewires parents and hid the middle commit (issue #6506)."""

        def git(cwd, *args):
            return subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=cwd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout.strip()

        repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        shas = {}
        for name in ("a", "b", "c"):
            (repo / f"{name}.txt").write_text(name)
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", name)
            shas[name] = git(repo, "rev-parse", "HEAD")
        graft = tmp_path / "grafts"
        graft.write_text(f"{shas['c']} {shas['a']}\n", encoding="utf-8")
        monkeypatch.setenv("GIT_GRAFT_FILE", str(graft))

        report = oc.scan_unpushed_commits(shas["a"], oc.worktree_runner(str(repo)))

        assert report["status"] == "ahead"
        assert sorted(c["subject"] for c in report["commits"]) == ["b", "c"]


class TestDefaultRunner:
    def test_returns_exit_code_and_stdout(self):
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="out", stderr="")
        with patch.object(oc.subprocess, "run", return_value=done) as run:
            assert oc.default_runner(["status"]) == (0, "out")
        assert run.call_args.args[0] == ["git", "status"]

    def test_none_stdout_becomes_empty(self):
        done = subprocess.CompletedProcess(args=[], returncode=1, stdout=None, stderr="")
        with patch.object(oc.subprocess, "run", return_value=done):
            assert oc.default_runner(["status"]) == (1, "")

    def test_launch_failure_maps_to_127(self):
        with patch.object(oc.subprocess, "run", side_effect=FileNotFoundError("git")):
            assert oc.default_runner(["status"]) == (127, "")

    def test_real_git_reports_ancestry_in_a_scratch_repo(self, tmp_path, monkeypatch):
        def git(*args):
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )

        git("init", "-q", "-b", "main")
        (tmp_path / "a.txt").write_text("a")
        git("add", ".")
        git("commit", "-q", "-m", "base")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()
        (tmp_path / "lefthook.yml").write_text("pre-push: {}")
        git("add", ".")
        git("commit", "-q", "-m", "drop duplicate gate")
        monkeypatch.chdir(tmp_path)
        report = oc.scan_unpushed_commits(head)
        assert report["status"] == "ahead"
        (commit,) = report["commits"]
        assert commit["subject"] == "drop duplicate gate"
        assert commit["risks"] == [oc.RISK_WIRING]
