"""Tests for scripts/validation/effective_context_claude.py (issue #4880).

Split out of ``test_effective_context.py`` (1196 lines, over the taste-lints
500-line ERROR threshold) alongside the module split that motivated it. This
file covers everything specific to Claude Code's own loading model: ``@``
import following (REQ-4), the user layer's ``~/.claude/CLAUDE.md`` and
``@~/...`` tokens (REQ-5), and ``.claude/rules/*.md`` ``paths:`` scoping.
Shared source-reading and CLI/ratchet tests live in their own split files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context_resolvers as ecr
from scripts.validation.instruction_budget_globs import UnsupportedApplyToError
from tests.validation._effective_context_helpers import _build_claude_copilot_tree, _write

# --------------------------------------------------------------------------
# REQ-1: list each loaded file, its layer, and its bytes, plus totals.
# --------------------------------------------------------------------------


class TestReq1ClaudeResolution:
    """REQ-1, T1: Claude layer resolution (root, nested, scoped)."""

    def test_claude_reports_every_layer_with_correct_bytes(self, tmp_path: Path) -> None:
        """REQ-1: root, nested, and scoped files are reported with exact bytes."""
        sizes = _build_claude_copilot_tree(tmp_path)
        result = ecr.resolve_effective_context(tmp_path, "a/b/target.py", "claude")
        by_path = {f.path: f for f in result.files}

        assert by_path["CLAUDE.md"].layer == "root"
        assert by_path["CLAUDE.md"].size_bytes == sizes["CLAUDE.md"]
        assert by_path["AGENTS.md"].layer == "root"
        assert by_path[".claude/CLAUDE.md"].layer == "root"
        assert by_path["a/CLAUDE.md"].layer == "nested"
        assert by_path["a/AGENTS.md"].layer == "nested"
        assert by_path[".claude/rules/always.md"].layer == "scoped"
        assert by_path[".claude/rules/scoped.md"].layer == "scoped"
        assert ".claude/rules/other.md" not in by_path

        assert result.path_local_bytes == sizes["a/CLAUDE.md"] + sizes["a/AGENTS.md"]
        assert result.repo_total_bytes == sum(
            sizes[p]
            for p in (
                "CLAUDE.md",
                "AGENTS.md",
                ".claude/CLAUDE.md",
                "a/CLAUDE.md",
                "a/AGENTS.md",
                ".claude/rules/always.md",
                ".claude/rules/scoped.md",
            )
        )
        assert result.user_total_bytes == 0

    def test_claude_nested_layer_empty_for_a_root_target(self, tmp_path: Path) -> None:
        """REQ-1: a target at the repo root has no nested layer."""
        _build_claude_copilot_tree(tmp_path)
        _write(tmp_path, "root_target.py", "print(1)\n")
        result = ecr.resolve_effective_context(tmp_path, "root_target.py", "claude")
        assert not any(f.layer == "nested" for f in result.files)
        assert result.path_local_bytes == 0


# --------------------------------------------------------------------------
# REQ-4: cycle, missing import, path outside the repository.
# --------------------------------------------------------------------------


class TestReq4ImportProblems:
    """REQ-4, T1: a bad import is reported and not followed."""

    def test_missing_import_is_reported_and_not_followed(self, tmp_path: Path) -> None:
        """REQ-4: an import naming a nonexistent file is a 'missing' problem."""
        _write(tmp_path, "CLAUDE.md", "@nonexistent.md\n")
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        assert result.problems == (ecr.ImportProblem("missing", "CLAUDE.md", "@nonexistent.md"),)
        assert not any(f.path == "nonexistent.md" for f in result.files)

    def test_import_cycle_is_reported_and_not_followed(self, tmp_path: Path) -> None:
        """REQ-4: A imports B, B imports A back; the second hop is a cycle."""
        _write(tmp_path, "CLAUDE.md", "@a.md\n")
        _write(tmp_path, "a.md", "@CLAUDE.md\n")
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        assert ecr.ImportProblem("cycle", "a.md", "@CLAUDE.md") in result.problems
        # a.md is still recorded once: a cycle stops recursion, it does not
        # discard the file that revealed it.
        assert sum(1 for f in result.files if f.path == "a.md") == 1

    def test_import_outside_repo_is_reported_and_not_followed(self, tmp_path: Path) -> None:
        """REQ-4: an import that normalizes outside the repo root is refused."""
        _write(tmp_path, "CLAUDE.md", "@../outside.md\n")
        _write(tmp_path, "target.py", "x = 1\n")
        (tmp_path.parent / "outside.md").write_text("should never be read\n", encoding="utf-8")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        assert result.problems == (
            ecr.ImportProblem("outside_repo", "CLAUDE.md", "@../outside.md"),
        )
        # CLAUDE.md itself still loads; only the bad import is refused.
        assert [f.path for f in result.files] == ["CLAUDE.md"]

    def test_reused_import_is_deduplicated_not_reported_as_a_cycle(self, tmp_path: Path) -> None:
        """REQ-4 (boundary): a file imported from two places is billed once.

        Root ``CLAUDE.md`` imports ``@shared.md`` (resolves to ``shared.md``,
        relative to its own directory, the repo root). Nested ``a/CLAUDE.md``
        imports ``@../shared.md`` (resolves relative to ``a/``, also
        ``shared.md``): the same file, reached through two different
        directories, not a cycle.
        """
        _write(tmp_path, "CLAUDE.md", "@shared.md\n")
        _write(tmp_path, "shared.md", "shared body\n")
        _write(tmp_path, "a/CLAUDE.md", "@../shared.md\n")
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "target.py").write_text("x = 1\n", encoding="utf-8")

        result = ecr.resolve_effective_context(tmp_path, "a/b/target.py", "claude")
        assert result.problems == ()
        assert sum(1 for f in result.files if f.path == "shared.md") == 1

    def test_import_depth_beyond_five_stops_silently(self, tmp_path: Path) -> None:
        """REQ-4 (boundary): the "max depth 5" cap bounds recursion, no crash."""
        _write(tmp_path, "CLAUDE.md", "@d1.md\n")
        for depth in range(1, 8):
            nxt = depth + 1
            _write(tmp_path, f"d{depth}.md", f"@d{nxt}.md\n")
        _write(tmp_path, "d8.md", "leaf\n")
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        paths = {f.path for f in result.files}
        # depth 0 = CLAUDE.md, depths 1..5 followed = d1..d5. d6 (depth 6)
        # would only be reached by processing d5's imports at depth 6, over
        # the cap, so it is never read.
        assert "d5.md" in paths
        assert "d6.md" not in paths

    def test_target_escaping_repo_raises(self, tmp_path: Path) -> None:
        """REQ-4 / CLI: --target itself escaping the repo is a config error."""
        with pytest.raises(ecr.TargetOutsideRepoError):
            ecr.resolve_effective_context(tmp_path, "../escape.py", "claude")

    def test_absolute_target_raises(self, tmp_path: Path) -> None:
        """REQ-4 / CLI: an absolute --target is treated as escaping the repo."""
        with pytest.raises(ecr.TargetOutsideRepoError):
            ecr.resolve_effective_context(tmp_path, "/etc/passwd", "claude")


# --------------------------------------------------------------------------
# REQ-5: the user layer is reported separately and excluded from totals.
# --------------------------------------------------------------------------


class TestReq5UserLayer:
    """REQ-5, T1: --include-user reports a 'user' layer excluded from totals."""

    def test_include_user_adds_a_user_layer_file_excluded_from_totals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-5: user CLAUDE.md is reported, but excluded from repo/path-local totals."""
        home = tmp_path / "home"
        home.mkdir()
        user_bytes = _write(home, "CLAUDE.md", "user preferences, quite long text here\n")
        monkeypatch.setattr(ecr.Path, "home", classmethod(lambda cls: home))

        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo, "CLAUDE.md", "root\n")
        _write(repo, "target.py", "x = 1\n")

        without_user = ecr.resolve_effective_context(repo, "target.py", "claude")
        with_user = ecr.resolve_effective_context(repo, "target.py", "claude", include_user=True)

        user_files = [f for f in with_user.files if f.layer == "user"]
        assert len(user_files) == 1
        assert user_files[0].path == "~/CLAUDE.md"
        assert user_files[0].size_bytes == user_bytes
        assert with_user.user_total_bytes == user_bytes
        assert with_user.repo_total_bytes == without_user.repo_total_bytes
        assert with_user.path_local_bytes == without_user.path_local_bytes

    def test_include_user_false_never_reads_the_home_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-5: without --include-user, no user file is read or reported."""

        def _boom(cls: object) -> Path:  # pragma: no cover - only runs if the bug regresses
            raise AssertionError("Path.home() must not be called without include_user")

        monkeypatch.setattr(ecr.Path, "home", classmethod(_boom))
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        assert not any(f.layer == "user" for f in result.files)

    def test_project_tilde_import_resolves_under_include_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-5: a project file's `@~/...` import is a user-layer file."""
        home = tmp_path / "home"
        home.mkdir()
        user_bytes = _write(home, "extra.md", "user extra content\n")
        monkeypatch.setattr(ecr.Path, "home", classmethod(lambda cls: home))

        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo, "CLAUDE.md", "@~/extra.md\n")
        _write(repo, "target.py", "x = 1\n")

        result = ecr.resolve_effective_context(repo, "target.py", "claude", include_user=True)
        user_files = [f for f in result.files if f.layer == "user"]
        assert user_files == [
            ecr.LoadedFile("user", "~/extra.md", user_bytes, "import via CLAUDE.md")
        ]

    def test_project_tilde_import_ignored_without_include_user(self, tmp_path: Path) -> None:
        """REQ-5: without --include-user, a `@~/...` import is skipped, not a problem."""
        _write(tmp_path, "CLAUDE.md", "@~/extra.md\n")
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        assert result.files == (
            ecr.LoadedFile("root", "CLAUDE.md", len(b"@~/extra.md\n"), "root file"),
        )
        assert result.problems == ()

    def test_reused_tilde_import_is_deduplicated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A `@~/...` import reached from two project files is billed once."""
        home = tmp_path / "home"
        home.mkdir()
        user_bytes = _write(home, "shared.md", "shared user content\n")
        monkeypatch.setattr(ecr.Path, "home", classmethod(lambda cls: home))

        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo, "CLAUDE.md", "@~/shared.md\n")
        _write(repo, "a/CLAUDE.md", "@~/shared.md\n")
        (repo / "a" / "b").mkdir(parents=True)
        (repo / "a" / "b" / "target.py").write_text("x\n", encoding="utf-8")

        result = ecr.resolve_effective_context(repo, "a/b/target.py", "claude", include_user=True)
        user_files = [f for f in result.files if f.layer == "user"]
        assert len(user_files) == 1
        assert user_files[0].size_bytes == user_bytes

    def test_missing_tilde_import_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A `@~/...` import naming a nonexistent home file is a 'missing' problem."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(ecr.Path, "home", classmethod(lambda cls: home))
        _write(tmp_path, "CLAUDE.md", "@~/missing.md\n")
        _write(tmp_path, "target.py", "x\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude", include_user=True)
        assert ecr.ImportProblem("missing", "CLAUDE.md", "@~/missing.md") in result.problems


# --------------------------------------------------------------------------
# Supporting units: extract_import_tokens, malformed frontmatter, races.
# --------------------------------------------------------------------------


class TestExtractImportTokens:
    def test_finds_standalone_line_token(self) -> None:
        assert ecr.extract_import_tokens("# heading\n\n@AGENTS.md\n\nmore text\n") == ["@AGENTS.md"]

    def test_ignores_import_inside_fenced_code_block(self) -> None:
        text = "before\n```\n@AGENTS.md\n```\nafter\n"
        assert ecr.extract_import_tokens(text) == []

    def test_ignores_import_embedded_mid_line(self) -> None:
        assert ecr.extract_import_tokens("See @AGENTS.md for details.\n") == []

    def test_finds_multiple_tokens(self) -> None:
        text = "@one.md\ntext\n@two.md\n"
        assert ecr.extract_import_tokens(text) == ["@one.md", "@two.md"]


class TestClaudeBoundaryBranches:
    """Defensive branches: dedup guards, races, malformed YAML."""

    def test_add_and_walk_is_a_no_op_when_rel_path_already_seen(self, tmp_path: Path) -> None:
        """`_add_and_walk`'s own dedup guard: a second call for the same path is inert."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        sink = ecr._ImportSink(seen={"CLAUDE.md"})
        repo = ecr.Repo(tmp_path, None)
        ecr._add_and_walk(repo.read_bytes, "CLAUDE.md", "root", sink)
        assert sink.files == []

    def test_malformed_yaml_syntax_fails_closed(self, tmp_path: Path) -> None:
        """Genuinely invalid YAML (not just a duplicate key) raises, not silently 0."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nbody\n")
        _write(tmp_path, "target.py", "x = 1\n")
        with pytest.raises(UnsupportedApplyToError):
            ecr.resolve_effective_context(tmp_path, "target.py", "claude")

    def test_duplicate_paths_key_fails_closed(self, tmp_path: Path) -> None:
        """A malformed rule (duplicate top-level key) raises, not silently 0."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(
            tmp_path,
            ".claude/rules/bad.md",
            '---\npaths: ["**"]\npaths: ["**/*.py"]\n---\nbody\n',
        )
        _write(tmp_path, "target.py", "x = 1\n")
        with pytest.raises(UnsupportedApplyToError):
            ecr.resolve_effective_context(tmp_path, "target.py", "claude")

    def test_rule_frontmatter_without_a_paths_key_is_always_loaded(self, tmp_path: Path) -> None:
        """Frontmatter present, but no `paths:` key, is treated as always-on."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/no_paths.md", "---\npriority: high\n---\nbody\n")
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "claude")
        rule = next(f for f in result.files if f.path == ".claude/rules/no_paths.md")
        assert rule.reason == "no paths: key (always loaded)"

    def test_claude_scoped_skips_a_rule_that_disappears_between_listing_and_reading(
        self, tmp_path: Path
    ) -> None:
        """A rules-dir race (listed, then unreadable) is skipped, not a crash."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/flaky.md", '---\npaths: ["**"]\n---\nbody\n')
        real_repo = ecr.Repo(tmp_path, None)

        class _FlakyRepo(ecr.Repo):
            def read_bytes(self, rel_path: str) -> bytes | None:
                if rel_path == ".claude/rules/flaky.md":
                    return None
                return super().read_bytes(rel_path)

        flaky = _FlakyRepo(tmp_path, None)
        files = ecr._resolve_claude_scoped(flaky, "target.py")
        assert files == []
        # Sanity: the real repo (no race) does read it.
        assert ecr._resolve_claude_scoped(real_repo, "target.py") != []
