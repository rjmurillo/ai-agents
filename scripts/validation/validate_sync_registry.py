#!/usr/bin/env python3
"""Assert every shared lib package is registered in the sync registry (Issue #1909).

`scripts/sync_plugin_lib.py` copies shared Python packages from `scripts/` to
`.claude/lib/` so the plugin install layout ships them with relative imports.
The list of pairs lives in `SYNC_PAIRS`. Nothing enforced that a newly added
shared lib package was registered there, so a new package could silently miss
the sync and crash at install time when a shimmed hook imports it.

This gate closes that provenance gap. It asserts:

1. Every package directory directly under `scripts/github_core/`,
   `scripts/hook_utilities/`, and `scripts/ai_review_common/` appears as a
   SYNC_PAIRS source. Those three directories are themselves the shared lib
   packages; the check also catches a future sub-package added beneath any of
   them.
2. Every package directory under `.claude/lib/` appears as a SYNC_PAIRS
   destination, or is named in an explicit allowlist (`LIB_ALLOWLIST`).

`SYNC_PAIRS` is imported from `sync_plugin_lib`, the single source of truth, so
this validator and the sync tool can never disagree about the registry contents.

Canonical: scripts/sync_plugin_lib.py defines the registry this validator reads.
The relevant fragment, copied verbatim:

    SYNC_PAIRS: list[tuple[str, str]] = [
        ("scripts/hook_utilities", ".claude/lib/hook_utilities"),
        ("scripts/github_core", ".claude/lib/github_core"),
        ("scripts/ai_review_common", ".claude/lib/ai_review_common"),
    ]

See `.claude/rules/canonical-source-mirror.md`.

Different than canonical: `sync_plugin_lib.py` consumes SYNC_PAIRS to copy
files. This validator only reads SYNC_PAIRS to assert registration coverage; it
copies nothing and mutates nothing. It is a read-only provenance gate, not a
second sync implementation.

Exit codes (per ADR-035):
    0 - every shared lib package is registered (or allowlisted)
    1 - one or more package directories are unregistered
    2 - config error (e.g. the repo root or sync_plugin_lib is missing)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Source directories whose package children MUST be registered as SYNC_PAIRS
# sources. These are the shared lib roots called out by Issue #1909. Keep this
# list aligned with the SYNC_PAIRS source paths in scripts/sync_plugin_lib.py:
# every synced source root belongs here so its children are scanned too.
SOURCE_ROOTS: tuple[str, ...] = (
    "scripts/github_core",
    "scripts/hook_utilities",
    "scripts/ai_review_common",
)

# `.claude/lib/` package directories that are allowed to exist without a
# SYNC_PAIRS destination. Empty today: every lib package is synced. Add a name
# here only with a comment explaining why the package is lib-only.
LIB_ALLOWLIST: frozenset[str] = frozenset()

_LIB_DIR_REL = ".claude/lib"


def _is_package_dir(path: Path) -> bool:
    """True when *path* is a directory holding a Python package.

    A package has an `__init__.py`; `__pycache__` and other bookkeeping dirs do
    not and are ignored.
    """
    return path.is_dir() and (path / "__init__.py").is_file()


def _sync_sources(sync_pairs: list[tuple[str, str]]) -> set[str]:
    """Return the set of source paths registered in SYNC_PAIRS."""
    return {src for src, _ in sync_pairs}


def _sync_destinations(sync_pairs: list[tuple[str, str]]) -> set[str]:
    """Return the set of destination paths registered in SYNC_PAIRS."""
    return {dst for _, dst in sync_pairs}


def _check_source_roots(
    repo_root: Path,
    sync_pairs: list[tuple[str, str]],
) -> list[str]:
    """Return errors for unregistered source package directories.

    Each path in SOURCE_ROOTS must itself be a registered SYNC_PAIRS source. If
    the directory contains sub-package directories, each of those must be
    registered too, so a nested package added later cannot escape the sync.
    """
    registered = _sync_sources(sync_pairs)
    errors: list[str] = []

    for root_rel in SOURCE_ROOTS:
        root = repo_root / root_rel
        if not _is_package_dir(root):
            # A missing or non-package source root is not this gate's concern;
            # sync_plugin_lib already warns when a source dir is absent.
            continue
        if root_rel not in registered:
            errors.append(
                f"source package {root_rel} is not registered in SYNC_PAIRS"
            )
        for child in sorted(root.iterdir()):
            if not _is_package_dir(child):
                continue
            child_rel = f"{root_rel}/{child.name}"
            if child_rel not in registered:
                errors.append(
                    f"source package {child_rel} is not registered in SYNC_PAIRS"
                )

    return errors


def _check_lib_destinations(
    repo_root: Path,
    sync_pairs: list[tuple[str, str]],
    allowlist: frozenset[str],
) -> list[str]:
    """Return errors for `.claude/lib/` packages with no registered destination."""
    registered = _sync_destinations(sync_pairs)
    lib_dir = repo_root / _LIB_DIR_REL
    if not lib_dir.is_dir():
        return []

    errors: list[str] = []
    for child in sorted(lib_dir.iterdir()):
        if not _is_package_dir(child):
            continue
        dst_rel = f"{_LIB_DIR_REL}/{child.name}"
        if dst_rel in registered or child.name in allowlist:
            continue
        errors.append(
            f"lib package {dst_rel} has no SYNC_PAIRS destination and is not "
            f"in LIB_ALLOWLIST"
        )
    return errors


def find_unregistered(
    repo_root: Path,
    sync_pairs: list[tuple[str, str]],
    allowlist: frozenset[str] = LIB_ALLOWLIST,
) -> list[str]:
    """Return every registration error for the given tree and registry.

    Pure over its inputs so tests can pass a synthetic repo root and a
    synthetic SYNC_PAIRS list without touching the real registry.
    """
    errors: list[str] = []
    errors.extend(_check_source_roots(repo_root, sync_pairs))
    errors.extend(_check_lib_destinations(repo_root, sync_pairs, allowlist))
    return errors


def _load_sync_pairs() -> list[tuple[str, str]]:
    """Import SYNC_PAIRS from sync_plugin_lib (single source of truth).

    Raises ImportError if the module is missing; the caller maps that to the
    ADR-035 config-error exit code.
    """
    import sync_plugin_lib

    pairs: list[tuple[str, str]] = sync_plugin_lib.SYNC_PAIRS
    return pairs


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to the repo root that contains "
        "scripts/validation/).",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[CONFIG] repo root not found: {repo_root}", file=sys.stderr)
        return 2

    try:
        sync_pairs = _load_sync_pairs()
    except ImportError as exc:
        print(f"[CONFIG] cannot import sync_plugin_lib: {exc}", file=sys.stderr)
        return 2

    errors = find_unregistered(repo_root, sync_pairs)
    if errors:
        print("[FAIL] Unregistered shared lib packages detected (Issue #1909):")
        for err in errors:
            print(f"  - {err}")
        print(
            "\nEvery shared lib package MUST be registered in "
            "scripts/sync_plugin_lib.py:SYNC_PAIRS so it ships with the plugin. "
            "Add the (source, destination) pair there, or add a lib-only "
            "package to LIB_ALLOWLIST in this script with a justifying comment."
        )
        return 1

    print("[PASS] Every shared lib package is registered in SYNC_PAIRS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
