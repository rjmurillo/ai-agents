"""Tests for scripts/validation/effective_context_sources.py (issue #4880).

Split out of ``test_effective_context.py`` (1196 lines, over the taste-lints
500-line ERROR threshold) alongside the module split that motivated it. This
file covers what ``effective_context_sources`` holds: ``Repo`` (live and
``--rev`` reading), target-to-directory resolution, the directory chain, and
glob matching. Claude- and Copilot-specific resolution live in their own
split test files; CLI, ratchet, and observe tests stay in
``test_effective_context.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context_resolvers as ecr
import scripts.validation.effective_context_sources as ecs
from tests.validation._effective_context_helpers import _commit_all, _init_git_repo, _write

# --------------------------------------------------------------------------
# REQ-2: --rev reads every file and import at that commit with `git show`.
# --------------------------------------------------------------------------


class TestReq2RevReading:
    """REQ-2, T3: `--rev` reads files and imports through `git show`."""

    def test_rev_reads_content_from_the_named_commit_not_the_working_tree(
        self, tmp_path: Path
    ) -> None:
        """REQ-2: resolving at an old rev sees the old bytes, not current ones."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "@AGENTS.md\n")
        _write(tmp_path, "AGENTS.md", "old\n")
        old_sha = _commit_all(tmp_path, "v1")

        _write(tmp_path, "AGENTS.md", "new, much longer content than before\n")
        _commit_all(tmp_path, "v2")

        at_old = ecr.resolve_effective_context(tmp_path, "target.py", "claude", rev=old_sha)
        at_head = ecr.resolve_effective_context(tmp_path, "target.py", "claude")

        old_agents = next(f for f in at_old.files if f.path == "AGENTS.md")
        head_agents = next(f for f in at_head.files if f.path == "AGENTS.md")
        assert old_agents.size_bytes == len(b"old\n")
        assert head_agents.size_bytes == len(b"new, much longer content than before\n")

    def test_rev_reads_a_nested_directory_listing_via_git_ls_tree(self, tmp_path: Path) -> None:
        """REQ-2: scoped rules are listed at the rev, not the working tree."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(
            tmp_path,
            ".claude/rules/only-at-old-rev.md",
            '---\npaths: ["**"]\n---\nold rule\n',
        )
        old_sha = _commit_all(tmp_path, "v1")
        (tmp_path / ".claude" / "rules" / "only-at-old-rev.md").unlink()
        _write(tmp_path, ".claude/rules/new-rule.md", '---\npaths: ["**"]\n---\nnew rule\n')
        _commit_all(tmp_path, "v2")

        at_old = ecr.resolve_effective_context(tmp_path, "target.py", "claude", rev=old_sha)
        at_head = ecr.resolve_effective_context(tmp_path, "target.py", "claude")

        old_scoped = {f.path for f in at_old.files if f.layer == "scoped"}
        head_scoped = {f.path for f in at_head.files if f.layer == "scoped"}
        assert old_scoped == {".claude/rules/only-at-old-rev.md"}
        assert head_scoped == {".claude/rules/new-rule.md"}

    def test_invalid_rev_raises(self, tmp_path: Path) -> None:
        """REQ-2 / CLI: an unresolvable --rev is a config error (exit 2)."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _commit_all(tmp_path, "v1")
        with pytest.raises(ecr.InvalidRevError):
            ecr.resolve_effective_context(tmp_path, "target.py", "claude", rev="not-a-real-rev")


class TestGlobMatches:
    def test_universal_glob_matches_anything(self) -> None:
        assert ecr.glob_matches({"**"}, "any/path/at/all.py") is True

    def test_extension_glob_matches_same_extension_only(self) -> None:
        patterns = {"**/*.py"}
        assert ecr.glob_matches(patterns, "a/b/target.py") is True
        assert ecr.glob_matches(patterns, "a/b/target.cs") is False

    def test_empty_pattern_set_matches_nothing(self) -> None:
        assert ecr.glob_matches(set(), "a/b/target.py") is False


class TestDirectoryChain:
    def test_root_target_has_no_chain(self) -> None:
        assert ecr.directory_chain("") == []

    def test_single_level(self) -> None:
        assert ecr.directory_chain("scripts") == ["scripts"]

    def test_multi_level_is_cumulative(self) -> None:
        assert ecr.directory_chain(".github/workflows") == [".github", ".github/workflows"]


class TestResolveBaseDirectory:
    def test_file_target_resolves_to_parent(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "f.py").write_text("x\n", encoding="utf-8")
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "a/b/f.py") == "a/b"

    def test_directory_target_resolves_to_itself(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "a/b") == "a/b"

    def test_nonexistent_file_target_still_resolves_to_its_parent(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "a/does-not-exist.py") == "a"

    def test_root_target_resolves_to_empty_string(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, "target.py") == ""

    def test_root_dot_target_resolves_to_empty_string_too(self, tmp_path: Path) -> None:
        """`resolve_base_directory` folds a "." target to the empty root string."""
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, ".") == ""

    def test_escaping_target_raises(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        with pytest.raises(ecr.TargetOutsideRepoError):
            ecr.resolve_base_directory(repo, "../../etc/passwd")


class TestRepoDirectAccessors:
    def test_read_bytes_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.read_bytes("nope.md") is None

    def test_list_dir_returns_empty_for_missing_directory(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.list_dir("nope") == []

    def test_is_dir_true_for_repo_root(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.is_dir("") is True

    def test_rev_is_valid_true_when_rev_is_none(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        assert repo.rev_is_valid() is True

    def test_list_dir_at_a_rev_excludes_a_subdirectory_entry(self, tmp_path: Path) -> None:
        """`git ls-tree` at a rev must keep only blobs, matching `is_file()` in the live tree.

        A bare `--name-only` listing cannot distinguish a file from a
        subdirectory of the same listed name; without a type filter, a
        subdirectory under a scanned rules/instructions directory would be
        misread as a rule file.
        """
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/real.md", '---\npaths: ["**"]\n---\nbody\n')
        _write(tmp_path, ".claude/rules/nested/inner.md", '---\npaths: ["**"]\n---\nbody\n')
        sha = _commit_all(tmp_path, "v1")

        live = ecs.Repo(tmp_path, None).list_dir(".claude/rules")
        at_rev = ecs.Repo(tmp_path, sha).list_dir(".claude/rules")

        assert live == [".claude/rules/real.md"]
        assert at_rev == [".claude/rules/real.md"]

    def test_rev_is_valid_refuses_an_option_shaped_rev(self, tmp_path: Path) -> None:
        """REQ-4: a `--rev` that starts with `-` never reaches git (CWE-88)."""
        repo = ecr.Repo(tmp_path, "--all")
        with mock.patch.object(ecs.subprocess, "run") as run:
            assert repo.rev_is_valid() is False
        run.assert_not_called()

    def test_ls_tree_failure_returns_empty_listing(self, tmp_path: Path) -> None:
        """A `git ls-tree` failure (bad rev, at the low-level accessor) yields []."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _commit_all(tmp_path, "v1")
        repo = ecr.Repo(tmp_path, "not-a-real-rev")
        assert repo.list_dir(".claude/rules") == []
