"""A seed run must come from a commit in local origin/main history (issue #6239).

These run real git in a throwaway repository, because the claim is about git's
exit code and a stub would only restate the implementation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.testmon_seed_trust import is_main_ancestor, origin_main_present


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Two commits on main (published as origin/main) and one commit off main."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", "a")
    _git(tmp_path, "commit", "-q", "-m", "one")
    (tmp_path / "a").write_text("2", encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "two")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(tmp_path, "checkout", "-q", "-b", "topic", "HEAD~1")
    (tmp_path / "b").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "b")
    _git(tmp_path, "commit", "-q", "-m", "off main")
    return tmp_path


def test_origin_main_is_present_only_when_the_ref_exists(repo: Path) -> None:
    assert origin_main_present(repo)
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    assert not origin_main_present(repo)


def test_a_commit_in_main_history_is_an_ancestor(repo: Path) -> None:
    assert is_main_ancestor(repo, _git(repo, "rev-parse", "origin/main"))
    assert is_main_ancestor(repo, _git(repo, "rev-parse", "origin/main~1"))


def test_a_commit_off_main_is_not_an_ancestor(repo: Path) -> None:
    assert not is_main_ancestor(repo, _git(repo, "rev-parse", "topic"))


@pytest.mark.parametrize(
    "sha",
    ["0" * 40, "--all", "origin/main", "abc", "A" * 40, "", "HEAD; rm -rf /"],
    ids=["unknown", "option", "refname", "short", "uppercase", "empty", "injection"],
)
def test_unknown_or_malformed_values_are_never_ancestors(repo: Path, sha: str) -> None:
    assert not is_main_ancestor(repo, sha)


def test_a_directory_that_is_not_a_repository_has_no_origin_main(tmp_path: Path) -> None:
    assert not origin_main_present(tmp_path)
    assert not is_main_ancestor(tmp_path, "a" * 40)
