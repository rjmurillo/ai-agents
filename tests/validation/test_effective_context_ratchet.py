"""Tests for the ratchet and --observe in scripts/validation/effective_context.py.

Split out of ``test_effective_context.py`` (1196 lines, over the taste-lints
500-line ERROR threshold): the CI-facing checks (REQ-3 ``--observe``, REQ-6/7
the frozen-target ratchet and its ceiling label, and issue #4880 AC7's
directory-discovery ratchet) live here; CLI argument handling and dispatch
stay in ``test_effective_context.py``.
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
from tests.validation._effective_context_helpers import (
    FakeCompletedProcess,
    _build_claude_copilot_tree,
    _commit_all,
    _init_git_repo,
    _write,
)

# --------------------------------------------------------------------------
# REQ-3: --observe compares the static Copilot set with a live listing.
# --------------------------------------------------------------------------


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

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(0, stdout=json.dumps(entries))

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

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(0, stdout=json.dumps(entries))

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

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(1, stderr="boom")

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        with pytest.raises(ec.CopilotUnavailableError):
            ec.run_copilot_observe(tmp_path, "", set())

    def test_observe_raises_on_malformed_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3 / ADR-035 exit 3: unparsable stdout is external, not a crash."""

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(0, stdout="not json")

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        with pytest.raises(ec.CopilotUnavailableError, match="unparsable"):
            ec.run_copilot_observe(tmp_path, "", set())

    def test_observe_raises_when_an_entry_is_not_an_object(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-3 / ADR-035 exit 3: a non-object entry is malformed, not a crash."""

        def _fake_run(*_args: object, **_kwargs: object) -> FakeCompletedProcess:
            return FakeCompletedProcess(0, stdout=json.dumps(["not-an-object"]))

        monkeypatch.setattr(ec.subprocess, "run", _fake_run)
        with pytest.raises(ec.CopilotUnavailableError, match="unparsable"):
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
# Issue #4880 AC7: the ratchet must cover every instructed directory, not
# only the five frozen targets. `--ci` enumerates every git-tracked
# directory with a nested CLAUDE.md/AGENTS.md and checks it against
# PATH_LOCAL_DIRECTORY_CEILING.
# --------------------------------------------------------------------------


class TestDiscoverNestedDirectories:
    def test_raises_when_git_binary_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR-035 exit 3: a missing `git` binary is external, not a silent pass."""

        def _fake_run(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(ecr.subprocess, "run", _fake_run)
        with pytest.raises(ecr.GitUnavailableError):
            ecr.discover_nested_directories(tmp_path)

    def test_finds_nested_directories_and_excludes_the_repo_root(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "AGENTS.md", "root\n")
        _write(tmp_path, "a/CLAUDE.md", "x\n")
        _write(tmp_path, "b/c/AGENTS.md", "x\n")
        _commit_all(tmp_path, "v1")

        directories, excluded = ecr.discover_nested_directories(tmp_path)
        assert directories == ["a", "b/c"]
        assert excluded == []

    def test_excludes_fixture_tree_paths_and_reports_them(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "a/CLAUDE.md", "x\n")
        _write(tmp_path, "tests/fixtures/CLAUDE.md", "should be excluded\n")
        _write(tmp_path, "tests/Fixtures/nested/AGENTS.md", "also excluded, case-insensitive\n")
        _commit_all(tmp_path, "v1")

        directories, excluded = ecr.discover_nested_directories(tmp_path)
        assert directories == ["a"]
        assert excluded == [
            "tests/Fixtures/nested/AGENTS.md",
            "tests/fixtures/CLAUDE.md",
        ]

    def test_untracked_files_are_not_discovered(self, tmp_path: Path) -> None:
        """Only git-tracked files count: an untracked nested file is invisible."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _commit_all(tmp_path, "v1")
        _write(tmp_path, "untracked/CLAUDE.md", "never committed\n")

        directories, _excluded = ecr.discover_nested_directories(tmp_path)
        assert directories == []

    def test_raises_outside_a_git_repository(self, tmp_path: Path) -> None:
        """`git ls-files` failing must not be silently read as "no directories".

        A vacuous `([], [])` would let `check_directory_ceiling` pass with
        zero directories checked, reporting green when the check never ran
        at all.
        """
        _write(tmp_path, "a/CLAUDE.md", "x\n")
        with pytest.raises(ecr.GitUnavailableError):
            ecr.discover_nested_directories(tmp_path)


class TestDirectoryCeiling:
    def test_real_repository_passes_the_directory_ceiling(self) -> None:
        ok, _report, failures, _excluded = ec.check_directory_ceiling(
            REPO_ROOT, ec.PATH_LOCAL_DIRECTORY_CEILINGS
        )
        assert ok, failures

    def test_synthetic_directory_growth_fails_and_names_everything(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "grown/CLAUDE.md", "x" * 500 + "\n")
        _commit_all(tmp_path, "v1")

        ceilings = {("grown", "claude"): 10, ("grown", "copilot"): 10}
        ok, report, failures, excluded = ec.check_directory_ceiling(tmp_path, ceilings)
        assert ok is False
        assert excluded == []
        assert any("FAIL" in line and "grown" in line for line in report)
        assert len(failures) == 2  # claude and copilot both breach
        for line in failures:
            assert "grown" in line
            assert "exceed ceiling 10" in line
            assert "--target grown --harness" in line

    def test_directory_missing_from_the_map_fails_and_names_the_constant(
        self, tmp_path: Path
    ) -> None:
        """A newly discovered directory with no ceiling entry fails, not passes silently."""
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "new_dir/CLAUDE.md", "x\n")
        _commit_all(tmp_path, "v1")

        ok, _report, failures, _excluded = ec.check_directory_ceiling(tmp_path, {})
        assert ok is False
        assert len(failures) == 2  # claude and copilot both missing
        for line in failures:
            assert "new_dir" in line
            assert "PATH_LOCAL_DIRECTORY_CEILINGS" in line

    def test_directory_ceiling_pass_at_exact_boundary(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        nested_bytes = _write(tmp_path, "a/CLAUDE.md", "12345\n")
        _commit_all(tmp_path, "v1")

        ceilings = {("a", "claude"): nested_bytes, ("a", "copilot"): nested_bytes}
        ok, _report, failures, _excluded = ec.check_directory_ceiling(tmp_path, ceilings)
        assert ok is True
        assert failures == []

    def test_ceiling_label_covers_the_directory_ceiling_too(self) -> None:
        """The directory ceiling map reuses the same local/measured/no-vendor label."""
        assert ec.PATH_LOCAL_DIRECTORY_CEILINGS
        assert all(value >= 0 for value in ec.PATH_LOCAL_DIRECTORY_CEILINGS.values())
        assert "local" in ec.CEILING_LABEL.lower()
        assert "no vendor" in ec.CEILING_LABEL.lower()

    def test_map_covers_every_discovered_directory_and_both_harnesses(self) -> None:
        """Every directory `discover_nested_directories` finds has both harness entries."""
        directories, _excluded = ecr.discover_nested_directories(REPO_ROOT)
        for directory in directories:
            assert (directory, "claude") in ec.PATH_LOCAL_DIRECTORY_CEILINGS
            assert (directory, "copilot") in ec.PATH_LOCAL_DIRECTORY_CEILINGS


class TestCiIncludesDirectoryRatchet:
    def test_ci_runs_the_real_directory_ratchet_and_exits_zero(self) -> None:
        assert ec.main(["--ci"]) == 0

    def test_ci_exits_three_when_git_ls_files_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ADR-035: a broken `git ls-files` is an external error, not a silent pass."""
        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 3
        assert "git" in capsys.readouterr().err.lower()

    def test_ci_fails_and_names_directory_harness_bytes_ceiling_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "grown/CLAUDE.md", "x" * 500 + "\n")
        _commit_all(tmp_path, "v1")
        monkeypatch.setattr(ec, "CEILINGS_BYTES", {})
        monkeypatch.setattr(
            ec, "PATH_LOCAL_DIRECTORY_CEILINGS", {("grown", "claude"): 10, ("grown", "copilot"): 10}
        )

        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 1
        out = capsys.readouterr().out
        assert "grown" in out
        assert "claude" in out
        assert "ceiling=" in out
        assert "--target grown --harness claude" in out

    def test_ci_reports_excluded_fixture_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path, "CLAUDE.md", "root\n")
        _write(tmp_path, "tests/fixtures/CLAUDE.md", "excluded\n")
        _commit_all(tmp_path, "v1")
        monkeypatch.setattr(ec, "CEILINGS_BYTES", {})

        code = ec.main(["--ci"], repo_root=tmp_path)
        assert code == 0
        out = capsys.readouterr().out
        assert "tests/fixtures/CLAUDE.md" in out
