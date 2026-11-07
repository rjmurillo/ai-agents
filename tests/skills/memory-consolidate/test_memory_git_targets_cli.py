"""Tests for memory_git_targets.py --dry-run and --help."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[2] / ".claude" / "skills" / "memory-consolidate" / "scripts"))
import memory_git_targets as mgt

_spec = importlib.util.spec_from_file_location(
    "memory_git_targets_test_helpers", _HERE / "test_memory_git_targets.py"
)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
_head_sha = _helpers._head_sha
_init_repo = _helpers._init_repo
_write_manifest = _helpers._write_manifest


class TestDryRunAndHelp:
    def _repo_with_changed_target(self, tmp_path: Path) -> tuple[Path, str]:
        repo = _init_repo(tmp_path)
        target = ".serena/memories/test-memory.md"
        sha = _head_sha(repo)
        (repo / target).write_text("changed", encoding="utf-8")
        _write_manifest(repo, {"startingCommit": sha, "targets": [target]})
        return repo, target

    def test_restore_dry_run_lists_targets_and_leaves_worktree_alone(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo, target = self._repo_with_changed_target(tmp_path)

        assert mgt.restore(cwd=repo, dry_run=True) == mgt.EXIT_OK

        out = capsys.readouterr().out
        assert "DRY RUN: would restore 1 target(s)" in out
        assert target in out
        assert (repo / target).read_text(encoding="utf-8") == "changed"

    def test_restore_dry_run_still_rejects_an_invalid_manifest(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {"startingCommit": "not-a-sha", "targets": []})

        assert mgt.restore(cwd=repo, dry_run=True) == mgt.EXIT_LOGIC

    def test_cleanup_dry_run_keeps_the_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo, _ = self._repo_with_changed_target(tmp_path)
        manifest = mgt._manifest_path(repo)

        assert mgt.cleanup(cwd=repo, dry_run=True) == mgt.EXIT_OK

        assert manifest.is_file()
        assert "DRY RUN: would remove" in capsys.readouterr().out

    def test_cleanup_dry_run_without_manifest_reports_none(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _init_repo(tmp_path)

        assert mgt.cleanup(cwd=repo, dry_run=True) == mgt.EXIT_OK
        assert "no manifest to remove" in capsys.readouterr().out

    def test_help_exits_zero_and_documents_examples_and_exit_codes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mgt.main(["--help"]) == mgt.EXIT_OK
        out = capsys.readouterr().out
        assert "examples:" in out
        assert "exit codes:" in out
        assert "--dry-run" in out or "restore" in out

    def test_restore_help_documents_dry_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert mgt.main(["restore", "--help"]) == mgt.EXIT_OK
        assert "--dry-run" in capsys.readouterr().out

    def test_unknown_flag_is_config_error_on_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert mgt.main(["check", "--bogus"]) == mgt.EXIT_CONFIG
        assert capsys.readouterr().out == ""
