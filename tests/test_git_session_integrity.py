"""Tests for git/session integrity (#4316, #4307, #4288).

Issue #4561's branch-discriminator tests were removed along with
new_session_log.py when the session-init skill was deleted (Issue #5138);
no surviving implementation exists to test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import warnings as _w
from datetime import UTC, datetime
from pathlib import Path

# Add the scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "validation"))


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"},
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create a bare origin and a clone as the working repo.

    Explicitly sets the default branch to ``main`` so the fixture is
    independent of the runner's ``init.defaultBranch`` setting.
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(["init", "--bare", "-b", "main"], str(origin))
    repo = tmp_path / "repo"
    _git(["clone", str(origin), str(repo)], str(tmp_path))
    _git(["config", "user.email", "t@t.com"], str(repo))
    _git(["config", "user.name", "Test"], str(repo))
    # Create initial commit on main and push so origin/main exists
    _git(["checkout", "-b", "main"], str(repo))
    (repo / "README.md").write_text("init\n")
    _git(["add", "README.md"], str(repo))
    _git(["commit", "-m", "initial"], str(repo))
    _git(["push", "origin", "main"], str(repo))
    return repo


# Issue #4316: Detect push to squash-merged branch


class TestSquashMergeDetection:
    """Tests for _is_branch_squash_merged."""

    def test_detects_squash_merged_branch(self, tmp_path: Path) -> None:
        """A push to a branch whose content is already on main via squash is blocked."""
        repo = _init_repo(tmp_path)

        # Create feature branch with a commit
        _git(["checkout", "-b", "feature/x"], str(repo))
        (repo / "feature.py").write_text("print('hello')\n")
        _git(["add", "feature.py"], str(repo))
        _git(["commit", "-m", "feat: add feature"], str(repo))
        _git(["push", "origin", "feature/x"], str(repo))

        # Simulate squash-merge: apply same content to main directly
        _git(["checkout", "main"], str(repo))
        (repo / "feature.py").write_text("print('hello')\n")
        _git(["add", "feature.py"], str(repo))
        _git(["commit", "-m", "feat: add feature (#1)"], str(repo))
        _git(["push", "origin", "main"], str(repo))

        # Go back to feature branch, add a new commit (the one that would be lost)
        _git(["checkout", "feature/x"], str(repo))
        _git(["fetch", "origin"], str(repo))
        (repo / "extra.py").write_text("# extra\n")
        _git(["add", "extra.py"], str(repo))
        _git(["commit", "-m", "fix: extra hardening"], str(repo))

        # Now test: the push should detect squash-merge
        from git_hook_policy import PushRef, _is_branch_squash_merged

        local_sha = _git(["rev-parse", "HEAD"], str(repo)).stdout.strip()
        remote_sha = _git(["rev-parse", "origin/feature/x"], str(repo)).stdout.strip()
        push_ref = PushRef(
            local_ref="refs/heads/feature/x",
            local_sha=local_sha,
            remote_ref="refs/heads/feature/x",
            remote_sha=remote_sha,
        )
        result = _is_branch_squash_merged(push_ref, Path(repo))
        assert result.lost_commits is not None, "Should detect squash-merged branch"
        assert len(result.lost_commits) >= 1, "Should report at least one lost commit"
        assert result.warning is None

    def test_normal_branch_not_blocked(self, tmp_path: Path) -> None:
        """A normal push to a branch whose PR has not merged passes."""
        repo = _init_repo(tmp_path)

        # Create feature branch
        _git(["checkout", "-b", "feature/y"], str(repo))
        (repo / "new.py").write_text("# new\n")
        _git(["add", "new.py"], str(repo))
        _git(["commit", "-m", "feat: new thing"], str(repo))
        _git(["push", "origin", "feature/y"], str(repo))

        # Add another commit
        (repo / "new.py").write_text("# updated\n")
        _git(["add", "new.py"], str(repo))
        _git(["commit", "-m", "fix: update"], str(repo))

        from git_hook_policy import PushRef, _is_branch_squash_merged

        _git(["fetch", "origin"], str(repo))
        local_sha = _git(["rev-parse", "HEAD"], str(repo)).stdout.strip()
        remote_sha = _git(["rev-parse", "origin/feature/y"], str(repo)).stdout.strip()
        push_ref = PushRef(
            local_ref="refs/heads/feature/y",
            local_sha=local_sha,
            remote_ref="refs/heads/feature/y",
            remote_sha=remote_sha,
        )
        result = _is_branch_squash_merged(push_ref, Path(repo))
        assert result.lost_commits is None, "Normal branch should not be flagged"
        assert result.warning is None

    def test_new_branch_not_blocked(self, tmp_path: Path) -> None:
        """A brand new branch (first push) is never flagged."""
        from git_hook_policy import PushRef, _is_branch_squash_merged

        repo = _init_repo(tmp_path)
        push_ref = PushRef(
            local_ref="refs/heads/new-branch",
            local_sha="abc123",
            remote_ref="refs/heads/new-branch",
            remote_sha="0" * 40,
        )
        result = _is_branch_squash_merged(push_ref, Path(repo))
        assert result.lost_commits is None
        assert result.warning is None

    def test_indeterminate_produces_warning(self, tmp_path: Path) -> None:
        """When merge-base computation fails, a warning is produced (not silent)."""
        repo = _init_repo(tmp_path)

        # Create a branch and push it
        _git(["checkout", "-b", "feature/z"], str(repo))
        (repo / "z.py").write_text("z\n")
        _git(["add", "z.py"], str(repo))
        _git(["commit", "-m", "feat: z"], str(repo))
        _git(["push", "origin", "feature/z"], str(repo))

        # Add a second commit so local != remote (not a no-op push)
        (repo / "z2.py").write_text("z2\n")
        _git(["add", "z2.py"], str(repo))
        _git(["commit", "-m", "feat: z2"], str(repo))

        # Delete the origin/main ref directly so merge-base will fail
        _git(["update-ref", "-d", "refs/remotes/origin/main"], str(repo))

        from git_hook_policy import PushRef, _is_branch_squash_merged

        local_sha = _git(["rev-parse", "HEAD"], str(repo)).stdout.strip()
        remote_sha = _git(["rev-parse", "origin/feature/z"], str(repo)).stdout.strip()
        push_ref = PushRef(
            local_ref="refs/heads/feature/z",
            local_sha=local_sha,
            remote_ref="refs/heads/feature/z",
            remote_sha=remote_sha,
        )
        result = _is_branch_squash_merged(push_ref, Path(repo))
        # Should not block (no lost_commits) but should warn
        assert result.lost_commits is None
        assert result.warning is not None, "Indeterminate state must produce a warning"
        assert "origin/main" in result.warning or "Cannot determine" in result.warning


# Issue #4307: Merge commits exempt from atomic-commit limit


class TestMergeCommitAtomicExempt:
    """Tests for check_atomic_commit merge-brought file exemption."""

    def test_merge_brought_files_excluded(self, tmp_path: Path) -> None:
        """During a merge, files from the merge parent are not counted."""
        repo = _init_repo(tmp_path)

        # Add many files to main (simulating upstream changes)
        _git(["checkout", "main"], str(repo))
        for i in range(8):
            (repo / f"upstream_{i}.py").write_text(f"# file {i}\n")
        _git(["add", "."], str(repo))
        _git(["commit", "-m", "chore: upstream changes"], str(repo))

        # Create feature branch from BEFORE those changes
        _git(["checkout", "-b", "feature/merge-test", "HEAD~1"], str(repo))
        (repo / "my_change.py").write_text("# my work\n")
        _git(["add", "my_change.py"], str(repo))
        _git(["commit", "-m", "feat: my work"], str(repo))

        # Merge main into feature branch
        _git(["merge", "main", "--no-edit"], str(repo))

        # Now the index has all the merge-brought files staged.
        # _merge_brought_paths should identify them.
        from git_hook_policy import _merge_brought_paths

        # We need to be mid-merge for MERGE_HEAD to exist. Let's create a
        # merge conflict scenario instead.
        # Actually after a successful merge, MERGE_HEAD is gone. We need to
        # test the function by simulating MERGE_HEAD presence.
        # Let's create a conflicting merge instead.
        _git(["reset", "--hard", "HEAD~1"], str(repo))

        # Create a conflict
        _git(["checkout", "main"], str(repo))
        (repo / "conflict.py").write_text("main version\n")
        _git(["add", "conflict.py"], str(repo))
        _git(["commit", "-m", "add conflict file"], str(repo))

        _git(["checkout", "feature/merge-test"], str(repo))
        (repo / "conflict.py").write_text("branch version\n")
        _git(["add", "conflict.py"], str(repo))
        _git(["commit", "-m", "add conflict file branch"], str(repo))

        # Start merge (will conflict)
        _git(["merge", "main", "--no-commit"], str(repo))

        # Resolve conflict (author's change)
        (repo / "conflict.py").write_text("resolved version\n")
        _git(["add", "conflict.py"], str(repo))
        # Also stage the upstream files (git does this automatically)
        _git(["add", "."], str(repo))

        # Now MERGE_HEAD exists. Test _merge_brought_paths.
        staged_files = []
        diff_result = _git(
            ["diff", "--cached", "--name-only", "--diff-filter=ACMRD"], str(repo)
        )
        staged_files = [f for f in diff_result.stdout.splitlines() if f.strip()]

        brought = _merge_brought_paths(Path(repo), staged_files)
        # upstream_* files should be "brought in" (identical to MERGE_HEAD)
        # conflict.py should NOT be brought in (author resolved it differently)
        assert "conflict.py" not in brought, "Author-resolved file should not be exempt"
        # At least some upstream files should be exempt
        upstream_brought = [f for f in brought if f.startswith("upstream_")]
        assert len(upstream_brought) > 0, "Merge-brought upstream files should be exempt"

    def test_no_merge_no_exemption(self, tmp_path: Path) -> None:
        """Without MERGE_HEAD, no files are exempted as merge-brought."""
        repo = _init_repo(tmp_path)
        (repo / "a.py").write_text("# a\n")
        _git(["add", "a.py"], str(repo))

        from git_hook_policy import _merge_brought_paths

        brought = _merge_brought_paths(Path(repo), ["a.py"])
        assert brought == set(), "No merge in progress means no exemptions"


# Issue #4288: Session log selector tie-break unification


class TestSessionLogSelectorTieBreak:
    """Tests for _session_log_for_branch using mtime-newest tie-break."""

    def _make_session_log(
        self, sessions_dir: Path, name: str, branch: str, mtime_offset: float = 0
    ) -> Path:
        """Create a minimal session log JSON file."""
        path = sessions_dir / name
        data = {"session": {"branch": branch, "number": 1}}
        path.write_text(json.dumps(data))
        # Set mtime
        base_time = time.time() + mtime_offset
        os.utime(path, (base_time, base_time))
        return path

    def test_returns_newest_when_multiple_match(self, tmp_path: Path) -> None:
        """When two logs match the same branch, the newest by mtime wins."""

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        # Create two logs for the same branch with different mtimes
        self._make_session_log(
            sessions_dir, f"{today}-session-1.json", "fix/test", mtime_offset=-100
        )
        newer = self._make_session_log(
            sessions_dir, f"{today}-session-2.json", "fix/test", mtime_offset=0
        )

        from git_hook_policy import _session_log_for_branch

        result = _session_log_for_branch(sessions_dir, "fix/test")
        assert result == newer, (
            f"Should return newer log ({newer.name}), got {result.name if result else None}"
        )

    def test_returns_none_when_no_match(self, tmp_path: Path) -> None:
        """Returns None when no log matches the branch."""

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        self._make_session_log(sessions_dir, f"{today}-session-1.json", "other/branch")

        from git_hook_policy import _session_log_for_branch

        result = _session_log_for_branch(sessions_dir, "fix/nonexistent")
        assert result is None

    def test_returns_none_when_no_candidates(self, tmp_path: Path) -> None:
        """Returns None for an empty sessions directory."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        from git_hook_policy import _session_log_for_branch

        result = _session_log_for_branch(sessions_dir, "any-branch")
        assert result is None

    def test_does_not_return_wrong_branch_log(self, tmp_path: Path) -> None:
        """Absent branch identity must NOT return another session's log."""

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        # Create a log for branch-A
        self._make_session_log(sessions_dir, f"{today}-session-1.json", "branch-a")

        from git_hook_policy import _session_log_for_branch

        # Ask for branch-b: must NOT get branch-a's log
        result = _session_log_for_branch(sessions_dir, "branch-b")
        assert result is None, "Must not return a log belonging to a different branch"

        # Ask for empty string: must also return None
        result_empty = _session_log_for_branch(sessions_dir, "")
        assert result_empty is None

    def test_skips_unreadable_newest_log(self, tmp_path: Path, monkeypatch: object) -> None:
        """An unreadable newest candidate is skipped; older readable one wins."""
        from unittest.mock import patch

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        older = self._make_session_log(
            sessions_dir, f"{today}-session-1.json", "fix/test", mtime_offset=-100
        )
        unreadable = self._make_session_log(
            sessions_dir, f"{today}-session-2.json", "fix/test", mtime_offset=0
        )

        real_stat = Path.stat

        def fake_stat(self_path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
            if self_path == unreadable:
                raise OSError("simulated unreadable")
            return real_stat(self_path, follow_symlinks=follow_symlinks)

        from git_hook_policy import _session_log_for_branch

        with patch.object(Path, "stat", fake_stat):
            with _w.catch_warnings(record=True) as caught:
                _w.simplefilter("always")
                result = _session_log_for_branch(sessions_dir, "fix/test")

        assert result == older, "Should fall back to readable older log"
        assert any("Skipping unreadable session log" in str(m.message) for m in caught)
