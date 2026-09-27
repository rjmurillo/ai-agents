"""Tests for scripts/validation/effective_context.py (SPEC-4880, issue #4880).

Covers REQ-1 through REQ-7 from
``.project-toolkit/specs/SPEC-4880-path-local-effective-context.md``. Each
test's docstring names the requirement it proves. Fixture trees are built
under ``tmp_path`` so results are independent of live repo drift; two anchor
tests (`test_req6_...real_repo...`, `test_observe_...` live subprocess calls)
run against the real repository to guard the ratchet and the loading model
from silent regression.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context as ec
import scripts.validation.effective_context_resolvers as ecr
from scripts.validation.instruction_budget_globs import UnsupportedApplyToError


def _write(root: Path, rel_path: str, content: str) -> int:
    """Write a UTF-8 text file and return its byte length."""
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def _build_claude_copilot_tree(root: Path) -> dict[str, int]:
    """A small tree exercising every Claude/Copilot layer for one target.

    Target: ``a/b/target.py``. Returns the byte length of every file written,
    keyed by its repo-relative path, so tests can assert exact totals.
    """
    sizes: dict[str, int] = {}
    sizes["CLAUDE.md"] = _write(root, "CLAUDE.md", "# root\n\n@AGENTS.md\n")
    sizes["AGENTS.md"] = _write(root, "AGENTS.md", "root agents body\n")
    sizes[".claude/CLAUDE.md"] = _write(root, ".claude/CLAUDE.md", "dot-claude root\n")
    sizes["a/CLAUDE.md"] = _write(root, "a/CLAUDE.md", "@AGENTS.md\n")
    sizes["a/AGENTS.md"] = _write(root, "a/AGENTS.md", "a-level agents\n")
    # a/b has no CLAUDE.md: nested layer for Claude stops growing there.
    sizes[".claude/rules/always.md"] = _write(
        root, ".claude/rules/always.md", "no frontmatter\nalways loaded\n"
    )
    sizes[".claude/rules/scoped.md"] = _write(
        root,
        ".claude/rules/scoped.md",
        '---\npaths:\n  - "**/*.py"\n---\n\nscoped to python\n',
    )
    sizes[".claude/rules/other.md"] = _write(
        root,
        ".claude/rules/other.md",
        '---\npaths:\n  - "**/*.cs"\n---\n\nscoped to csharp, should not match\n',
    )
    sizes[".github/copilot-instructions.md"] = _write(
        root, ".github/copilot-instructions.md", "copilot repo instructions\n"
    )
    sizes[".github/instructions/scoped.instructions.md"] = _write(
        root,
        ".github/instructions/scoped.instructions.md",
        '---\napplyTo: "**/*.py"\n---\n\nscoped to python\n',
    )
    sizes[".github/instructions/other.instructions.md"] = _write(
        root,
        ".github/instructions/other.instructions.md",
        '---\napplyTo: "**/*.cs"\n---\n\nscoped to csharp, should not match\n',
    )
    (root / "a" / "b").mkdir(parents=True, exist_ok=True)
    (root / "a" / "b" / "target.py").write_text("print('hi')\n", encoding="utf-8")
    return sizes


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


class TestReq1CopilotResolution:
    """REQ-1, T2: Copilot layer resolution (root, nested/model, scoped)."""

    def test_copilot_reports_every_layer_with_correct_bytes(self, tmp_path: Path) -> None:
        """REQ-1: Copilot root/nested/scoped layers, no import expansion."""
        sizes = _build_claude_copilot_tree(tmp_path)
        result = ecr.resolve_effective_context(tmp_path, "a/b/target.py", "copilot")
        by_path = {f.path: f for f in result.files}

        assert by_path[".github/copilot-instructions.md"].layer == "root"
        assert by_path["AGENTS.md"].layer == "root"
        assert by_path["CLAUDE.md"].layer == "root"
        assert by_path["a/AGENTS.md"].layer == "nested"
        assert by_path["a/CLAUDE.md"].layer == "nested"
        assert by_path[".github/instructions/scoped.instructions.md"].layer == "scoped"
        assert ".github/instructions/other.instructions.md" not in by_path

        # Copilot never expands @ imports: AGENTS.md is read directly (raw
        # bytes), not "because CLAUDE.md imported it".
        assert by_path["AGENTS.md"].reason == "root file"
        assert result.path_local_bytes == sizes["a/CLAUDE.md"] + sizes["a/AGENTS.md"]

    def test_copilot_has_no_import_problems(self, tmp_path: Path) -> None:
        """REQ-1: Copilot resolution never follows imports, so no problems."""
        _build_claude_copilot_tree(tmp_path)
        result = ecr.resolve_effective_context(tmp_path, "a/b/target.py", "copilot")
        assert result.problems == ()


# --------------------------------------------------------------------------
# REQ-2: --rev reads every file and import at that commit with `git show`.
# --------------------------------------------------------------------------


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _commit_all(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", message], cwd=root, check=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


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


# --------------------------------------------------------------------------
# REQ-3: --observe compares the static Copilot set with a live listing.
# --------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestReq3Observe:
    """REQ-3, T4: --observe with a stubbed `copilot instruction list` runner."""

    def test_observe_matches_when_listing_equals_the_static_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3: no mismatch when the (stubbed) listing equals the static set."""
        _build_claude_copilot_tree(tmp_path)
        entries = [
            {"location": "repository", "sourcePath": ".github/copilot-instructions.md"},
            {"location": "repository", "sourcePath": "AGENTS.md"},
            {"location": "repository", "sourcePath": "CLAUDE.md"},
            {"location": "repository", "sourcePath": "a/AGENTS.md"},
            {"location": "repository", "sourcePath": "a/CLAUDE.md"},
            # Both instructions files, even the one whose applyTo does not
            # match this target: REQ-3 compares before the applyTo filter.
            {"location": "repository", "sourcePath": ".github/instructions/scoped.instructions.md"},
            {"location": "repository", "sourcePath": ".github/instructions/other.instructions.md"},
            {"location": "user", "sourcePath": "/home/dev/.copilot/copilot-instructions.md"},
        ]

        def _fake_run(*_args: object, **_kwargs: object) -> _FakeCompletedProcess:
            return _FakeCompletedProcess(0, stdout=json.dumps(entries))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        repo = ecr.Repo(tmp_path, None)
        base_dir = ecr.resolve_base_directory(repo, "a/b/target.py")
        static_paths = ecr.copilot_static_paths_unfiltered(repo, base_dir)

        ok, missing, extra = ec.run_copilot_observe(tmp_path, base_dir, static_paths)
        assert ok is True
        assert missing == []
        assert extra == []

    def test_observe_reports_missing_and_extra_on_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3: a listing that drops one file and adds another fails, named."""
        _build_claude_copilot_tree(tmp_path)
        entries = [
            {"location": "repository", "sourcePath": ".github/copilot-instructions.md"},
            {"location": "repository", "sourcePath": "AGENTS.md"},
            {"location": "repository", "sourcePath": "CLAUDE.md"},
            {"location": "repository", "sourcePath": "a/AGENTS.md"},
            {"location": "repository", "sourcePath": "a/CLAUDE.md"},
            {"location": "repository", "sourcePath": ".github/instructions/scoped.instructions.md"},
            # `other.instructions.md` is dropped (missing) and a bogus extra
            # file is added.
            {"location": "repository", "sourcePath": ".github/instructions/bogus.instructions.md"},
        ]

        def _fake_run(*_args: object, **_kwargs: object) -> _FakeCompletedProcess:
            return _FakeCompletedProcess(0, stdout=json.dumps(entries))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        repo = ecr.Repo(tmp_path, None)
        base_dir = ecr.resolve_base_directory(repo, "a/b/target.py")
        static_paths = ecr.copilot_static_paths_unfiltered(repo, base_dir)

        ok, missing, extra = ec.run_copilot_observe(tmp_path, base_dir, static_paths)
        assert ok is False
        assert missing == [".github/instructions/other.instructions.md"]
        assert extra == [".github/instructions/bogus.instructions.md"]

    def test_observe_raises_when_copilot_binary_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3 / ADR-035 exit 3: a missing `copilot` binary is an external error."""

        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        with pytest.raises(ec.CopilotUnavailableError):
            ec.run_copilot_observe(tmp_path, "", set())

    def test_observe_raises_on_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3 / ADR-035 exit 3: a `copilot` timeout is an external error."""

        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired(cmd="copilot", timeout=60)

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        with pytest.raises(ec.CopilotUnavailableError):
            ec.run_copilot_observe(tmp_path, "", set())

    def test_observe_raises_on_nonzero_exit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3: a non-zero `copilot` exit is treated as unavailable."""

        def _fake_run(*_args: object, **_kwargs: object) -> _FakeCompletedProcess:
            return _FakeCompletedProcess(1, stderr="boom")

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        with pytest.raises(ec.CopilotUnavailableError):
            ec.run_copilot_observe(tmp_path, "", set())

    @pytest.mark.skipif(
        subprocess.run(["which", "copilot"], capture_output=True).returncode != 0,
        reason="copilot CLI not installed on this machine",
    )
    def test_observe_live_matches_for_every_frozen_target(self) -> None:
        """REQ-3 / T9-T10: one live `copilot instruction list --json` per target.

        Live evidence, not a stub: run once per frozen target against the
        real repository, exactly as the task's report requires. A CLI
        transiently unavailable here is reported by pytest as a failure with
        the real stderr, not silently downgraded, since the module itself
        only downgrades to "unavailable" inside `run_copilot_observe`.
        """
        for target in ec.FROZEN_TARGETS:
            code = ec.main(["--target", target, "--harness", "copilot", "--observe"])
            assert code == 0, f"observe mismatch or error for {target}"


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
    """REQ-5, T1/T2: --include-user reports a 'user' layer excluded from totals."""

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


# --------------------------------------------------------------------------
# REQ-6 / REQ-7: the path-local ratchet and its label text.
# --------------------------------------------------------------------------


class TestReq6Ratchet:
    """REQ-6, T5: the ratchet fails on growth and names the fix command."""

    def test_real_repository_passes_its_own_ratchet(self) -> None:
        """REQ-6: the real repository, at HEAD, holds every ceiling it sets."""
        ok, _report, failures = ec.check_ceilings(REPO_ROOT, ec.CEILINGS_BYTES)
        assert ok, failures

    def test_synthetic_growth_fixture_fails_the_ratchet(self, tmp_path: Path) -> None:
        """REQ-6: a nested file grown past its ceiling fails, naming the fix."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "a/CLAUDE.md", "a" * 500 + "\n")
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "target.py").write_text("x = 1\n", encoding="utf-8")

        tiny_ceilings = {("a/b/target.py", "claude"): 10}
        ok, report, failures = ec.check_ceilings(tmp_path, tiny_ceilings)

        assert ok is False
        assert any("FAIL" in line for line in report)
        assert len(failures) == 1
        assert "exceed ceiling 10" in failures[0]
        assert "--target a/b/target.py --harness claude" in failures[0]

    def test_ratchet_passes_when_nested_bytes_are_at_the_ceiling(self, tmp_path: Path) -> None:
        """REQ-6: the ceiling is a not-to-exceed bound, so equality passes."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        nested_bytes = _write(tmp_path, "a/CLAUDE.md", "12345\n")
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "target.py").write_text("x = 1\n", encoding="utf-8")

        ok, _report, failures = ec.check_ceilings(
            tmp_path, {("a/b/target.py", "claude"): nested_bytes}
        )
        assert ok is True
        assert failures == []

    def test_ci_flag_runs_the_real_ratchet_and_exits_zero(self) -> None:
        """REQ-6 / CLI: `--ci` against the real repository exits 0."""
        assert ec.main(["--ci"]) == 0


class TestReq7CeilingLabel:
    """REQ-7, T5: the ceiling comment names the ceilings local, not vendor-set."""

    def test_ceiling_label_names_the_ceilings_local(self) -> None:
        """REQ-7: the label states the ceilings are local and measured."""
        assert "local" in ec.CEILING_LABEL.lower()
        assert "measured" in ec.CEILING_LABEL.lower()

    def test_ceiling_label_disclaims_a_vendor_limit(self) -> None:
        """REQ-7: the label states no vendor size limit is implied."""
        assert "no vendor" in ec.CEILING_LABEL.lower()


# --------------------------------------------------------------------------
# Supporting resolver units: glob matching, directory chain, imports parsing,
# base-directory resolution, malformed frontmatter, CLI plumbing.
# --------------------------------------------------------------------------


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

    def test_escaping_target_raises(self, tmp_path: Path) -> None:
        repo = ecr.Repo(tmp_path, None)
        with pytest.raises(ecr.TargetOutsideRepoError):
            ecr.resolve_base_directory(repo, "../../etc/passwd")


class TestMalformedFrontmatter:
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

    def test_non_string_applyto_entry_fails_closed(self, tmp_path: Path) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(
            tmp_path,
            ".github/instructions/bad.instructions.md",
            "---\napplyTo:\n  - 5\n---\nbody\n",
        )
        _write(tmp_path, "target.py", "x = 1\n")
        with pytest.raises(UnsupportedApplyToError):
            ecr.resolve_effective_context(tmp_path, "target.py", "copilot")


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


# --------------------------------------------------------------------------
# CLI plumbing: argument validation and output formats.
# --------------------------------------------------------------------------


class TestBoundaryBranches:
    """Defensive branches: dedup guards, races, malformed YAML, unknown input."""

    def test_add_and_walk_is_a_no_op_when_rel_path_already_seen(self, tmp_path: Path) -> None:
        """`_add_and_walk`'s own dedup guard: a second call for the same path is inert."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        seen: set[str] = {"CLAUDE.md"}
        files: list[ecr.LoadedFile] = []
        problems: list[ecr.ImportProblem] = []
        repo = ecr.Repo(tmp_path, None)
        ecr._add_and_walk(repo.read_bytes, "CLAUDE.md", "root", seen, files, problems, None)
        assert files == []

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

    def test_malformed_yaml_syntax_fails_closed(self, tmp_path: Path) -> None:
        """Genuinely invalid YAML (not just a duplicate key) raises, not silently 0."""
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nbody\n")
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

    def test_instructions_file_without_applyto_key_scopes_to_nothing(self, tmp_path: Path) -> None:
        """A `.instructions.md` with frontmatter but no `applyTo:` never loads."""
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(
            tmp_path,
            ".github/instructions/no_applyto.instructions.md",
            "---\ndescription: x\n---\nbody\n",
        )
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "copilot")
        assert not any(f.path.endswith("no_applyto.instructions.md") for f in result.files)

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

    def test_copilot_scoped_skips_an_instructions_file_that_disappears(
        self, tmp_path: Path
    ) -> None:
        """The same race, on the Copilot side (`resolve_copilot`'s scoped loop)."""
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(
            tmp_path,
            ".github/instructions/flaky.instructions.md",
            '---\napplyTo: "**"\n---\nbody\n',
        )

        class _FlakyRepo(ecr.Repo):
            def read_bytes(self, rel_path: str) -> bytes | None:
                if rel_path == ".github/instructions/flaky.instructions.md":
                    return None
                return super().read_bytes(rel_path)

        flaky = _FlakyRepo(tmp_path, None)
        files = ecr.resolve_copilot(flaky, "", "target.py", include_user=False)
        assert not any(f.path.endswith("flaky.instructions.md") for f in files)

    def test_copilot_user_layer_reads_copilot_home_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-5: Copilot's user file honors $COPILOT_HOME, default ~/.copilot."""
        copilot_home = tmp_path / "custom-copilot-home"
        copilot_home.mkdir()
        user_bytes = _write(copilot_home, "copilot-instructions.md", "user copilot text\n")
        monkeypatch.setenv(ecr.COPILOT_HOME_ENV, str(copilot_home))

        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo, ".github/copilot-instructions.md", "x\n")
        _write(repo, "target.py", "x = 1\n")

        result = ecr.resolve_effective_context(repo, "target.py", "copilot", include_user=True)
        user_files = [f for f in result.files if f.layer == "user"]
        assert len(user_files) == 1
        assert user_files[0].size_bytes == user_bytes

    def test_root_dot_target_resolves_to_empty_base_dir(self, tmp_path: Path) -> None:
        """`resolve_base_directory` folds a "." target to the empty root string."""
        repo = ecr.Repo(tmp_path, None)
        assert ecr.resolve_base_directory(repo, ".") == ""

    def test_unknown_harness_raises_value_error(self, tmp_path: Path) -> None:
        _write(tmp_path, "target.py", "x = 1\n")
        with pytest.raises(ValueError, match="unknown harness"):
            ecr.resolve_effective_context(tmp_path, "target.py", "bogus")

    def test_ls_tree_failure_returns_empty_listing(self, tmp_path: Path) -> None:
        """A `git ls-tree` failure (bad rev, at the low-level accessor) yields []."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _commit_all(tmp_path, "v1")
        repo = ecr.Repo(tmp_path, "not-a-real-rev")
        assert repo.list_dir(".claude/rules") == []


class TestCliInjectedRepoRoot:
    """CLI paths only reachable by injecting `repo_root` (a synthetic tree)."""

    def test_malformed_rule_frontmatter_exits_two_via_main(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nbody\n")
        _write(tmp_path, "target.py", "x = 1\n")
        code = ec.main(["--target", "target.py", "--harness", "claude"], repo_root=tmp_path)
        assert code == 2
        assert "not valid YAML" in capsys.readouterr().err

    def test_ci_reports_a_malformed_rule_as_exit_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nbody\n")
        _write(tmp_path, "target.py", "x = 1\n")
        monkeypatch.setattr(ec, "CEILINGS_BYTES", {("target.py", "claude"): 10})
        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 2
        assert "not valid YAML" in capsys.readouterr().err

    def test_ci_prints_fail_and_exits_one_on_a_real_breach(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "a/CLAUDE.md", "a" * 100 + "\n")
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "target.py").write_text("x\n", encoding="utf-8")
        monkeypatch.setattr(ec, "CEILINGS_BYTES", {("a/b/target.py", "claude"): 1})
        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 1
        out = capsys.readouterr().out
        assert "FAIL: path-local effective-context ratchet breached." in out

    def test_problems_are_printed_in_the_table(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "CLAUDE.md", "@nonexistent.md\n")
        _write(tmp_path, "target.py", "x = 1\n")
        code = ec.main(["--target", "target.py", "--harness", "claude"], repo_root=tmp_path)
        assert code == 0
        assert "PROBLEM  missing" in capsys.readouterr().out

    def test_observe_mismatch_via_main_prints_missing_and_extra_and_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(tmp_path, "target.py", "x = 1\n")
        entries = [{"location": "repository", "sourcePath": "bogus.instructions.md"}]

        def _fake_run(*_args: object, **_kwargs: object) -> _FakeCompletedProcess:
            return _FakeCompletedProcess(0, stdout=json.dumps(entries))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        code = ec.main(
            ["--target", "target.py", "--harness", "copilot", "--observe"], repo_root=tmp_path
        )
        assert code == 1
        out = capsys.readouterr().out
        assert "MISMATCH" in out
        assert "missing (static but not observed)" in out
        assert "extra (observed but not static)" in out

    def test_observe_mismatch_via_main_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(tmp_path, "target.py", "x = 1\n")
        entries: list[dict[str, str]] = []

        def _fake_run(*_args: object, **_kwargs: object) -> _FakeCompletedProcess:
            return _FakeCompletedProcess(0, stdout=json.dumps(entries))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        code = ec.main(
            [
                "--target",
                "target.py",
                "--harness",
                "copilot",
                "--observe",
                "--json",
            ],
            repo_root=tmp_path,
        )
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["observe"]["match"] is False
        assert ".github/copilot-instructions.md" in payload["observe"]["missing"]

    def test_normalize_source_path_folds_an_absolute_path_under_repo_root(
        self, tmp_path: Path
    ) -> None:
        absolute = str(tmp_path / "a" / "b.md")
        assert ec._normalize_source_path(tmp_path, absolute) == "a/b.md"

    def test_observe_copilot_unavailable_via_main_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(tmp_path, "target.py", "x = 1\n")

        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        code = ec.main(
            ["--target", "target.py", "--harness", "copilot", "--observe"], repo_root=tmp_path
        )
        assert code == 3
        assert "not on PATH" in capsys.readouterr().err

    def test_normalize_source_path_falls_back_for_a_path_outside_repo_root(
        self, tmp_path: Path
    ) -> None:
        outside = str(tmp_path.parent / "elsewhere" / "b.md")
        result = ec._normalize_source_path(tmp_path, outside)
        assert result == Path(outside).as_posix()


class TestCli:
    def test_missing_target_and_harness_without_ci_exits_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            ec.main([])
        assert exc_info.value.code == 2

    def test_observe_with_rev_exits_two(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            ec.main(
                [
                    "--target",
                    "scripts/validation/pre_pr.py",
                    "--harness",
                    "copilot",
                    "--observe",
                    "--rev",
                    "HEAD",
                ]
            )
        assert exc_info.value.code == 2

    def test_observe_with_claude_only_exits_two(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            ec.main(
                ["--target", "scripts/validation/pre_pr.py", "--harness", "claude", "--observe"]
            )
        assert exc_info.value.code == 2

    def test_target_outside_repo_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = ec.main(["--target", "../outside.py", "--harness", "claude"])
        assert code == 2
        assert "escapes the repository" in capsys.readouterr().err

    def test_invalid_rev_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = ec.main(
            [
                "--target",
                "scripts/validation/pre_pr.py",
                "--harness",
                "claude",
                "--rev",
                "not-a-rev",
            ]
        )
        assert code == 2
        assert "does not resolve to a commit" in capsys.readouterr().err

    def test_json_output_is_valid_json_with_expected_keys(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = ec.main(
            ["--target", "scripts/validation/pre_pr.py", "--harness", "claude", "--json"]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["target"] == "scripts/validation/pre_pr.py"
        assert payload[0]["harness"] == "claude"
        assert "path_local_bytes" in payload[0]["totals"]

    def test_table_output_runs_for_both_harnesses(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = ec.main(["--target", "scripts/validation/pre_pr.py", "--harness", "both"])
        assert code == 0
        out = capsys.readouterr().out
        assert "== claude ::" in out
        assert "== copilot ::" in out
