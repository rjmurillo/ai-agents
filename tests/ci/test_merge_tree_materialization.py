"""Failure and exact-tree controls for merge-tree materialization."""

from __future__ import annotations

import errno
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from unittest.mock import call, patch

import pytest

from scripts.ci import merge_tree_materialization as _mat
from scripts.ci import merge_tree_ratchet_check as _m
from scripts.ci import ruff_count_ratchet as _ruff
from tests.ci.test_merge_tree_ratchet_check import (
    _commit_all,
    _git,
    _make_repo_with_baselines,
)

pytestmark = pytest.mark.windows_path


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
        # Issue #5441: base_ref="HEAD" is trivially a clean fast-forward, which
        # would skip materialization and read scored.py straight from repo_root,
        # trivially satisfying the assertion without ever exercising
        # export-ignore during a real checkout-index. Force the materialize
        # path so this test still covers what it names.
        patch.object(_m, "is_fast_forward_clean", return_value=False),
        patch("scripts.ci.ruff_count_ratchet.current_count", side_effect=count_materialized),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

    assert rc == _m.EXIT_OK


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_merge_tree_ruff_count_matches_direct_count_on_windows(tmp_path: Path) -> None:
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    (repo / "scored.py").write_text("import os\n", encoding="utf-8")
    _commit_all(repo, "add scored file")
    real_ruff_count = _ruff.current_count
    direct_count = real_ruff_count(repo)
    merged_counts: list[int] = []

    def count_merged_tree(root: Path) -> int:
        count = real_ruff_count(root)
        assert count is not None
        merged_counts.append(count)
        return count

    with (
        # Issue #5441: force the materialize path. base_ref="HEAD" is a clean
        # fast-forward, which would skip materialize_tree entirely, and this
        # test exists specifically to prove the Windows path-separator patch
        # does not break counting during materialization.
        patch.object(_m, "is_fast_forward_clean", return_value=False),
        patch.object(_mat.os, "sep", "\\"),
        patch(
            "scripts.ci.ruff_count_ratchet.current_count",
            side_effect=count_merged_tree,
        ),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])

    assert direct_count is not None
    assert direct_count > 0
    assert rc == _m.EXIT_OK
    assert merged_counts == [direct_count]


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
    """Issue #5441: forces the materialize path.

    base_ref="HEAD" is a clean fast-forward, which skips
    ``_materialize_tree``/``_init_scratch_repo`` entirely and reads
    ``repo_root`` directly, so without ``is_fast_forward_clean`` forced
    False, ``failed_step``'s mock would never be consulted.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    with (
        patch.object(_m, "is_fast_forward_clean", return_value=False),
        patch.object(_m, failed_step, return_value=False),
    ):
        rc = _m.main(["--repo-root", str(repo), "--base-ref", "HEAD"])
    assert rc == _m.EXIT_EXTERNAL


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_materialize_tree_reports_deadline_already_exhausted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Issue #5441 review: an expired deadline blocks materialize before it starts.

    Without this check, ``git read-tree``/``checkout-index`` would run
    unbounded even though the caller already knows the budget is spent,
    risking an outer SIGKILL with zero diagnostic instead of this message.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    destination = tmp_path / "materialized"

    assert _mat.materialize_tree(repo, head, destination, deadline=time.monotonic() - 1) is False
    assert "read-tree not run: deadline already exhausted" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_checkout_tree_stops_mid_sequence_when_deadline_expires_between_steps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deadline exhaustion DURING materialization, not just before it starts.

    ``read-tree`` gets a positive remaining budget and succeeds; the mocked
    clock then reports the deadline as expired before ``checkout-index``
    runs. This is exactly the gap the review named: the aggregate deadline
    inside the per-ratchet loop never fires if a step upstream of it, like
    materialization, has no bound of its own and simply keeps running.
    """
    repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    destination = tmp_path / "materialized"

    with patch.object(_mat.time, "monotonic", side_effect=[0.0, 100.0]):
        assert _mat.materialize_tree(repo, head, destination, deadline=1.0) is False
    assert "checkout-index not run: deadline already exhausted" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_init_scratch_repo_reports_deadline_already_exhausted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same deadline guard, applied to the five ``git`` calls in scratch init."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "file.txt").write_text("x\n", encoding="utf-8")

    assert _mat.init_scratch_repo(scratch, deadline=time.monotonic() - 1) is False
    assert "init not run: deadline already exhausted" in capsys.readouterr().err


def test_run_git_timeout_returns_exit_124(capsys: pytest.CaptureFixture[str]) -> None:
    """``run_git``'s own timeout handling, isolated from the callers above.

    ``resolve_executable`` is mocked alongside ``subprocess.run`` rather than
    guarding this test with the module's ``shutil.which("git")`` skip. It runs
    before the mocked ``run``, and on a machine with no git it raises, so
    ``run_git`` would return 127 from its OSError arm and this assertion would
    fail rather than exercise the timeout arm (issue #5441 review). Mocking
    both keeps the timeout arm covered where a skip would drop it: nothing in
    this test needs a real git.
    """
    with (
        patch.object(_mat, "resolve_executable", return_value="git"),
        patch.object(
            _mat.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=0.01),
        ),
    ):
        proc = _mat.run_git(Path("."), "status", timeout=0.01)
    assert proc.returncode == 124
    assert "timed out after" in proc.stderr


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
        # Issue #5441: base_ref="HEAD" is a clean fast-forward, which skips
        # materialization (and so the scratch cleanup this test targets)
        # entirely. Force the materialize path.
        patch.object(_m, "is_fast_forward_clean", return_value=False),
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
    assert remove.call_count == len(_mat._CLEANUP_RETRY_DELAYS) + 1
    assert sleep.call_args_list == [
        call(delay) for delay in _mat._CLEANUP_RETRY_DELAYS
    ]


def test_remove_tree_retries_transient_os_error(tmp_path: Path) -> None:
    target = tmp_path / "scratch"
    target.mkdir()
    real_rmtree = shutil.rmtree
    attempts = 0

    def remove_after_transient_error(path: Path, **_: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(errno.ENOTEMPTY, "directory not empty")
        real_rmtree(path)

    with (
        patch.object(
            _mat.shutil,
            "rmtree",
            side_effect=remove_after_transient_error,
        ) as remove,
        patch.object(_mat.time, "sleep") as sleep,
    ):
        error = _mat.remove_tree(target, "scratch")

    assert error is None
    assert remove.call_count == 2
    sleep.assert_called_once_with(_mat._CLEANUP_RETRY_DELAYS[0])
    assert not target.exists()


def test_remove_tree_reports_permanent_os_error_without_retry(tmp_path: Path) -> None:
    target = tmp_path / "scratch"
    target.mkdir()
    failure = OSError(errno.EIO, "I/O error")
    with (
        patch.object(_mat.shutil, "rmtree", side_effect=failure) as remove,
        patch.object(_mat.time, "sleep") as sleep,
    ):
        error = _mat.remove_tree(target, "scratch")

    assert error == "scratch cleanup failed: OSError: [Errno 5] I/O error"
    remove.assert_called_once_with(target, onexc=_mat._make_writable_and_retry)
    sleep.assert_not_called()


def test_remove_tree_missing_path_does_not_retry(tmp_path: Path) -> None:
    target = tmp_path / "missing"
    with (
        patch.object(_mat.shutil, "rmtree", side_effect=FileNotFoundError) as remove,
        patch.object(_mat.time, "sleep") as sleep,
    ):
        error = _mat.remove_tree(target, "scratch")

    assert error is None
    remove.assert_called_once_with(target, onexc=_mat._make_writable_and_retry)
    sleep.assert_not_called()


def test_make_writable_and_retry_clears_readonly_attribute(tmp_path: Path) -> None:
    target = tmp_path / "readonly"
    target.write_text("content", encoding="utf-8")
    target.chmod(target.stat().st_mode & ~stat.S_IWRITE)

    with patch.object(_mat.os, "chmod", wraps=os.chmod) as chmod:
        _mat._make_writable_and_retry(os.unlink, str(target), PermissionError())

    assert not target.exists()
    chmod.assert_called_once()


@pytest.mark.parametrize("missing_step", ["stat", "retry"])
def test_make_writable_and_retry_accepts_concurrent_removal(
    tmp_path: Path, missing_step: str
) -> None:
    target = tmp_path / "disappearing"
    target.write_text("content", encoding="utf-8")

    if missing_step == "stat":
        target.unlink()
        _mat._make_writable_and_retry(os.unlink, str(target), PermissionError())
    else:
        def removed_before_retry(path: str) -> None:
            Path(path).unlink()
            raise FileNotFoundError(path)

        _mat._make_writable_and_retry(
            removed_before_retry, str(target), PermissionError()
        )

    assert not target.exists()


def test_make_writable_and_retry_reraises_non_permission_error(
    tmp_path: Path,
) -> None:
    target = tmp_path / "locked"
    failure = OSError(errno.EBUSY, "busy")

    with pytest.raises(OSError, match="busy"):
        _mat._make_writable_and_retry(os.unlink, str(target), failure)


def test_remove_tree_clears_readonly_files(tmp_path: Path) -> None:
    target = tmp_path / "scratch"
    target.mkdir()
    readonly = target / "pack.idx"
    readonly.write_text("index\n", encoding="utf-8")
    readonly.chmod(stat.S_IREAD)

    assert _mat.remove_tree(target, "scratch") is None
    assert not target.exists()
