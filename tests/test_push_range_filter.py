"""Tests for push-range file filter (issue #4492).

lefthook computes {push_files} from @{push}...HEAD.  On the first push of a new
branch @{push} is unresolvable and lefthook falls back to a comparison that
can include upstream-only files.  That causes glob-gated E2E jobs (plugin-load-e2e,
hook-anchoring-e2e) to fire on files the branch never touched.

_push_range_changed_files() reads push refs from stdin and computes the actual
changed files using the push range spec from resolve_push_update, avoiding the
@{push} fallback entirely.

_any_glob_match() is a lightweight fnmatch filter that decides whether any file
in a set matches any of the job's globs.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_SCRIPTS))

from scripts.validation import git_hook_policy  # noqa: E402

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _init_repo(root: Path) -> str:
    """Initialise a bare git repo; return the initial commit SHA."""
    for args in (
        ("init", "-q", "-b", "main"),
        ("-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"),
    ):
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root), *args],
            check=True, capture_output=True,
        )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def _commit(root: Path, filename: str, content: str = "x") -> str:
    (root / filename).write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root),
         "add", filename],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root),
         "commit", "-qm", f"add {filename}"],
        check=True, capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


class TestPushRangeChangedFiles:
    """_push_range_changed_files returns the actual push range files."""

    def test_returns_branch_only_files(self, tmp_path: Path) -> None:
        """Positive: files added on the branch appear in the result."""
        base_sha = _init_repo(tmp_path)
        head_sha = _commit(tmp_path, "branch_file.py")

        # Simulate git pre-push stdin: local_ref local_sha remote_ref remote_sha
        stdin = io.StringIO(
            f"refs/heads/feature {head_sha} refs/heads/feature {base_sha}\n"
        )
        result = git_hook_policy._push_range_changed_files(stdin, tmp_path)

        assert result is not None
        assert "branch_file.py" in result

    def test_upstream_only_files_excluded(self, tmp_path: Path) -> None:
        """Positive: files added only to 'main' after the branch diverged do NOT
        appear.  This is the #4492 contamination scenario."""
        merge_base_sha = _init_repo(tmp_path)

        # 'Main' adds a file after the branch point.
        _commit(tmp_path, "upstream_skill.md")

        # 'Feature' branch diverges from merge_base_sha, not main_head.
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout", "-b", "feature", merge_base_sha],
            check=True, capture_output=True,
        )
        branch_head = _commit(tmp_path, "branch_file.py")

        # Push range: feature tip vs merge_base (not vs main tip).
        stdin = io.StringIO(
            f"refs/heads/feature {branch_head} refs/heads/feature {merge_base_sha}\n"
        )
        result = git_hook_policy._push_range_changed_files(stdin, tmp_path)

        assert result is not None
        assert "branch_file.py" in result
        assert "upstream_skill.md" not in result

    def test_empty_stdin_returns_none(self, tmp_path: Path) -> None:
        """Edge: no push refs on stdin (empty push) returns None so callers fail open."""
        stdin = io.StringIO("")
        result = git_hook_policy._push_range_changed_files(stdin, tmp_path)

        assert result is None

    def test_malformed_stdin_returns_none(self, tmp_path: Path) -> None:
        """Negative: malformed stdin returns None; callers must not silently skip."""
        stdin = io.StringIO("not valid push ref data\n")
        result = git_hook_policy._push_range_changed_files(stdin, tmp_path)

        assert result is None

    def test_deletion_ref_is_ignored(self, tmp_path: Path) -> None:
        """Edge: a deletion push (local_sha = all zeros) is skipped, not errored."""
        base_sha = _init_repo(tmp_path)
        zero_sha = "0" * 40
        stdin = io.StringIO(
            f"refs/heads/feature {zero_sha} refs/heads/feature {base_sha}\n"
        )
        # A deletion ref has no range to diff; the function skips it.
        # With only deletion refs, the result is an empty set (no changes found).
        # Callers treat an empty set as "no relevant files": the job is skipped.
        result = git_hook_policy._push_range_changed_files(stdin, tmp_path)

        assert result is not None
        assert len(result) == 0

    def test_preserves_a_tab_in_a_changed_path(self, tmp_path: Path) -> None:
        base_sha = _init_repo(tmp_path)
        filename = "branch\tfile.py"
        head_sha = _commit(tmp_path, filename)
        stdin = io.StringIO(
            f"refs/heads/feature {head_sha} refs/heads/feature {base_sha}\n"
        )

        result = git_hook_policy._push_range_changed_files(stdin, tmp_path)

        assert result == {filename}


class TestAnyGlobMatch:
    """_any_glob_match is a lightweight fnmatch filter."""

    def test_exact_match(self) -> None:
        """Positive: exact file name match returns True."""
        assert git_hook_policy._any_glob_match(
            {".claude/.claude-plugin/plugin.json"},
            (".claude/.claude-plugin/plugin.json",),
        )

    def test_wildcard_match(self) -> None:
        """Positive: ** glob matches nested paths."""
        assert git_hook_policy._any_glob_match(
            {".claude/skills/my-skill/SKILL.md"},
            (".claude/skills/**",),
        )

    def test_no_match(self) -> None:
        """Negative: no pattern matches any file returns False."""
        assert not git_hook_policy._any_glob_match(
            {"scripts/validation/some_file.py"},
            (".claude/skills/**", "src/copilot-cli/**"),
        )

    def test_empty_files(self) -> None:
        """Edge: empty file set never matches."""
        assert not git_hook_policy._any_glob_match(set(), (".claude/skills/**",))

    def test_empty_globs(self) -> None:
        """Edge: empty glob list never matches."""
        assert not git_hook_policy._any_glob_match({".claude/skills/x/SKILL.md"}, ())

    def test_cosmetic_control(self) -> None:
        """Cosmetic control: function exists and is callable.  Survives any
        whitespace mutation in the assertion so the mutation harness is
        measuring behaviour, not comment style."""
        result = git_hook_policy._any_glob_match({"a/b.py"}, ("a/*.py",))
        assert result is True


class TestHandleSessions:
    """The session gate consumes the actual push range rather than push_files."""

    def test_only_push_range_session_logs_are_validated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []
        monkeypatch.setattr(sys, "stdin", io.StringIO("push refs\n"))
        monkeypatch.setattr(
            git_hook_policy,
            "_push_range_changed_files",
            lambda _stream, _root: {
                ".agents/sessions/2026-08-10-session-1-branch.json",
                ".agents/sessions/upstream-only.json.bak",
                "README.md",
            },
        )

        def record_sessions(paths: list[str], _root: Path) -> int:
            seen.append(paths)
            return 0

        monkeypatch.setattr(
            git_hook_policy,
            "validate_branch_sessions",
            record_sessions,
        )
        monkeypatch.setattr(
            git_hook_policy,
            "_push_updates_match_head",
            lambda _payload, _root: True,
        )
        monkeypatch.setattr(
            git_hook_policy,
            "_session_paths_match_head",
            lambda _paths, _root: True,
        )
        args = type("Args", (), {"repo_root": str(tmp_path), "paths": []})()

        assert git_hook_policy._handle_sessions(args) == 0
        assert seen == [[".agents/sessions/2026-08-10-session-1-branch.json"]]

    def test_push_range_resolution_failure_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("malformed\n"))
        monkeypatch.setattr(
            git_hook_policy,
            "_push_range_changed_files",
            lambda _stream, _root: None,
        )
        args = type("Args", (), {"repo_root": str(tmp_path), "paths": []})()

        assert git_hook_policy._handle_sessions(args) == 2

    def test_off_head_push_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("push refs\n"))
        monkeypatch.setattr(
            git_hook_policy,
            "_push_range_changed_files",
            lambda _stream, _root: {
                ".agents/sessions/2026-08-10-session-1-branch.json"
            },
        )
        monkeypatch.setattr(
            git_hook_policy,
            "_push_updates_match_head",
            lambda _payload, _root: False,
        )
        args = type("Args", (), {"repo_root": str(tmp_path), "paths": []})()

        assert git_hook_policy._handle_sessions(args) == 2

    def test_dirty_session_file_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("push refs\n"))
        monkeypatch.setattr(
            git_hook_policy,
            "_push_range_changed_files",
            lambda _stream, _root: {
                ".agents/sessions/2026-08-10-session-1-branch.json"
            },
        )
        monkeypatch.setattr(
            git_hook_policy,
            "_push_updates_match_head",
            lambda _payload, _root: True,
        )
        monkeypatch.setattr(
            git_hook_policy,
            "_session_paths_match_head",
            lambda _paths, _root: False,
        )
        args = type("Args", (), {"repo_root": str(tmp_path), "paths": []})()

        assert git_hook_policy._handle_sessions(args) == 2

    def test_a_committed_session_symlink_does_not_match_head(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        target = tmp_path / "valid.json"
        target.write_text("{}\n", encoding="utf-8")
        link = sessions / "2026-08-10-session-1-link.json"
        link.symlink_to(target)
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", str(link.relative_to(tmp_path))],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git", "-c", "user.email=t@t", "-c", "user.name=t",
                "-C", str(tmp_path), "commit", "-qm", "add session link",
            ],
            check=True,
            capture_output=True,
        )

        assert not git_hook_policy._session_paths_match_head(
            [str(link.relative_to(tmp_path))],
            tmp_path,
        )


class TestHandleCliPluginE2eSkip:
    """_handle_cli_plugin_e2e skips when no relevant files in push range."""

    def _make_stdin_with_file(self, tmp_path: Path, filename: str) -> io.StringIO:
        """Return a stdin stream for a push that changed exactly one file."""
        for args in (
            ("init", "-q", "-b", "main"),
            ("-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "--allow-empty", "-m", "init"),
        ):
            subprocess.run(
                ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                 "-C", str(tmp_path), *args],
                check=True, capture_output=True,
            )
        (tmp_path / filename).write_text("x\n", encoding="utf-8")
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "-C", str(tmp_path), "add", filename],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "-C", str(tmp_path), "commit", "-qm", "add file"],
            check=True, capture_output=True,
        )
        head = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        parent = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD~1"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        return io.StringIO(
            f"refs/heads/feature {head} refs/heads/feature {parent}\n"
        )

    def test_skips_when_no_relevant_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Positive: an unrelated Python file triggers no plugin E2E run."""
        stdin_data = self._make_stdin_with_file(tmp_path, "scripts_only.py")
        run_called = {"n": 0}

        def fake_run_cli_e2e(test_file: str, repo_root: Any) -> int:
            run_called["n"] += 1
            return 0

        monkeypatch.setattr(git_hook_policy, "run_cli_e2e", fake_run_cli_e2e)
        monkeypatch.setattr("sys.stdin", stdin_data)

        import argparse
        args = argparse.Namespace(repo_root=str(tmp_path))
        rc = git_hook_policy._handle_cli_plugin_e2e(args)

        assert rc == 0
        assert run_called["n"] == 0
        assert "skipped" in capsys.readouterr().out.lower()

    def test_runs_when_relevant_file_in_range(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Positive: a skill file in the push range triggers the E2E run."""
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "skills").mkdir(exist_ok=True)
        stdin_data = self._make_stdin_with_file(tmp_path, ".claude/skills/foo.py")
        run_called = {"n": 0}

        def fake_run_cli_e2e(test_file: str, repo_root: Any) -> int:
            run_called["n"] += 1
            return 0

        monkeypatch.setattr(git_hook_policy, "run_cli_e2e", fake_run_cli_e2e)
        monkeypatch.setattr("sys.stdin", stdin_data)

        import argparse
        args = argparse.Namespace(repo_root=str(tmp_path))
        rc = git_hook_policy._handle_cli_plugin_e2e(args)

        assert rc == 0
        assert run_called["n"] == 1

