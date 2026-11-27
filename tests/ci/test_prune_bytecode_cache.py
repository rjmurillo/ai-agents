"""Validity and invalidation tests for scripts/ci/prune_bytecode_cache.py."""

from __future__ import annotations

import marshal
import os
import py_compile
import sys
from pathlib import Path

import pytest

from tests.ci.prune_bytecode_cache_helpers import (
    OLD_INTERPRETER_TAG,
    OLD_PYTEST_TAG,
    PYC_BYTES,
    PYTEST_TAG,
    _paths,
    _pytest_pyc_bytes,
    _run,
    _write_pyc,
    _write_source,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="cache pruning requires POSIX directory file descriptors and O_NOFOLLOW",
)


def test_keeps_pytest_bytecode_and_removes_interpreter_bytecode(tmp_path: Path, capsys) -> None:
    workspace, cache_root = _paths(tmp_path)
    interpreter_pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    pytest_pyc = _write_pyc(workspace, cache_root, "tests/test_probe.py", PYTEST_TAG)

    assert _run(workspace, cache_root) == 0

    assert not interpreter_pyc.exists()
    assert pytest_pyc.is_file()
    output = capsys.readouterr().out
    assert "pycs_before=2" in output
    assert "pycs_after=1" in output
    assert "removed_files=1" in output


def test_keeps_a_dotted_source_name(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/foo.test.py", PYTEST_TAG)

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
        workspace,
        cache_root,
        ".pytest_tmp/head-guard-e2e-u/test_probe.py",
        PYTEST_TAG,
        source_exists=False,
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
    misplaced = cache_root / "pkg" / "__pycache__" / f"module.{PYTEST_TAG}.pyc"
    misplaced.parent.mkdir(parents=True)
    misplaced.write_bytes(PYC_BYTES)

    assert _run(workspace, cache_root) == 0

    assert not misplaced.exists()


def test_removes_a_file_with_a_valid_name_but_invalid_magic(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    invalid = _write_pyc(workspace, cache_root, "pkg/module.py", PYTEST_TAG, content=b"not a pyc")

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


def test_removes_interpreter_unchecked_hash_bytecode_after_the_source_changes(
    tmp_path: Path,
) -> None:
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

    assert not pyc.exists()


def test_removes_interpreter_bytecode_with_unknown_flag_bits(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    data = bytearray(pyc.read_bytes())
    data[4:8] = (4).to_bytes(4, "little")
    pyc.write_bytes(bytes(data))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_interpreter_flags_two_when_timestamp_data_matches(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    data = bytearray(pyc.read_bytes())
    data[4:8] = (2).to_bytes(4, "little")
    pyc.write_bytes(bytes(data))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_timestamp_bytecode_the_import_machinery_would_reuse(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = workspace / "pkg" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text('VALUE = "old"\n', encoding="utf-8")
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    original_stat = source.stat()
    source.write_text('VALUE = "new"\n', encoding="utf-8")
    os.utime(source, (original_stat.st_atime, original_stat.st_mtime))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_timestamp_bytecode_with_same_size_and_whole_second_mtime(tmp_path: Path) -> None:
    """A same-second edit can satisfy timestamp validation while carrying stale code."""
    workspace, cache_root = _paths(tmp_path)
    source = workspace / "pkg" / "module.py"
    source.parent.mkdir(parents=True)
    old = 'VALUE = "old"\n'
    new = 'VALUE = "new"\n'
    assert len(old) == len(new)
    source.write_text(old, encoding="utf-8")
    original_mtime = 1_700_000_000.1
    os.utime(source, (original_mtime, original_mtime))
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py")
    changed_mtime = original_mtime + 0.8
    source.write_text(new, encoding="utf-8")
    os.utime(source, (changed_mtime, changed_mtime))
    assert int(original_mtime) == int(changed_mtime)

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


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
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py", PYTEST_TAG)
    pyc.write_bytes(pyc.read_bytes()[:16] + marshal.dumps({"not": "code"}))

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()


def test_removes_a_symlink_even_when_its_name_looks_valid(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    valid = _write_pyc(workspace, cache_root, "pkg/module.py", PYTEST_TAG)
    _write_source(workspace, "pkg/linked.py")
    link = valid.with_name(f"linked.{PYTEST_TAG}.pyc")
    link.symlink_to(valid)

    assert _run(workspace, cache_root) == 0

    assert not link.exists()
    assert valid.is_file()


def test_a_hardlinked_cache_entry_is_removed_without_touching_the_other_name(
    tmp_path: Path,
) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "pkg/module.py", PYTEST_TAG)
    outside = tmp_path / "outside-hardlink.pyc"
    os.link(pyc, outside)

    assert _run(workspace, cache_root) == 0

    assert not pyc.exists()
    assert outside.is_file()
    assert outside.read_bytes() == _pytest_pyc_bytes(workspace / "pkg" / "module.py")
