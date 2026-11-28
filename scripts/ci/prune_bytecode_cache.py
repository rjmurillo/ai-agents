#!/usr/bin/env python3
"""Prune a prefixed bytecode cache to entries a later pytest run can read.

The cache root is the checkout-shaped subtree of PYTHONPYCACHEPREFIX. Validation
resolves the workspace and cache root to real paths, rejects any overlap with
the workspace, and requires the resolved root to keep the resolved workspace as
a proper trailing path. The bytecode cache prefix is the resolved leading path
left after that workspace tail. Equality with that prefix is rejected because
the prefix itself covers every source tree rather than only this checkout.

A file may remain only when it is regular pytest-rewritten bytecode for the
running interpreter and pytest version, its name carries the running pytest
rewrite tag, it sits at the deterministic prefixed path Python derives for its
source, that source still exists in the checkout, its invalidation data matches
what pytest validates, and its marshal payload loads to a code object. Ordinary
interpreter bytecode is removed even when the import machinery would accept it:
timestamp validation uses whole seconds and byte count, so a same-size edit
within one second can carry stale code past that check. Every other entry is
removed, then empty directories are removed bottom up.

Traversal and deletion are anchored to one directory file descriptor for the
resolved root. Every child open uses O_NOFOLLOW relative to that descriptor, so
replacing the root's ancestor, the root, or a scanned directory with a symlink
cannot make unlink or rmdir follow that symlink outside the resolved root. The
residual race is replacement of the root or a directory with another real
directory, or a privileged bind mount, between validation and deletion. Those
cases cannot follow a symlink to victim files, and unprivileged cache writers
cannot use them to reach arbitrary directories.

--verify-only is the publisher's gate. It applies the same per-file predicate
without removing anything: a rejected entry, an empty candidate, or a file set
that changes between two scans exits 1. It exits 2 when a bytecode cache prefix
is set for the verifying interpreter, because Python could then read the
candidate as bytecode. The check never imports or executes candidate files.
It does decode each payload with marshal.loads, as the prune does. That call
does not run the payload, but marshal is not designed for untrusted data, so a
hostile payload can crash this process, which fails closed. The decode adds no
authentication: it confirms only that the bytes parse as a code object.

EXIT CODES (ADR-035):
  0 - success
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
import stat
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
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
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="read-only: exit nonzero unless every entry is a current pytest pyc",
    )
    return parser


def _current_tags() -> frozenset[str]:
    cache_tag = sys.implementation.cache_tag
    if not cache_tag:
        raise RuntimeError("sys.implementation.cache_tag is empty")
    return frozenset((f"{cache_tag}-pytest-{pytest.__version__}",))


def _resolve_existing_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{label} could not be resolved: {exc}") from exc
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    return resolved


def _path_tail(path: Path) -> tuple[str, ...]:
    return path.relative_to(path.anchor).parts


def _require_proper_containment(cache_root: Path, cache_prefix: Path) -> None:
    if cache_root == cache_prefix or not cache_root.is_relative_to(cache_prefix):
        raise ValueError("cache root must be a proper descendant of the bytecode cache prefix")


def _validate_paths(workspace: Path, cache_root: Path) -> tuple[Path, Path]:
    if not workspace.is_absolute() or not cache_root.is_absolute():
        raise ValueError("workspace and cache root must be absolute paths")
    if cache_root.is_symlink():
        raise ValueError("cache root must not be a symlink")
    workspace = _resolve_existing_directory(workspace, "workspace")
    cache_root = _resolve_existing_directory(cache_root, "cache root")
    if cache_root.is_relative_to(workspace) or workspace.is_relative_to(cache_root):
        raise ValueError("cache root must not overlap the workspace")

    workspace_tail = _path_tail(workspace)
    cache_tail = _path_tail(cache_root)
    if not workspace_tail:
        raise ValueError("workspace must not be the filesystem root")
    if (
        len(cache_tail) <= len(workspace_tail)
        or cache_tail[-len(workspace_tail) :] != workspace_tail
    ):
        raise ValueError("cache root must be the bytecode prefix concatenated with workspace")

    prefix = Path(cache_root.anchor, *cache_tail[: -len(workspace_tail)])
    prefix = _resolve_existing_directory(prefix, "bytecode cache prefix")
    _require_proper_containment(cache_root, prefix)
    return workspace, cache_root


def _directory_open_flags() -> int:
    try:
        return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    except AttributeError as exc:
        raise RuntimeError("cache pruning requires O_DIRECTORY and O_NOFOLLOW") from exc


@contextmanager
def _opened_directory(path: str | Path, *, dir_fd: int | None = None) -> Iterator[int]:
    options = {} if dir_fd is None else {"dir_fd": dir_fd}
    fd = os.open(path, _directory_open_flags(), **options)
    try:
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _opened_root_directory(path: Path) -> Iterator[int]:
    """Open an absolute directory path without following any symlink component."""
    if not path.is_absolute():
        raise ValueError("cache root must be absolute")
    fds: list[int] = []
    try:
        fd = os.open(path.anchor, _directory_open_flags())
        fds.append(fd)
        for part in _path_tail(path):
            fd = os.open(part, _directory_open_flags(), dir_fd=fds[-1])
            fds.append(fd)
        yield fds[-1]
    finally:
        for open_fd in reversed(fds):
            os.close(open_fd)


def _scan(cache_root: Path, root_fd: int) -> CacheEntries:
    files: list[Path] = []
    directories: list[Path] = []
    root_device = os.stat(".", dir_fd=root_fd, follow_symlinks=False).st_dev

    def visit(fd: int, base: Path) -> None:
        for name in os.listdir(fd):
            path = base / name
            try:
                entry_stat = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if entry_stat.st_dev != root_device:
                raise RuntimeError("cache scan crosses a filesystem boundary")
            if stat.S_ISDIR(entry_stat.st_mode):
                directories.append(path)
                with _opened_directory(name, dir_fd=fd) as child_fd:
                    visit(child_fd, path)
            else:
                files.append(path)

    visit(root_fd, cache_root)
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


def _file_open_flags() -> int:
    try:
        return os.O_RDONLY | os.O_NOFOLLOW
    except AttributeError as exc:
        raise RuntimeError("cache pruning requires O_NOFOLLOW for file opens") from exc


def _read_pyc_from_parent(name: str, parent_fd: int) -> bytes | None:
    try:
        file_fd = os.open(name, _file_open_flags(), dir_fd=parent_fd)
    except OSError:
        return None
    try:
        stream = os.fdopen(file_fd, "rb")
    except OSError:
        os.close(file_fd)
        return None
    try:
        with stream:
            return stream.read()
    except OSError:
        return None


def _source_hash_matches(data: bytes, source: Path) -> bool:
    try:
        source_bytes = source.read_bytes()
    except OSError:
        return False
    return data[8:16] == importlib.util.source_hash(source_bytes)


def _payload_is_code(data: bytes) -> bool:
    try:
        payload = marshal.loads(data[16:])
    except Exception:
        return False
    return isinstance(payload, types.CodeType)


def _consumer_accepts(data: bytes, source: Path) -> bool:
    if len(data) <= 16 or data[:4] != importlib.util.MAGIC_NUMBER:
        return False
    flags = int.from_bytes(data[4:8], "little")
    metadata_matches = flags == 3 and _source_hash_matches(data, source)
    return metadata_matches and _payload_is_code(data)


def _is_current_pyc(
    path: Path,
    cache_root: Path,
    workspace: Path,
    tags: frozenset[str],
    *,
    parent_fd: int,
) -> bool:
    try:
        entry_stat = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    if not stat.S_ISREG(entry_stat.st_mode) or entry_stat.st_nlink != 1:
        return False
    tag = _matching_tag(path.name, tags)
    if tag is None:
        return False
    source = _source_for(path, cache_root, workspace, tags)
    if source is None or not source.is_file():
        return False
    data = _read_pyc_from_parent(path.name, parent_fd)
    if data is None:
        return False
    return _consumer_accepts(data, source)


@contextmanager
def _opened_parent_directory(cache_root: Path, path: Path, root_fd: int) -> Iterator[int]:
    try:
        relative_parent = path.parent.relative_to(cache_root)
    except ValueError as exc:
        raise ValueError("cache entry must stay inside the cache root") from exc

    fds: list[int] = []
    try:
        fd = os.open(".", _directory_open_flags(), dir_fd=root_fd)
        fds.append(fd)
        for part in relative_parent.parts:
            fd = os.open(part, _directory_open_flags(), dir_fd=fds[-1])
            fds.append(fd)
        yield fds[-1]
    finally:
        for open_fd in reversed(fds):
            os.close(open_fd)


def _remove_invalid_entries(
    entries: CacheEntries, cache_root: Path, workspace: Path, root_fd: int
) -> tuple[int, list[str]]:
    tags = _current_tags()
    removed = 0
    errors: list[str] = []
    for path in entries.files:
        try:
            with _opened_parent_directory(cache_root, path, root_fd) as parent_fd:
                if _is_current_pyc(path, cache_root, workspace, tags, parent_fd=parent_fd):
                    continue
                os.unlink(path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            errors.append(f"could not remove a cache entry: {exc}")
        else:
            removed += 1
    return removed, errors


def _remove_empty_directories(
    directories: tuple[Path, ...], cache_root: Path, root_fd: int
) -> tuple[int, list[str]]:
    removed = 0
    errors: list[str] = []
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            with _opened_parent_directory(cache_root, path, root_fd) as parent_fd:
                os.rmdir(path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            continue
        except ValueError as exc:
            errors.append(f"could not remove an empty cache directory: {exc}")
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                errors.append(f"could not remove an empty cache directory: {exc}")
        else:
            removed += 1
    return removed, errors


def prune_cache(cache_root: Path, workspace: Path) -> tuple[PruneSummary, list[str]]:
    with _opened_root_directory(cache_root) as root_fd:
        before = _scan(cache_root, root_fd)
        removed_files, errors = _remove_invalid_entries(before, cache_root, workspace, root_fd)
        removed_directories, directory_errors = _remove_empty_directories(
            before.directories, cache_root, root_fd
        )
        errors.extend(directory_errors)
        after = _scan(cache_root, root_fd)
    summary = PruneSummary(
        files_before=len(before.files),
        files_after=len(after.files),
        pycs_before=before.pyc_count,
        pycs_after=after.pyc_count,
        removed_files=removed_files,
        removed_directories=removed_directories,
    )
    return summary, errors


def verify_cache(cache_root: Path, workspace: Path) -> tuple[int, list[str]]:
    """Read-only check that every entry is a current pytest pyc. Returns (pycs, rejected).

    Nothing is opened for writing, deleted, imported, or executed. The file set
    is scanned twice and any difference between the two scans is rejected, so a
    writer that adds or removes an entry during verification fails the run.
    """
    tags = _current_tags()
    rejected: list[str] = []
    with _opened_root_directory(cache_root) as root_fd:
        first = _scan(cache_root, root_fd)
        for path in first.files:
            relative = path.relative_to(cache_root)
            try:
                with _opened_parent_directory(cache_root, path, root_fd) as parent_fd:
                    current = _is_current_pyc(
                        path, cache_root, workspace, tags, parent_fd=parent_fd
                    )
            except (OSError, ValueError):
                current = False
            if not current:
                rejected.append(f"rejected cache entry: {relative}")
        second = _scan(cache_root, root_fd)
    if set(second.files) != set(first.files):
        rejected.append("cache file set changed during verification")
    return first.pyc_count, rejected


def _publisher_environment_error() -> str | None:
    """Return a message when this interpreter could read the candidate as bytecode."""
    if sys.pycache_prefix or os.environ.get("PYTHONPYCACHEPREFIX"):
        return "verification must run with no bytecode cache prefix set"
    return None


def _verify_main(workspace: Path, cache_root: Path) -> int:
    environment_error = _publisher_environment_error()
    if environment_error is not None:
        print(f"error: {environment_error}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        pycs, rejected = verify_cache(cache_root, workspace)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOGIC
    except OSError as exc:
        print(f"error: could not scan the bytecode cache: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    if pycs == 0:
        rejected.append("candidate holds no pytest bytecode")
    print(f"prune_bytecode_cache: verify pycs={pycs} rejected={len(rejected)}")
    for message in rejected:
        print(f"error: {message}", file=sys.stderr)
    return EXIT_LOGIC if rejected else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace, cache_root = _validate_paths(args.workspace, args.cache_root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if args.verify_only:
        return _verify_main(workspace, cache_root)

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
