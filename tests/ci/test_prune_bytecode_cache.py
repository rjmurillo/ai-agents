"""Tests for scripts/ci/prune_bytecode_cache.py."""

from __future__ import annotations

import importlib.util
import marshal
import os
import py_compile
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
    if not source.exists():
        source.write_text("# source\n", encoding="utf-8")
    return source


def _pytest_pyc_bytes(source: Path) -> bytes:
    data = source.read_bytes()
    code = compile(data, str(source), "exec")
    flags = (3).to_bytes(4, "little")
    header = importlib.util.MAGIC_NUMBER + flags + importlib.util.source_hash(data)
    return header + marshal.dumps(code)


def _write_pyc(
    workspace: Path,
    cache_root: Path,
    relative: str,
    tag: str = INTERPRETER_TAG,
    *,
    source_exists: bool = True,
    content: bytes | None = None,
    invalidation_mode: py_compile.PycInvalidationMode = py_compile.PycInvalidationMode.TIMESTAMP,
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
    if content is not None:
        cache_path.write_bytes(content)
    elif source_exists and tag == INTERPRETER_TAG:
        py_compile.compile(
            str(source), cfile=str(cache_path), invalidation_mode=invalidation_mode, doraise=True
        )
    elif source_exists and tag == PYTEST_TAG:
        cache_path.write_bytes(_pytest_pyc_bytes(source))
    else:
        cache_path.write_bytes(PYC_BYTES)
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


@pytest.mark.parametrize("flags", [0, 1, 4])
def test_removes_pytest_bytecode_with_flags_pytest_rejects(tmp_path: Path, flags: int) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/test_probe.py", PYTEST_TAG)
    data = bytearray(pyc.read_bytes())
    data[4:8] = flags.to_bytes(4, "little")
    pyc.write_bytes(bytes(data))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_pytest_bytecode_with_a_mismatched_source_hash(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/test_probe.py", PYTEST_TAG)
    data = bytearray(pyc.read_bytes())
    data[8] ^= 0xFF
    pyc.write_bytes(bytes(data))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_pytest_bytecode_truncated_after_the_header(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/test_probe.py", PYTEST_TAG)
    pyc.write_bytes(pyc.read_bytes()[:16])

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_pytest_bytecode_with_a_truncated_marshal_payload(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/test_probe.py", PYTEST_TAG)
    pyc.write_bytes(pyc.read_bytes()[:32])

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_interpreter_bytecode_with_a_stale_timestamp(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = _write_source(workspace, "pkg/module.py")
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    source.write_text("# source changed to a different length\n", encoding="utf-8")

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_interpreter_bytecode_with_a_mismatched_checked_hash(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = _write_source(workspace, "pkg/module.py")
    pyc = _write_pyc(
        workspace,
        cache_root,
        "pkg/module.py",
        invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
    )
    source.write_text("# changed\n", encoding="utf-8")

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_keeps_interpreter_unchecked_hash_bytecode_after_the_source_changes(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = _write_source(workspace, "pkg/module.py")
    pyc = _write_pyc(
        workspace,
        cache_root,
        "pkg/module.py",
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    source.write_text("# changed\n", encoding="utf-8")

    assert _run(workspace, cache_root) == 0

    assert pyc.is_file()


def test_removes_interpreter_bytecode_with_unknown_flag_bits(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    data = bytearray(pyc.read_bytes())
    data[4:8] = (4).to_bytes(4, "little")
    pyc.write_bytes(bytes(data))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_keeps_interpreter_flags_two_when_timestamp_data_matches(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    data = bytearray(pyc.read_bytes())
    data[4:8] = (2).to_bytes(4, "little")
    pyc.write_bytes(bytes(data))

    assert _run(workspace, cache_root) == 0

    assert pyc.is_file()


def test_keeps_timestamp_bytecode_the_import_machinery_would_reuse(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = workspace / "pkg" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text('VALUE = "old"\n', encoding="utf-8")
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    original_stat = source.stat()
    source.write_text('VALUE = "new"\n', encoding="utf-8")
    os.utime(source, (original_stat.st_atime, original_stat.st_mtime))

    assert _run(workspace, cache_root) == 0

    assert pyc.is_file()


def test_removes_interpreter_bytecode_truncated_after_the_header(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    pyc.write_bytes(pyc.read_bytes()[:16])

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_bytecode_with_a_truncated_marshal_payload(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    pyc.write_bytes(pyc.read_bytes()[:32])

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_bytecode_whose_payload_is_not_a_code_object(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    pyc.write_bytes(pyc.read_bytes()[:16] + marshal.dumps({"not": "code"}))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_a_symlink_even_when_its_name_looks_valid(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    valid = _write_pyc(workspace, cache_root, "pkg/module.py")
    _write_source(workspace, "pkg/linked.py")
    link = valid.with_name(f"linked.{INTERPRETER_TAG}.pyc")
    link.symlink_to(valid)

    assert _run(workspace, cache_root) == 0

    assert not link.exists()
    assert valid.is_file()


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
    pyc = _write_pyc(workspace, real_root, "pkg/module.py")

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

    with mock.patch.object(prune.os, "unlink", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3

    assert orphan.is_file()


def test_an_empty_directory_remove_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "pkg/gone.py", source_exists=False)

    with mock.patch.object(prune.os, "rmdir", side_effect=PermissionError("denied")):
        assert _run(workspace, cache_root) == 3


def test_a_scan_failure_returns_external_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)

    with mock.patch.object(prune.os, "listdir", side_effect=PermissionError("denied")):
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

    def swap_during_validation(path, _cache_root, _workspace, _tags) -> bool:
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


def test_a_pyc_read_error_marks_the_file_invalid(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")

    with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
        assert prune._read_pyc(pyc) is None


def test_a_file_that_disappears_before_removal_is_not_an_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    missing = cache_root / "missing.pyc"
    entries = prune.CacheEntries((missing,), ())

    assert prune._remove_invalid_entries(entries, cache_root, workspace) == (0, [])


def test_a_directory_that_disappears_before_removal_is_not_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing-directory"

    assert prune._remove_empty_directories((missing,), tmp_path) == (0, [])
