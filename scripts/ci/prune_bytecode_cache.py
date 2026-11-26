#!/usr/bin/env python3
"""Prune a prefixed bytecode cache to entries a later pytest run can read.

The cache root is the checkout-shaped subtree of PYTHONPYCACHEPREFIX. A file
may remain only when it is regular bytecode for the running interpreter, its
name carries either the running interpreter tag or the running pytest rewrite
tag, it sits at the deterministic prefixed path Python derives for its source,
that source still exists in the checkout, its invalidation data matches what the
consumer validates, and its marshal payload loads to a code object. Every other
entry is removed, then empty directories are removed bottom up.

EXIT CODES (ADR-035):
  0 - success, including a missing cache root with zero entries examined
  1 - logic failure or invalid bytecode cache state that cannot be classified
  2 - configuration error in the workspace or cache root arguments
  3 - external filesystem error while pruning
"""

from __future__ import annotations

import argparse
import errno
import importlib.util
import marshal
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


@dataclass(frozen=True, slots=True)
class CacheEntries:
    files: tuple[Path, ...]
    directories: tuple[Path, ...]

    @property
    def pyc_count(self) -> int:
        return sum(path.suffix == ".pyc" for path in self.files)


@dataclass(frozen=True, slots=True)
class PruneSummary:
    files_before: int
    files_after: int
    pycs_before: int
    pycs_after: int
    removed_files: int
    removed_directories: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    return parser


def _current_tags() -> frozenset[str]:
    cache_tag = sys.implementation.cache_tag
    if not cache_tag:
        raise RuntimeError("sys.implementation.cache_tag is empty")
    return frozenset((cache_tag, f"{cache_tag}-pytest-{pytest.__version__}"))


def _validate_paths(workspace: Path, cache_root: Path) -> tuple[Path, Path]:
    if not workspace.is_absolute() or not cache_root.is_absolute():
        raise ValueError("workspace and cache root must be absolute paths")
    if not workspace.is_dir():
        raise ValueError("workspace must be an existing directory")
    workspace = workspace.resolve()
    cache_text = os.fspath(cache_root)
    workspace_text = os.fspath(workspace)
    if cache_text == workspace_text or not cache_text.endswith(workspace_text):
        raise ValueError("cache root must be the bytecode prefix concatenated with workspace")
    if cache_root.is_symlink():
        raise ValueError("cache root must not be a symlink")
    if cache_root.exists() and not cache_root.is_dir():
        raise ValueError("cache root must be a directory when it exists")
    return workspace, cache_root


def _raise_scan_error(error: OSError) -> None:
    raise error


def _scan(cache_root: Path) -> CacheEntries:
    files: list[Path] = []
    directories: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(
        cache_root, onerror=_raise_scan_error, followlinks=False
    ):
        base = Path(dirpath)
        files.extend(base / name for name in filenames)
        for name in dirnames:
            path = base / name
            if path.is_symlink():
                files.append(path)
            else:
                directories.append(path)
    return CacheEntries(tuple(files), tuple(directories))


def _matching_tag(name: str, tags: frozenset[str]) -> str | None:
    for tag in sorted(tags, key=len, reverse=True):
        if name.endswith(f".{tag}.pyc"):
            return tag
    return None


def _source_for(path: Path, cache_root: Path, workspace: Path, tags: frozenset[str]) -> Path | None:
    tag = _matching_tag(path.name, tags)
    if tag is None:
        return None
    try:
        relative = path.relative_to(cache_root)
    except ValueError:
        return None
    stem = path.name[: -len(f".{tag}.pyc")]
    if not stem:
        return None
    return workspace / relative.parent / f"{stem}.py"


def _read_pyc(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _source_hash_matches(data: bytes, source: Path) -> bool:
    try:
        source_bytes = source.read_bytes()
    except OSError:
        return False
    return data[8:16] == importlib.util.source_hash(source_bytes)


def _timestamp_matches(data: bytes, source: Path) -> bool:
    try:
        stat = source.stat()
    except OSError:
        return False
    recorded_mtime = int.from_bytes(data[8:12], "little")
    recorded_size = int.from_bytes(data[12:16], "little")
    return (
        recorded_mtime == int(stat.st_mtime) & 0xFFFFFFFF
        and recorded_size == stat.st_size & 0xFFFFFFFF
    )


def _interpreter_invalidation_matches(data: bytes, source: Path, flags: int) -> bool:
    if flags & ~0b11:
        return False
    if flags & 0b1:
        return (flags & 0b10) == 0 or _source_hash_matches(data, source)
    return _timestamp_matches(data, source)


def _payload_is_code(data: bytes) -> bool:
    try:
        payload = marshal.loads(data[16:])
    except Exception:
        return False
    return isinstance(payload, types.CodeType)


def _consumer_accepts(data: bytes, source: Path, *, pytest_tagged: bool) -> bool:
    if len(data) <= 16 or data[:4] != importlib.util.MAGIC_NUMBER:
        return False
    flags = int.from_bytes(data[4:8], "little")
    if pytest_tagged:
        metadata_matches = flags == 3 and _source_hash_matches(data, source)
    else:
        metadata_matches = _interpreter_invalidation_matches(data, source, flags)
    return metadata_matches and _payload_is_code(data)


def _is_current_pyc(path: Path, cache_root: Path, workspace: Path, tags: frozenset[str]) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    tag = _matching_tag(path.name, tags)
    if tag is None:
        return False
    source = _source_for(path, cache_root, workspace, tags)
    if source is None or not source.is_file():
        return False
    data = _read_pyc(path)
    if data is None:
        return False
    pytest_tag = f"{sys.implementation.cache_tag}-pytest-{pytest.__version__}"
    return _consumer_accepts(data, source, pytest_tagged=tag == pytest_tag)


def _remove_invalid_entries(
    entries: CacheEntries, cache_root: Path, workspace: Path
) -> tuple[int, list[str]]:
    tags = _current_tags()
    removed = 0
    errors: list[str] = []
    for path in entries.files:
        if _is_current_pyc(path, cache_root, workspace, tags):
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"could not remove a cache entry: {exc}")
        else:
            removed += 1
    return removed, errors


def _remove_empty_directories(directories: tuple[Path, ...]) -> tuple[int, list[str]]:
    removed = 0
    errors: list[str] = []
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                errors.append(f"could not remove an empty cache directory: {exc}")
        else:
            removed += 1
    return removed, errors


def prune_cache(cache_root: Path, workspace: Path) -> tuple[PruneSummary, list[str]]:
    if not cache_root.exists():
        summary = PruneSummary(0, 0, 0, 0, 0, 0)
        return summary, []

    before = _scan(cache_root)
    removed_files, errors = _remove_invalid_entries(before, cache_root, workspace)
    removed_directories, directory_errors = _remove_empty_directories(before.directories)
    errors.extend(directory_errors)
    after = _scan(cache_root)
    summary = PruneSummary(
        files_before=len(before.files),
        files_after=len(after.files),
        pycs_before=before.pyc_count,
        pycs_after=after.pyc_count,
        removed_files=removed_files,
        removed_directories=removed_directories,
    )
    return summary, errors


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace, cache_root = _validate_paths(args.workspace, args.cache_root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        summary, errors = prune_cache(cache_root, workspace)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOGIC
    except OSError as exc:
        print(f"error: could not scan the bytecode cache: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    print(
        "prune_bytecode_cache: "
        f"files_before={summary.files_before} files_after={summary.files_after} "
        f"pycs_before={summary.pycs_before} pycs_after={summary.pycs_after} "
        f"removed_files={summary.removed_files} "
        f"removed_directories={summary.removed_directories}"
    )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
