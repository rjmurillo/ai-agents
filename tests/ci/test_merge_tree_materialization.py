"""Failure and exact-tree controls for merge-tree materialization."""

from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path
from unittest.mock import call, patch

import pytest

from scripts.ci import merge_tree_materialization as _mat
from scripts.ci import merge_tree_ratchet_check as _m
from tests.ci.test_merge_tree_ratchet_check import (
    _commit_all,
    _git,
    _make_repo_with_baselines,
)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_export_ignored_scored_file_is_still_materialized(tmp_path: Path) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    (repo / "scored.py").write_text("scored = True\n", encoding="utf-8")
    (repo / ".gitattributes").write_text("scored.py export-ignore\n", encoding="utf-8")
    _commit_all(repo, "add export-ignored scored file")

    def count_materialized(root: Path) -> int:
        assert (root / "scored.py").read_text(encoding="utf-8") == "scored = True\n"
        return 0

    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", side_effect=count_materialized),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

    assert rc == _m.EXIT_OK


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_materialization_preserves_symlinks_when_git_config_disables_them(
    tmp_path: Path,
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    target = repo / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")
    link = repo / "package_link"
    try:
        link.symlink_to(target.name)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    _commit_all(repo, "add symlink")
    _git(repo, "config", "core.symlinks", "false")

    destination = tmp_path / "materialized"
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _mat.materialize_tree(repo, head, destination)
    assert (destination / "package_link").is_symlink()
    assert (destination / "package_link").read_text(encoding="utf-8") == "value = 1\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize("failed_step", ["_materialize_tree", "_init_scratch_repo"])
def test_materialization_or_scratch_init_failure_is_external(
    tmp_path: Path, failed_step: str
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    with patch.object(_m, failed_step, return_value=False):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
    assert rc == _m.EXIT_EXTERNAL


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_missing_git_launch_is_external(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    with patch.object(_mat, "resolve_executable", side_effect=FileNotFoundError("git")):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
    assert rc == _m.EXIT_EXTERNAL
    assert "FileNotFoundError: git" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize(
    ("ruff_count", "expected_exit"),
    [(0, _m.EXIT_EXTERNAL), (11, _m.EXIT_REGRESSION)],
)
def test_cleanup_failure_does_not_mask_primary_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    ruff_count: int,
    expected_exit: int,
) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    with (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=ruff_count),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
        patch.object(
            _m,
            "_remove_tree",
            return_value="merge-tree scratch cleanup failed: PermissionError: denied",
        ),
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

    assert rc == expected_exit
    assert "PermissionError: denied" in capsys.readouterr().err


def test_remove_tree_retries_transient_permission_error(tmp_path: Path) -> None:
    target = tmp_path / "scratch"
    target.mkdir()
    real_rmtree = shutil.rmtree
    attempts = 0

    def remove_after_transient_lock(path: Path, **_: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 4:
            raise PermissionError("pack index locked")
        real_rmtree(path)

    with (
        patch.object(
            _mat.shutil,
            "rmtree",
            side_effect=remove_after_transient_lock,
        ) as remove,
        patch.object(_mat.time, "sleep") as sleep,
    ):
        error = _mat.remove_tree(target, "scratch")

    assert error is None
    assert remove.call_count == 5
    assert sleep.call_args_list == [
        call(delay) for delay in _mat._CLEANUP_RETRY_DELAYS[:4]
    ]
    assert not target.exists()


def test_remove_tree_reports_permission_error_after_retry_budget(
    tmp_path: Path,
) -> None:
    target = tmp_path / "scratch"
    target.mkdir()
    with (
        patch.object(_mat.shutil, "rmtree", side_effect=PermissionError("denied")) as remove,
        patch.object(_mat.time, "sleep") as sleep,
    ):
        error = _mat.remove_tree(target, "scratch")

    assert error == "scratch cleanup failed: PermissionError: denied"


def test_remove_tree_clears_readonly_files(tmp_path: Path) -> None:
    target = tmp_path / "scratch"
    target.mkdir()
    readonly = target / "pack.idx"
    readonly.write_text("index\n", encoding="utf-8")
    readonly.chmod(stat.S_IREAD)

    assert _mat.remove_tree(target, "scratch") is None
    assert not target.exists()
