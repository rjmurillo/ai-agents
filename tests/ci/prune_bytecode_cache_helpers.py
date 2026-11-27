"""Shared helpers for the prune_bytecode_cache tests."""

from __future__ import annotations

import importlib.util
import marshal
import py_compile
import sys
from pathlib import Path

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
