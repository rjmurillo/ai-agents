"""Tests for scripts/ci/prune_bytecode_cache.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from scripts.ci import prune_bytecode_cache as prune

INTERPRETER_TAG = sys.implementation.cache_tag
PYTEST_TAG = f"{INTERPRETER_TAG}-pytest-{pytest.__version__}"
OLD_PYTEST_TAG = f"{INTERPRETER_TAG}-pytest-0.0.0"
OLD_INTERPRETER_TAG = "cpython-999"
PYC_BYTES = importlib.util.MAGIC_NUMBER + b"\0" * 12


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "checkout"
    workspace.mkdir()
    cache_root = Path(f"{tmp_path / 'prefix'}{workspace}")
    cache_root.mkdir(parents=True)
    return workspace, cache_root


def _write_source(workspace: Path, relative: str) -> Path:
    source = workspace / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# source\n", encoding="utf-8")
    return source


def _write_pyc(
    workspace: Path,
    cache_root: Path,
    relative: str,
    tag: str = INTERPRETER_TAG,
    *,
    source_exists: bool = True,
    content: bytes = PYC_BYTES,
) -> Path:
    if source_exists:
        _write_source(workspace, relative)
    source = workspace / relative
    cache_path = (
        cache_root
        / source.relative_to(workspace).parent
        / f"{source.name.removesuffix('.py')}.{tag}.pyc"
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(content)
    return cache_path


def _run(workspace: Path, cache_root: Path) -> int:
    return prune.main(["--workspace", str(workspace), "--cache-root", str(cache_root)])


def test_keeps_current_interpreter_and_pytest_bytecode(tmp_path: Path, capsys) -> None:
    workspace, cache_root = _paths(tmp_path)
    interpreter_pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    pytest_pyc = _write_pyc(workspace, cache_root, "tests/test_probe.py", PYTEST_TAG)

    assert _run(workspace, cache_root) == 0

    assert interpreter_pyc.is_file()
    assert pytest_pyc.is_file()
    output = capsys.readouterr().out
    assert "pycs_before=2" in output
    assert "pycs_after=2" in output
    assert "removed_files=0" in output


def test_keeps_a_dotted_source_name(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/foo.test.py")

    assert _run(workspace, cache_root) == 0

    assert pyc.is_file()


@pytest.mark.parametrize("tag", [OLD_INTERPRETER_TAG, OLD_PYTEST_TAG])
def test_removes_bytecode_for_another_interpreter_or_pytest_tag(tmp_path: Path, tag: str) -> None:
    workspace, cache_root = _paths(tmp_path)
    stale = _write_pyc(workspace, cache_root, "tests/test_old.py", tag)

    assert _run(workspace, cache_root) == 0

    assert not stale.exists()
    assert not stale.parent.exists()


def test_removes_bytecode_whose_source_no_longer_exists(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    orphan = _write_pyc(
        workspace, cache_root, ".pytest_tmp/head-guard-e2e-u/test_probe.py", source_exists=False
    )

    assert _run(workspace, cache_root) == 0

    assert not orphan.exists()
    assert not (cache_root / ".pytest_tmp").exists()


def test_removes_files_that_are_not_bytecode(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    stray = cache_root / "notes.txt"
    stray.write_text("not bytecode", encoding="utf-8")

    assert _run(workspace, cache_root) == 0

    assert not stray.exists()


def test_removes_bytecode_in_the_unprefixed_pycache_layout(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_source(workspace, "pkg/module.py")
    misplaced = cache_root / "pkg" / "__pycache__" / f"module.{INTERPRETER_TAG}.pyc"
    misplaced.parent.mkdir(parents=True)
    misplaced.write_bytes(PYC_BYTES)

    assert _run(workspace, cache_root) == 0

    assert not misplaced.exists()


def test_removes_a_file_with_a_valid_name_but_invalid_magic(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    invalid = _write_pyc(workspace, cache_root, "pkg/module.py", content=b"not a pyc")

    assert _run(workspace, cache_root) == 0

    assert not invalid.exists()


def test_removes_a_symlink_even_when_its_name_looks_valid(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    valid = _write_pyc(workspace, cache_root, "pkg/module.py")
    _write_source(workspace, "pkg/linked.py")
    link = valid.with_name(f"linked.{INTERPRETER_TAG}.pyc")
    link.symlink_to(valid)

    assert _run(workspace, cache_root) == 0

    assert not link.exists()
    assert valid.is_file()


def test_a_missing_cache_root_is_a_zero_count_success(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "checkout"
    workspace.mkdir()
    cache_root = Path(f"{tmp_path / 'prefix'}{workspace}")

    assert _run(workspace, cache_root) == 0

    output = capsys.readouterr().out
    assert "pycs_before=0" in output
    assert "pycs_after=0" in output


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

    with mock.patch.object(Path, "unlink", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3

    assert orphan.is_file()


def test_an_empty_directory_remove_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "pkg/gone.py", source_exists=False)

    with mock.patch.object(Path, "rmdir", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3


def test_a_scan_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)

    with mock.patch.object(prune.os, "walk", side_effect=PermissionError("denied")):
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


def test_scan_error_callback_raises_the_os_error() -> None:
    error = PermissionError("denied")

    with pytest.raises(PermissionError, match="denied"):
        prune._raise_scan_error(error)


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


def test_source_mapping_rejects_a_path_outside_the_cache_root(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    outside = tmp_path / f"module.{INTERPRETER_TAG}.pyc"

    assert prune._source_for(outside, cache_root, workspace, prune._current_tags()) is None


def test_removes_a_pyc_whose_name_has_no_source_stem(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    stemless = cache_root / f".{INTERPRETER_TAG}.pyc"
    stemless.write_bytes(PYC_BYTES)

    assert _run(workspace, cache_root) == 0

    assert not stemless.exists()


def test_a_magic_read_error_marks_the_file_invalid(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")

    with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
        assert not prune._has_current_magic(pyc)


def test_a_file_that_disappears_before_removal_is_not_an_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    missing = cache_root / "missing.pyc"
    entries = prune.CacheEntries((missing,), ())

    assert prune._remove_invalid_entries(entries, cache_root, workspace) == (0, [])


def test_a_directory_that_disappears_before_removal_is_not_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing-directory"

    assert prune._remove_empty_directories((missing,)) == (0, [])
