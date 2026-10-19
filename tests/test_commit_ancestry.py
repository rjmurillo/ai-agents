"""Tests for commit_ancestry.check_ancestor against a real repository (issue #6506).

A branch or tag named like a cited hex prefix made ``git rev-parse`` resolve the
ref's tip, not the commit the reviewer cited. These tests build a real repository
so the ref-versus-object precedence is git's, not a mock's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
sys.path.insert(0, str(_SCRIPTS_DIR))
try:
    import commit_ancestry
finally:
    sys.path.remove(str(_SCRIPTS_DIR))

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={**_ENV, "PATH": os.environ["PATH"], "HOME": str(repo)},
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str, str]:
    """A repository with two commits; returns (path, first sha, second sha)."""
    root = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    _git(root, "commit", "-q", "--allow-empty", "-m", "first")
    first = _git(root, "rev-parse", "HEAD")
    _git(root, "commit", "-q", "--allow-empty", "-m", "second")
    second = _git(root, "rev-parse", "HEAD")
    return root, first, second


class TestRefNameCollision:
    def test_prefix_without_a_same_named_ref_is_reachable(self, repo) -> None:
        root, first, second = repo

        assert commit_ancestry.check_ancestor(first[:7], second, str(root)) == (
            True,
            "reachable",
            "",
        )

    @pytest.mark.parametrize("kind", ["branch", "tag", "remote"])
    def test_ref_named_like_the_prefix_is_refused(self, repo, kind: str) -> None:
        root, first, second = repo
        prefix = second[:7]
        if kind == "branch":
            _git(root, "branch", prefix, first)
        elif kind == "tag":
            _git(root, "tag", prefix, first)
        else:
            _git(root, "update-ref", f"refs/remotes/{prefix}/HEAD", first)

        result = commit_ancestry.check_ancestor(prefix, second, str(root))

        assert result == (False, "invalid", "ref-name-collision")

    def test_unshadowed_resolution_would_have_picked_the_ref(self, repo) -> None:
        """Control: without the guard, git resolves the branch tip, not the cited commit."""
        root, first, second = repo
        prefix = second[:7]
        _git(root, "branch", prefix, first)

        resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{prefix}^{{commit}}")

        assert resolved == first
        assert resolved != second

    def test_full_sha_is_not_shadowed_by_a_short_ref(self, repo) -> None:
        root, first, second = repo
        _git(root, "branch", second[:7], first)

        assert commit_ancestry.check_ancestor(second, second, str(root)) == (
            True,
            "reachable",
            "",
        )

    def test_ref_below_the_sha_name_is_not_a_collision(self, repo) -> None:
        root, first, second = repo
        prefix = second[:7]
        _git(root, "branch", f"{prefix}-topic", first)
        _git(root, "update-ref", f"refs/heads/other/{prefix}", first)

        assert commit_ancestry.check_ancestor(prefix, second, str(root))[:2] == (True, "reachable")

    def test_unrelated_commit_is_unreachable(self, repo) -> None:
        root, first, second = repo

        assert commit_ancestry.check_ancestor(second[:7], first, str(root)) == (
            False,
            "unreachable",
            "",
        )


class TestCaseInsensitiveRefShadow:
    """A case-insensitive filesystem resolves refs/heads/ABC1234 for abc1234.

    No case-insensitive filesystem is available in CI, so for-each-ref output is
    patched to list the ref in its stored case; rev-parse still sees a commit.
    """

    @staticmethod
    def _listing(root: Path, extra: list[str]):
        real_git = commit_ancestry._git

        def patched(repo_path: str, *args: str) -> tuple[int, str, str]:
            if args[0] == "for-each-ref":
                return 0, "\n".join(["refs/heads/main", *extra]) + "\n", ""
            return real_git(repo_path, *args)

        return patch.object(commit_ancestry, "_git", side_effect=patched)

    @pytest.mark.parametrize(
        "template",
        [
            "refs/heads/{upper}",
            "refs/tags/{upper}",
            "refs/remotes/{upper}/HEAD",
            "refs/{upper}",
            "refs/heads/{mixed}",
        ],
    )
    def test_differently_cased_ref_is_refused(self, repo, template: str) -> None:
        root, _, second = repo
        prefix = second[:7]
        listed = template.format(upper=prefix.upper(), mixed=prefix[:3] + prefix[3:].upper())

        with self._listing(root, [listed]):
            result = commit_ancestry.check_ancestor(prefix, second, str(root))

        assert result == (False, "invalid", "ref-name-collision")

    def test_uppercase_citation_meets_the_differently_cased_ref(self, repo) -> None:
        root, _, second = repo
        prefix = second[:7]

        with self._listing(root, [f"refs/heads/{prefix.upper()}"]):
            result = commit_ancestry.check_ancestor(prefix.upper(), second, str(root))

        assert result == (False, "invalid", "ref-name-collision")

    def test_unrelated_and_nested_refs_do_not_collide(self, repo) -> None:
        root, _, second = repo
        prefix = second[:7]
        extra = [
            f"refs/heads/{prefix.upper()}-topic",
            f"refs/heads/other/{prefix.upper()}",
            "refs/heads/Feature",
        ]

        with self._listing(root, extra):
            result = commit_ancestry.check_ancestor(prefix, second, str(root))

        assert result == (True, "reachable", "")

    def test_empty_ref_listing_is_reachable(self, repo) -> None:
        root, _, second = repo
        real_git = commit_ancestry._git

        def patched(repo_path: str, *args: str) -> tuple[int, str, str]:
            if args[0] == "for-each-ref":
                return 0, "", ""
            return real_git(repo_path, *args)

        with patch.object(commit_ancestry, "_git", side_effect=patched):
            result = commit_ancestry.check_ancestor(second[:7], second, str(root))

        assert result == (True, "reachable", "")


class TestUppercaseSha:
    def _orphan_with_letter_prefix(self, root: Path) -> str:
        """Create an unreferenced commit whose first 7 hex digits include a letter."""
        for attempt in range(200):
            tree = _git(root, "hash-object", "-t", "tree", "-w", "--stdin")
            sha = _git(root, "commit-tree", tree, "-m", f"orphan {attempt}")
            if any(c in "abcdef" for c in sha[:7]):
                return sha
        raise AssertionError("no orphan commit with a letter in its prefix")

    def test_uppercase_sha_resolves_like_lowercase(self, repo) -> None:
        root, first, second = repo
        prefix = first[:7]

        upper = commit_ancestry.check_ancestor(prefix.upper(), second, str(root))

        assert upper == commit_ancestry.check_ancestor(prefix, second, str(root))
        assert upper == (True, "reachable", "")

    def test_root_ref_named_like_an_uppercase_prefix_cannot_shadow_the_commit(self, repo) -> None:
        """$GIT_DIR/<UPPER> is a root ref; it must not turn an orphan into a reachable commit."""
        root, _, second = repo
        orphan = self._orphan_with_letter_prefix(root)
        upper = orphan[:7].upper()
        (root / ".git" / upper).write_text(second + "\n", encoding="utf-8")

        assert commit_ancestry.check_ancestor(upper, second, str(root)) == (
            False,
            "unreachable",
            "",
        )
        assert commit_ancestry.check_ancestor(orphan[:7], second, str(root)) == (
            False,
            "unreachable",
            "",
        )

    def test_uppercase_non_hex_is_still_refused(self) -> None:
        assert commit_ancestry.check_ancestor("ABCG123", "b" * 40, ".") == (
            False,
            "invalid",
            "not-a-sha",
        )


class TestShaShape:
    @pytest.mark.parametrize(
        "value",
        [
            "HEAD",
            "main",
            "abc",
            "abc123g",
            "abc1234\n",
            " abc1234",
            "-abc1234",
            "a" * 41,
            "",
            "ab*",
        ],
    )
    def test_non_hex_input_never_reaches_git(self, value: str) -> None:
        with patch("subprocess.run", side_effect=AssertionError("git must not run")):
            assert commit_ancestry.check_ancestor(value, "b" * 40, ".") == (
                False,
                "invalid",
                "not-a-sha",
            )


class TestProbeFailure:
    def test_probe_failure_is_invalid_not_a_pass(self, repo) -> None:
        root, _, second = repo
        real_git = commit_ancestry._git

        def failing(repo_path: str, *args: str) -> tuple[int, str, str]:
            if args[0] == "for-each-ref":
                return 128, "", "fatal: broken refs\n"
            return real_git(repo_path, *args)

        with patch.object(commit_ancestry, "_git", side_effect=failing):
            result = commit_ancestry.check_ancestor(second[:7], second, str(root))

        assert result == (False, "invalid", "git-error: fatal: broken refs")

    def test_probe_failure_without_stderr_still_fails_closed(self, repo) -> None:
        root, _, second = repo
        real_git = commit_ancestry._git

        def failing(repo_path: str, *args: str) -> tuple[int, str, str]:
            if args[0] == "for-each-ref":
                return 1, "", ""
            return real_git(repo_path, *args)

        with patch.object(commit_ancestry, "_git", side_effect=failing):
            result = commit_ancestry.check_ancestor(second[:7], second, str(root))

        assert result[:2] == (False, "invalid")
        assert result[2].startswith("git-error: ")
