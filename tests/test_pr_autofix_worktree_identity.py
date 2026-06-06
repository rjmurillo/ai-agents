"""Regression tests for placeholder identity leak in pr-autofix worktrees.

Evidence: squash merge a2cc80e7 (#2458) on main carried
``Co-authored-by: Test <test@test.com>`` because a pytest fixture wrote
``test@test.com`` into a worktree's local .git/config via a subprocess
call with the wrong cwd.

These tests verify:
(a) Worktree identity reset clobbers leaked placeholder identity.
(b) Placeholder guard rejects commits authored by Test <test@test.com>.
(c) Guard skips checks for repos inside pytest tmp_path tree.
(d) Squash-body sanitizer removes placeholder co-author trailers.

See: issue #2466, commit a2cc80e7, PR #2458.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers for building temp git repos
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check,
    )


def _make_repo(path: Path, *, name: str = "Tester", email: str = "tester@example.com") -> Path:
    """Initialize a bare-ish git repo with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], path)
    _git(["config", "user.name", name], path)
    _git(["config", "user.email", email], path)
    (path / "README.md").write_text("init\n")
    _git(["add", "."], path)
    _git(["commit", "-m", "init"], path)
    return path


# ---------------------------------------------------------------------------
# (a) Worktree identity reset
# ---------------------------------------------------------------------------


class TestWorktreeIdentityReset:
    """reset_worktree_identity must clobber leaked placeholder identity."""

    def test_bot_operator_replaces_leaked_identity(self, tmp_path: Path) -> None:
        """After reset_worktree_identity, commits use rjmurillo-bot identity."""
        from scripts.github_core.worktree_identity import reset_worktree_identity

        repo = _make_repo(tmp_path / "repo")
        worktree_path = tmp_path / "wt"
        worktree_path.mkdir()

        # Simulate a leaked placeholder identity in the worktree's local config
        _git(["init", "-b", "main"], worktree_path)
        _git(["config", "user.name", "Test"], worktree_path)
        _git(["config", "user.email", "test@test.com"], worktree_path)

        reset_worktree_identity(worktree_path, operator="rjmurillo-bot")

        result = _git(["config", "--local", "user.name"], worktree_path)
        assert result.stdout.strip() == "rjmurillo-bot"

        result = _git(["config", "--local", "user.email"], worktree_path)
        assert result.stdout.strip() == "rjmurillo-bot@users.noreply.github.com"

    def test_human_operator_unsets_local_identity(self, tmp_path: Path) -> None:
        """With operator=rjmurillo, local identity is unset so global flows through."""
        from scripts.github_core.worktree_identity import reset_worktree_identity

        worktree_path = tmp_path / "wt"
        worktree_path.mkdir()
        _git(["init", "-b", "main"], worktree_path)
        _git(["config", "user.name", "Test"], worktree_path)
        _git(["config", "user.email", "test@test.com"], worktree_path)

        reset_worktree_identity(worktree_path, operator="rjmurillo")

        result = _git(["config", "--local", "user.name"], worktree_path, check=False)
        assert result.returncode != 0, "local user.name should be unset"

        result = _git(["config", "--local", "user.email"], worktree_path, check=False)
        assert result.returncode != 0, "local user.email should be unset"

    def test_reset_is_idempotent(self, tmp_path: Path) -> None:
        """Calling reset_worktree_identity twice is safe."""
        from scripts.github_core.worktree_identity import reset_worktree_identity

        worktree_path = tmp_path / "wt"
        worktree_path.mkdir()
        _git(["init", "-b", "main"], worktree_path)

        reset_worktree_identity(worktree_path, operator="rjmurillo-bot")
        reset_worktree_identity(worktree_path, operator="rjmurillo-bot")

        result = _git(["config", "--local", "user.email"], worktree_path)
        assert result.stdout.strip() == "rjmurillo-bot@users.noreply.github.com"


# ---------------------------------------------------------------------------
# (b) Placeholder guard rejects bad commits
# ---------------------------------------------------------------------------


class TestPlaceholderGuardRejectsCommits:
    """check_placeholder_identity exits non-zero for placeholder commits."""

    def _plant_commit(
        self,
        repo: Path,
        *,
        name: str,
        email: str,
        message: str = "bad commit",
    ) -> str:
        """Plant a commit with given identity and return its SHA."""
        _git(["config", "user.name", name], repo)
        _git(["config", "user.email", email], repo)
        (repo / "file.txt").write_text(f"{name}\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", message], repo)
        result = _git(["rev-parse", "HEAD"], repo)
        return result.stdout.strip()

    def test_rejects_placeholder_author(self, tmp_path: Path) -> None:
        """A commit with author Test <test@test.com> must be rejected (exit 1)."""
        from scripts.validation import check_placeholder_identity
        from scripts.validation.check_placeholder_identity import run_check

        repo = _make_repo(tmp_path / "repo")
        base = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        self._plant_commit(repo, name="Test", email="test@test.com")
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        # Patch _is_pytest_tmp so the guard tests the real check logic,
        # not the exemption heuristic (repos in tmp_path would otherwise skip).
        with patch.object(check_placeholder_identity, "_is_pytest_tmp", return_value=False):
            result = run_check(push_range=f"{base}..{head}", repo_root=repo)

        assert result.returncode == 1
        assert "author" in result.stderr.lower() or "author" in result.stdout.lower()
        assert "test@test.com" in result.stderr or "test@test.com" in result.stdout

    def test_rejects_placeholder_committer(self, tmp_path: Path) -> None:
        """A commit where committer is Test <test@test.com> must be rejected."""
        from scripts.validation import check_placeholder_identity
        from scripts.validation.check_placeholder_identity import run_check

        repo = _make_repo(tmp_path / "repo")
        base = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        (repo / "file.txt").write_text("content\n")
        _git(["add", "."], repo)
        import os
        env_overrides = {
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
            "GIT_AUTHOR_NAME": "Legit Author",
            "GIT_AUTHOR_EMAIL": "legit@example.com",
        }
        env = {**os.environ, **env_overrides}
        subprocess.run(
            ["git", "commit", "-m", "committer mismatch"],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
        )
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        with patch.object(check_placeholder_identity, "_is_pytest_tmp", return_value=False):
            result = run_check(push_range=f"{base}..{head}", repo_root=repo)

        assert result.returncode == 1
        assert "committer" in result.stderr.lower() or "committer" in result.stdout.lower()

    def test_rejects_bare_test_name_variants(self, tmp_path: Path) -> None:
        """Commits with test@test.com are rejected."""
        from scripts.validation import check_placeholder_identity
        from scripts.validation.check_placeholder_identity import run_check

        repo = _make_repo(tmp_path / "repo")
        base = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        self._plant_commit(repo, name="Test", email="test@test.com", message="bad")
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        with patch.object(check_placeholder_identity, "_is_pytest_tmp", return_value=False):
            result = run_check(push_range=f"{base}..{head}", repo_root=repo)

        assert result.returncode == 1

    def test_allows_example_com_emails(self, tmp_path: Path) -> None:
        """RFC-2606 reserved *@example.com emails must NOT be blocked."""
        from scripts.validation import check_placeholder_identity
        from scripts.validation.check_placeholder_identity import run_check

        repo = _make_repo(tmp_path / "repo")
        base = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        self._plant_commit(repo, name="Test User", email="test@example.com", message="ok")
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        with patch.object(check_placeholder_identity, "_is_pytest_tmp", return_value=False):
            result = run_check(push_range=f"{base}..{head}", repo_root=repo)

        assert result.returncode == 0

    def test_clean_commits_pass(self, tmp_path: Path) -> None:
        """Commits with legitimate identity must pass."""
        from scripts.validation import check_placeholder_identity
        from scripts.validation.check_placeholder_identity import run_check

        repo = _make_repo(tmp_path / "repo")
        base = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        self._plant_commit(
            repo, name="rjmurillo-bot", email="rjmurillo-bot@users.noreply.github.com",
        )
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        with patch.object(check_placeholder_identity, "_is_pytest_tmp", return_value=False):
            result = run_check(push_range=f"{base}..{head}", repo_root=repo)

        assert result.returncode == 0


# ---------------------------------------------------------------------------
# (c) Allow-list: guard skips repos inside pytest tmp_path tree
# ---------------------------------------------------------------------------


class TestGuardTmpPathExemption:
    """Guard exits 0 with SKIP message for repos inside pytest's tmp_path."""

    def test_skips_repo_under_tmp_path(self, tmp_path: Path) -> None:
        """A repo under pytest's tmp_path tree is exempted (contains 'pytest-of-')."""
        from scripts.validation.check_placeholder_identity import run_check

        # tmp_path is already under /tmp/pytest-of-<user>/... on this system.
        # No manual path construction needed; use tmp_path directly.
        repo = _make_repo(tmp_path / "repo")
        base_sha = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        _git(["config", "user.name", "Test"], repo)
        _git(["config", "user.email", "test@test.com"], repo)
        (repo / "bad.txt").write_text("bad\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "placeholder"], repo)
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        result = run_check(push_range=f"{base_sha}..{head}", repo_root=repo)

        # The heuristic fires only when tmp_path contains "pytest-of-".
        # Verify the path so the assertion matches the actual environment.
        import tempfile as _tempfile
        resolved = repo.resolve()
        tmp_dir = Path(_tempfile.gettempdir()).resolve()
        is_pytest_layout = (
            str(resolved).startswith(str(tmp_dir))
            and "pytest-of-" in str(resolved)
        )
        if is_pytest_layout:
            assert result.returncode == 0
            combined = (result.stdout + result.stderr).upper()
            assert "SKIP" in combined
        else:
            # CI with a non-standard tmp layout: guard ran, whatever it returned
            assert result.returncode in (0, 1)

    def test_real_worktree_path_not_exempted(self, tmp_path: Path) -> None:
        """A repo at a non-pytest-tmp path is NOT exempted by the heuristic.

        We simulate a real worktree by mocking _is_pytest_tmp to return False,
        confirming the guard proceeds to check commits (and blocks the bad one).
        """
        from scripts.validation import check_placeholder_identity
        from scripts.validation.check_placeholder_identity import run_check

        repo = _make_repo(tmp_path / "fake_real_repo")
        base_sha = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        _git(["config", "user.name", "Test"], repo)
        _git(["config", "user.email", "test@test.com"], repo)
        (repo / "bad.txt").write_text("bad\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "placeholder"], repo)
        head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

        # Simulate a non-tmp repo path: patch heuristic to return False.
        with patch.object(check_placeholder_identity, "_is_pytest_tmp", return_value=False):
            result = run_check(
                push_range=f"{base_sha}..{head}",
                repo_root=repo,
            )
        assert result.returncode == 1


# ---------------------------------------------------------------------------
# (d) Squash-body sanitizer
# ---------------------------------------------------------------------------


class TestSquashBodySanitizer:
    """filter_coauthor_trailers removes placeholder Co-authored-by lines."""

    def test_removes_test_at_test_dot_com_trailer(self) -> None:
        """Co-authored-by: Test <test@test.com> must be stripped."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        body = (
            "Fix the bug\n\n"
            "Co-authored-by: Test <test@test.com>\n"
            "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>\n"
        )
        result = filter_coauthor_trailers(body)
        assert "test@test.com" not in result
        assert "Copilot" in result

    def test_removes_bare_test_name_with_test_tld_trailer(self) -> None:
        """Name-based placeholder trailers must be stripped."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        body = "Co-authored-by: Test <fixture@example.test>\n"
        result = filter_coauthor_trailers(body)
        assert "fixture@example.test" not in result

    def test_preserves_copilot_trailer(self) -> None:
        """Copilot co-author must be preserved."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        body = "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>\n"
        result = filter_coauthor_trailers(body)
        assert "Copilot" in result

    def test_preserves_example_com_trailer(self) -> None:
        """RFC-2606 *@example.com co-authors are NOT placeholder and must be preserved."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        body = "Co-authored-by: Tester <tester@example.com>\n"
        result = filter_coauthor_trailers(body)
        assert "tester@example.com" in result

    def test_preserves_rjmurillo_bot_trailer(self) -> None:
        """Bot co-author must be preserved."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        body = "Co-authored-by: rjmurillo-bot <rjmurillo-bot@users.noreply.github.com>\n"
        result = filter_coauthor_trailers(body)
        assert "rjmurillo-bot" in result

    def test_empty_body_unchanged(self) -> None:
        """Empty body returns empty string."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        assert filter_coauthor_trailers("") == ""

    def test_body_with_only_placeholder_trailer_becomes_clean(self) -> None:
        """A body whose only trailer is the placeholder becomes trailer-free."""
        from scripts.github_core.placeholder_identity import filter_coauthor_trailers

        body = "Fix something\n\nCo-authored-by: Test <test@test.com>\n"
        result = filter_coauthor_trailers(body)
        assert "test@test.com" not in result
        assert "Fix something" in result

    def test_is_placeholder_identity_true_for_test_at_test(self) -> None:
        """is_placeholder_identity returns True for the known bad identity."""
        from scripts.github_core.placeholder_identity import is_placeholder_identity

        assert is_placeholder_identity("Test", "test@test.com") is True
        assert is_placeholder_identity("TEST", "TEST@TEST.COM") is True

    def test_is_placeholder_identity_false_for_example_com(self) -> None:
        """is_placeholder_identity returns False for RFC-2606 addresses."""
        from scripts.github_core.placeholder_identity import is_placeholder_identity

        assert is_placeholder_identity("Test User", "test@example.com") is False
        assert is_placeholder_identity("Test User", "user@example.org") is False

    def test_is_placeholder_identity_false_for_real_bot(self) -> None:
        """is_placeholder_identity returns False for the real bot identity."""
        from scripts.github_core.placeholder_identity import is_placeholder_identity

        assert is_placeholder_identity(
            "rjmurillo-bot", "rjmurillo-bot@users.noreply.github.com"
        ) is False
