"""Case folding in prune_branch_config (issue #6506).

Git lowercases the section name in ``git config --list`` keys, so a legacy
``[branch.Feature-X]`` section reads as ``feature-x`` while the branch is
``Feature-X``. Split from ``test_prune_branch_config.py`` to keep both files
under the 500-line limit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.maintenance.prune_branch_config import (
    find_stale_branches,
    list_configured_branches,
    prune_branch_config,
    resolve_config_path,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "f.txt").write_text("x", encoding="utf-8")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _sections(repo: Path) -> tuple[str, ...]:
    return list_configured_branches(repo)


class TestFindStaleCaseFolding:
    def test_legacy_lowercased_section_of_a_mixed_case_branch_is_live(self) -> None:
        stale = find_stale_branches(["feature-x"], frozenset({"Feature-X"}), frozenset())

        assert stale == ()

    def test_legacy_lowercased_section_of_a_mixed_case_checkout_is_live(self) -> None:
        stale = find_stale_branches(["feature-x"], frozenset(), frozenset({"Feature-X"}))

        assert stale == ()

    def test_unrelated_section_stays_stale_when_case_is_folded(self) -> None:
        stale = find_stale_branches(["feature-y"], frozenset({"Feature-X"}), frozenset())

        assert stale == ("feature-y",)


class TestPruneCaseFolding:
    def test_legacy_mixed_case_section_is_not_reported_or_removed(self, repo: Path) -> None:
        """Git lowercases ``[branch.Feature-X]`` when listing keys, though the branch is live."""
        _git(repo, "branch", "Feature-X")
        config = resolve_config_path(repo)
        with config.open("a", encoding="utf-8") as handle:
            handle.write("[branch.Feature-X]\n\tremote = origin\n")
        assert _sections(repo) == ("feature-x",)

        dry = prune_branch_config(repo)
        applied = prune_branch_config(repo, apply=True)

        assert dry.stale == ()
        assert applied.stale == ()
        assert applied.removed == 0
        assert "[branch.Feature-X]" in config.read_text(encoding="utf-8")
