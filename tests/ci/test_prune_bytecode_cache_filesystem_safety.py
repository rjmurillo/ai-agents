"""Filesystem-safety and configuration tests for scripts/ci/prune_bytecode_cache.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from scripts.ci import prune_bytecode_cache as prune
from tests.ci.prune_bytecode_cache_helpers import (
    INTERPRETER_TAG,
    PYC_BYTES,
    PYTEST_TAG,
    _paths,
    _run,
    _write_pyc,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="cache pruning requires POSIX directory file descriptors and O_NOFOLLOW",
)


def test_an_open_parent_descriptor_tracks_the_original_directory_across_rename(
    tmp_path: Path,
) -> None:
    workspace, cache_root = _paths(tmp_path)
    cache_dir = cache_root / "pkg"
    cache_dir.mkdir()
    original = cache_dir / f"module.{PYTEST_TAG}.pyc"
    original.write_bytes(b"original")

    with prune._opened_root_directory(cache_root) as root_fd:
        with prune._opened_parent_directory(cache_root, original, root_fd) as parent_fd:
            moved = tmp_path / "moved-cache-dir"
            cache_dir.rename(moved)
            replacement = cache_dir
            replacement.mkdir()
            (replacement / original.name).write_bytes(b"replacement")

            assert prune._read_pyc_from_parent(original.name, parent_fd) == b"original"


def test_the_scan_fails_closed_at_a_filesystem_boundary(tmp_path: Path, monkeypatch) -> None:
    workspace, cache_root = _paths(tmp_path)
    (cache_root / "mounted").mkdir()
    real_stat = os.stat

    def cross_device_stat(path, **kwargs):
        result = real_stat(path, **kwargs)
        if path == "mounted":
            return SimpleNamespace(st_mode=result.st_mode, st_dev=result.st_dev + 1)
        return result

    monkeypatch.setattr(os, "stat", cross_device_stat)

    with prune._opened_root_directory(cache_root) as root_fd:
        with pytest.raises(RuntimeError, match="filesystem boundary"):
            prune._scan(cache_root, root_fd)


def test_a_missing_cache_root_is_a_configuration_error(tmp_path: Path) -> None:
    workspace = tmp_path / "checkout"
    workspace.mkdir()
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    sentinel = prefix / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    cache_root = Path(f"{prefix}{workspace}")

    assert _run(workspace, cache_root) == 2

    assert sentinel.is_file()


def test_rejects_a_cache_root_that_is_not_the_prefixed_workspace(tmp_path: Path) -> None:
    workspace, _cache_root = _paths(tmp_path)
    wrong = tmp_path / "wrong-cache"
    wrong.mkdir()
    sentinel = wrong / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    assert _run(workspace, wrong) == 2

    assert sentinel.is_file()


def test_rejects_the_workspace_itself_as_the_cache_root(tmp_path: Path) -> None:
    workspace, _cache_root = _paths(tmp_path)
    sentinel = workspace / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    assert _run(workspace, workspace) == 2

    assert sentinel.is_file()


def test_rejects_a_dotdot_cache_root_that_resolves_to_the_workspace(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    sentinel = workspace / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    escape = Path(f"{cache_root}{'/..' * 32}{workspace}")

    assert _run(workspace, escape) == 2

    assert sentinel.is_file()


def test_rejects_an_intermediate_symlink_cache_root_that_resolves_to_the_workspace(
    tmp_path: Path,
) -> None:
    workspace, _cache_root = _paths(tmp_path)
    sentinel = workspace / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    link = tmp_path / "root-link"
    link.symlink_to("/", target_is_directory=True)
    escape = Path(f"{link}{workspace}")

    assert _run(workspace, escape) == 2

    assert sentinel.is_file()


def test_rejects_a_cache_root_inside_the_workspace(tmp_path: Path) -> None:
    workspace, _cache_root = _paths(tmp_path)
    nested = workspace / "nested-prefix" / workspace.relative_to(workspace.anchor)
    nested.mkdir(parents=True)
    sentinel = nested / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    assert _run(workspace, nested) == 2

    assert sentinel.is_file()


def test_accepts_a_symlinked_prefix_when_the_resolved_root_is_checkout_shaped(
    tmp_path: Path,
) -> None:
    workspace, _cache_root = _paths(tmp_path)
    real_prefix = tmp_path / "real-prefix"
    real_root = Path(f"{real_prefix}{workspace}")
    real_root.mkdir(parents=True)
    link_prefix = tmp_path / "link-prefix"
    link_prefix.symlink_to(real_prefix, target_is_directory=True)
    cache_root = Path(f"{link_prefix}{workspace}")
    pyc = _write_pyc(workspace, real_root, "pkg/module.py", PYTEST_TAG)

    assert _run(workspace, cache_root) == 0

    assert pyc.is_file()


def test_containment_prefix_equality_is_rejected(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"

    with pytest.raises(ValueError, match="proper descendant"):
        prune._require_proper_containment(prefix, prefix)


def test_rejects_a_symlink_cache_root(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    cache_root.rmdir()
    cache_root.symlink_to(target, target_is_directory=True)

    assert _run(workspace, cache_root) == 2

    assert sentinel.is_file()


def test_a_delete_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    orphan = _write_pyc(workspace, cache_root, "gone.py", source_exists=False)

    with mock.patch.object(os, "unlink", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3

    assert orphan.is_file()


def test_an_empty_directory_remove_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "pkg/gone.py", source_exists=False)

    with mock.patch.object(os, "rmdir", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3


def test_a_scan_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)

    with mock.patch.object(os, "listdir", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3


def test_rejects_relative_paths(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    relative = Path("relative-cache")

    assert prune.main(["--workspace", str(workspace), "--cache-root", str(relative)]) == 2
    assert prune.main(["--workspace", str(relative), "--cache-root", str(cache_root)]) == 2


def test_rejects_a_missing_workspace(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    missing = tmp_path / "missing-workspace"

    assert prune.main(["--workspace", str(missing), "--cache-root", str(cache_root)]) == 2


def test_rejects_a_cache_root_that_is_a_file(tmp_path: Path) -> None:
    workspace, _cache_root = _paths(tmp_path)
    cache_root = Path(f"{tmp_path / 'file-prefix'}{workspace}")
    cache_root.parent.mkdir(parents=True)
    cache_root.write_text("not a directory", encoding="utf-8")

    assert _run(workspace, cache_root) == 2


def test_an_empty_interpreter_cache_tag_returns_logic_error(tmp_path: Path, monkeypatch) -> None:
    workspace, cache_root = _paths(tmp_path)
    monkeypatch.setattr(sys, "implementation", SimpleNamespace(cache_tag=""))

    assert _run(workspace, cache_root) == 1


def test_removes_a_symlinked_directory_without_touching_its_target(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    target = tmp_path / "outside-target"
    target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    link = cache_root / "linked-directory"
    link.symlink_to(target, target_is_directory=True)

    assert _run(workspace, cache_root) == 0

    assert not link.exists()
    assert sentinel.is_file()


def test_a_midrun_directory_symlink_swap_cannot_delete_outside(tmp_path: Path, monkeypatch) -> None:
    workspace, cache_root = _paths(tmp_path)
    cache_dir = cache_root / "pkg"
    cache_dir.mkdir()
    victim_name = f"gone.{INTERPRETER_TAG}.pyc"
    stale = cache_dir / victim_name
    stale.write_bytes(PYC_BYTES)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / victim_name
    victim.write_text("keep", encoding="utf-8")
    swapped = False

    def swap_during_validation(path, _cache_root, _workspace, _tags, *, parent_fd) -> bool:
        nonlocal swapped
        if path == stale and not swapped:
            swapped = True
            moved = tmp_path / "moved-cache-dir"
            cache_dir.rename(moved)
            cache_dir.symlink_to(outside, target_is_directory=True)
        return False

    monkeypatch.setattr(prune, "_is_current_pyc", swap_during_validation)

    assert _run(workspace, cache_root) == 3

    assert victim.is_file()


def test_a_midrun_ancestor_symlink_swap_cannot_delete_outside(tmp_path: Path, monkeypatch) -> None:
    workspace, cache_root = _paths(tmp_path)
    victim_name = f"gone.{INTERPRETER_TAG}.pyc"
    stale = cache_root / victim_name
    stale.write_bytes(PYC_BYTES)
    outside = tmp_path / "outside"
    redirected_root = outside / cache_root.name
    redirected_root.mkdir(parents=True)
    victim = redirected_root / victim_name
    victim.write_text("keep", encoding="utf-8")
    parent = cache_root.parent
    moved_parent = tmp_path / "moved-parent"
    original_stale = moved_parent / cache_root.name / victim_name
    swapped = False

    def swap_during_validation(path, _cache_root, _workspace, _tags, *, parent_fd) -> bool:
        nonlocal swapped
        if path == stale and not swapped:
            swapped = True
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)
        return False

    monkeypatch.setattr(prune, "_is_current_pyc", swap_during_validation)

    assert _run(workspace, cache_root) == 0

    assert victim.is_file()
    assert victim.read_text(encoding="utf-8") == "keep"
    assert not original_stale.exists()


def test_the_root_open_rejects_a_relative_path() -> None:
    with pytest.raises(ValueError, match="cache root must be absolute"):
        with prune._opened_root_directory(Path("relative-cache-root")):
            pass


def test_the_root_open_refuses_a_symlinked_ancestor(tmp_path: Path) -> None:
    real = tmp_path / "real"
    child = real / "child"
    child.mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(OSError):
        with prune._opened_root_directory(link / "child"):
            pass


def test_source_mapping_rejects_a_path_outside_the_cache_root(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    outside = tmp_path / f"module.{INTERPRETER_TAG}.pyc"

    assert prune._source_for(outside, cache_root, workspace, prune._current_tags()) is None


def test_removes_a_pyc_whose_name_has_no_source_stem(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    stemless = cache_root / f".{PYTEST_TAG}.pyc"
    stemless.write_bytes(PYC_BYTES)

    assert _run(workspace, cache_root) == 0

    assert not stemless.exists()


def test_a_pyc_read_error_marks_the_file_invalid(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py", PYTEST_TAG)

    with prune._opened_root_directory(cache_root) as root_fd:
        with prune._opened_parent_directory(cache_root, pyc, root_fd) as parent_fd:
            with mock.patch.object(os, "open", side_effect=PermissionError("denied")):
                assert prune._read_pyc_from_parent(pyc.name, parent_fd) is None


def test_a_file_that_disappears_before_removal_is_not_an_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    missing = cache_root / "missing.pyc"
    entries = prune.CacheEntries((missing,), ())

    with prune._opened_directory(cache_root) as root_fd:
        assert prune._remove_invalid_entries(entries, cache_root, workspace, root_fd) == (0, [])


def test_a_directory_that_disappears_before_removal_is_not_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing-directory"

    with prune._opened_directory(tmp_path) as root_fd:
        assert prune._remove_empty_directories((missing,), tmp_path, root_fd) == (0, [])
