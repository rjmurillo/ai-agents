"""Tests for the read-only publisher mode of scripts/ci/prune_bytecode_cache.py.

Every fixture is inert: valid-looking headers around bytes that are empty,
random, or a code object that only writes a canary file inside tmp_path if it is
ever executed. The verifier must never run it.
"""

from __future__ import annotations

import importlib.util
import marshal
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import prune_bytecode_cache as prune
from tests.ci.prune_bytecode_cache_helpers import (
    INTERPRETER_TAG,
    OLD_INTERPRETER_TAG,
    OLD_PYTEST_TAG,
    PYTEST_TAG,
    _paths,
    _write_pyc,
    _write_source,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="cache verification requires POSIX directory file descriptors and O_NOFOLLOW",
)


@pytest.fixture(autouse=True)
def _no_bytecode_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONPYCACHEPREFIX", raising=False)
    monkeypatch.setattr(sys, "pycache_prefix", None)


def _verify(workspace: Path, cache_root: Path) -> int:
    return prune.main(
        ["--verify-only", "--workspace", str(workspace), "--cache-root", str(cache_root)]
    )


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def _header(source: Path) -> bytes:
    data = source.read_bytes()
    return (
        importlib.util.MAGIC_NUMBER + (3).to_bytes(4, "little") + importlib.util.source_hash(data)
    )


def test_accepts_a_tree_of_current_pytest_bytecode(tmp_path: Path, capsys) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_a.py", PYTEST_TAG)
    _write_pyc(workspace, cache_root, "tests/sub/test_b.py", PYTEST_TAG)
    assert _verify(workspace, cache_root) == 0
    assert "verify pycs=2 rejected=0" in capsys.readouterr().out


def test_verification_changes_nothing_on_disk(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_a.py", PYTEST_TAG)
    _write_pyc(workspace, cache_root, "tests/test_stale.py", OLD_PYTEST_TAG)
    before = _snapshot(cache_root)
    assert _verify(workspace, cache_root) == 1
    assert _snapshot(cache_root) == before


@pytest.mark.parametrize("tag", [OLD_PYTEST_TAG, OLD_INTERPRETER_TAG])
def test_rejects_bytecode_for_another_pytest_or_interpreter_tag(
    tmp_path: Path, tag: str, capsys
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    _write_pyc(workspace, cache_root, "tests/test_old.py", tag)
    assert _verify(workspace, cache_root) == 1
    assert "rejected cache entry: tests/test_old." in capsys.readouterr().err


def test_rejects_ordinary_interpreter_bytecode(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    _write_pyc(workspace, cache_root, "pkg/module.py", INTERPRETER_TAG)
    assert _verify(workspace, cache_root) == 1


def test_rejects_a_pyc_whose_source_is_missing(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    _write_pyc(workspace, cache_root, "tests/test_gone.py", PYTEST_TAG, source_exists=False)
    assert _verify(workspace, cache_root) == 1


def test_rejects_a_pyc_whose_source_changed_after_the_pyc_was_written(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    source = _write_source(workspace, "tests/test_edit.py")
    _write_pyc(workspace, cache_root, "tests/test_edit.py", PYTEST_TAG)
    source.write_text("# edited\n", encoding="utf-8")
    assert _verify(workspace, cache_root) == 1


def test_rejects_a_garbage_payload_behind_a_correct_header(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = _write_source(workspace, "tests/test_bad.py")
    _write_pyc(
        workspace,
        cache_root,
        "tests/test_bad.py",
        PYTEST_TAG,
        content=_header(source) + b"\x00not marshal data",
    )
    assert _verify(workspace, cache_root) == 1


def test_rejects_a_non_code_payload_behind_a_correct_header(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = _write_source(workspace, "tests/test_bad.py")
    _write_pyc(
        workspace,
        cache_root,
        "tests/test_bad.py",
        PYTEST_TAG,
        content=_header(source) + marshal.dumps({"not": "code"}),
    )
    assert _verify(workspace, cache_root) == 1


def test_rejects_a_wrong_magic_number_and_wrong_flags(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    source = _write_source(workspace, "tests/test_magic.py")
    payload = marshal.dumps(compile("pass", "x", "exec"))
    _write_pyc(
        workspace,
        cache_root,
        "tests/test_magic.py",
        PYTEST_TAG,
        content=b"\x00\x00\x00\x00" + _header(source)[4:] + payload,
    )
    other = _write_source(workspace, "tests/test_flags.py")
    _write_pyc(
        workspace,
        cache_root,
        "tests/test_flags.py",
        PYTEST_TAG,
        content=importlib.util.MAGIC_NUMBER
        + (0).to_bytes(4, "little")
        + _header(other)[8:]
        + payload,
    )
    assert _verify(workspace, cache_root) == 1


def test_never_executes_a_candidate_whose_code_would_write_a_canary(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    canary = tmp_path / "canary.txt"
    source = _write_source(workspace, "tests/test_canary.py")
    code = compile(f"open({str(canary)!r}, 'w').close()", "canary", "exec")
    _write_pyc(
        workspace,
        cache_root,
        "tests/test_canary.py",
        PYTEST_TAG,
        content=_header(source) + marshal.dumps(code),
    )
    assert _verify(workspace, cache_root) == 0
    assert not canary.exists()


def test_rejects_a_symlink_entry_and_never_follows_it(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    outside = tmp_path / "outside.pyc"
    outside.write_bytes(b"outside")
    link = cache_root / "tests" / f"test_link.{PYTEST_TAG}.pyc"
    link.symlink_to(outside)
    assert _verify(workspace, cache_root) == 1
    assert outside.read_bytes() == b"outside"


def test_rejects_a_hard_linked_entry(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    pyc = _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    os.link(pyc, tmp_path / "second-name")
    assert _verify(workspace, cache_root) == 1


def test_rejects_a_stray_non_bytecode_file(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    (cache_root / "tests" / "notes.txt").write_text("stray", encoding="utf-8")
    assert _verify(workspace, cache_root) == 1


def test_rejects_an_empty_candidate(tmp_path: Path, capsys) -> None:
    workspace, cache_root = _paths(tmp_path)
    assert _verify(workspace, cache_root) == 1
    assert "candidate holds no pytest bytecode" in capsys.readouterr().err


def test_rejects_a_candidate_with_only_directories(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    (cache_root / "tests").mkdir()
    assert _verify(workspace, cache_root) == 1


def test_a_missing_cache_root_is_a_configuration_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    cache_root.rmdir()
    assert _verify(workspace, cache_root) == 2


def test_a_symlinked_cache_root_is_a_configuration_error(tmp_path: Path) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    moved = tmp_path / "moved"
    cache_root.rename(moved)
    cache_root.symlink_to(moved, target_is_directory=True)
    assert _verify(workspace, cache_root) == 2


def test_refuses_to_run_with_a_bytecode_prefix_in_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", str(tmp_path / "prefix"))
    assert _verify(workspace, cache_root) == 2
    assert "no bytecode cache prefix" in capsys.readouterr().err


def test_refuses_to_run_with_an_interpreter_bytecode_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    monkeypatch.setattr(sys, "pycache_prefix", str(tmp_path / "prefix"))
    assert _verify(workspace, cache_root) == 2


def test_a_prefix_exits_2_before_a_planted_pytest_pyc_can_run(tmp_path: Path) -> None:
    """The prefix guard must run before `import pytest`, so a planted pyc never runs.

    In-process tests cannot see import order because pytest is already imported
    there. This one starts a real interpreter with the prefix set and a planted
    timestamp pyc for pytest/__init__.py at the path that interpreter derives.
    """
    workspace, cache_root = _paths(tmp_path)
    prefix = tmp_path / "prefix"
    canary = tmp_path / "canary.txt"
    pytest_spec = importlib.util.find_spec("pytest")
    assert pytest_spec is not None and pytest_spec.origin is not None
    source = Path(pytest_spec.origin)
    planted = (
        prefix
        / source.parent.relative_to(source.anchor)
        / f"{source.stem}.{sys.implementation.cache_tag}.pyc"
    )
    planted.parent.mkdir(parents=True)
    text = source.read_text(encoding="utf-8").replace("from __future__ import annotations\n", "", 1)
    code = compile(
        f"from __future__ import annotations\nopen({str(canary)!r}, 'w').close()\n{text}",
        str(source),
        "exec",
    )
    stat_result = source.stat()
    planted.write_bytes(
        importlib.util.MAGIC_NUMBER
        + (0).to_bytes(4, "little")
        + (int(stat_result.st_mtime) & 0xFFFFFFFF).to_bytes(4, "little")
        + (stat_result.st_size & 0xFFFFFFFF).to_bytes(4, "little")
        + marshal.dumps(code)
    )

    def pytest_pycs() -> list[str]:
        return sorted(
            str(path)
            for path in prefix.rglob("*.pyc")
            if {"pytest", "_pytest"} & set(path.relative_to(prefix).parts)
        )

    before = pytest_pycs()
    assert len(before) == 1
    tree_before = sorted(cache_root.rglob("*"))

    result = subprocess.run(
        [
            sys.executable,
            str(Path(prune.__file__)),
            "--verify-only",
            "--workspace",
            str(workspace),
            "--cache-root",
            str(cache_root),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(tmp_path),
            "PYTHONPYCACHEPREFIX": str(prefix),
        },
    )

    assert result.returncode == 2, result.stderr
    assert "no bytecode cache prefix" in result.stderr
    assert not canary.exists(), "the planted pytest pyc ran before the prefix guard"
    assert pytest_pycs() == before
    assert sorted(cache_root.rglob("*")) == tree_before


def test_rejects_a_file_set_that_changes_between_the_two_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    real_scan = prune._scan
    calls = {"count": 0}

    def racing_scan(root: Path, fd: int) -> prune.CacheEntries:
        entries = real_scan(root, fd)
        calls["count"] += 1
        if calls["count"] == 1:
            _write_pyc(workspace, cache_root, "tests/test_late.py", PYTEST_TAG)
        return entries

    monkeypatch.setattr(prune, "_scan", racing_scan)
    assert _verify(workspace, cache_root) == 1
    assert "file set changed during verification" in capsys.readouterr().err


def test_a_filesystem_boundary_in_the_scan_is_a_logic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)

    def boundary(root: Path, fd: int) -> prune.CacheEntries:
        raise RuntimeError("cache scan crosses a filesystem boundary")

    monkeypatch.setattr(prune, "_scan", boundary)
    assert _verify(workspace, cache_root) == 1


def test_an_unreadable_directory_is_an_external_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)

    def broken(root: Path, fd: int) -> prune.CacheEntries:
        raise PermissionError("denied")

    monkeypatch.setattr(prune, "_scan", broken)
    assert _verify(workspace, cache_root) == 3


def test_an_entry_that_cannot_be_opened_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)

    def unreadable(*args: object, **kwargs: object) -> bool:
        raise PermissionError("denied")

    monkeypatch.setattr(prune, "_is_current_pyc", unreadable)
    assert _verify(workspace, cache_root) == 1


def test_a_pruned_tree_always_verifies(tmp_path: Path) -> None:
    """The leg-side prune and the publisher verify apply one predicate."""
    workspace, cache_root = _paths(tmp_path)
    _write_pyc(workspace, cache_root, "tests/test_ok.py", PYTEST_TAG)
    _write_pyc(workspace, cache_root, "tests/test_old.py", OLD_PYTEST_TAG)
    _write_pyc(workspace, cache_root, "pkg/module.py", INTERPRETER_TAG)
    assert _verify(workspace, cache_root) == 1
    assert prune.main(["--workspace", str(workspace), "--cache-root", str(cache_root)]) == 0
    assert _verify(workspace, cache_root) == 0
