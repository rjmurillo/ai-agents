#!/usr/bin/env python3
"""Verify a packed npm tarball holds the files the CLI needs at run time.

``npm pack`` succeeds when ``bundle/assets/`` is missing, because ``files`` is an
allowlist and npm skips an entry that does not exist. A tarball without the kit
passes every other check and then fails each ``ai-agents init`` with ENOENT
(issue #7217). This script opens the packed file and refuses that tarball.

Stdlib only (``ci-scripts.md`` MUST 18): the workflow step runs bare ``python3``.

EXIT CODES (ADR-035):
  0  - The tarball holds every required entry
  1  - A required entry is missing, or the directory does not hold one tarball
  2  - Usage error
  3  - The tarball cannot be read
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from collections.abc import Sequence
from pathlib import Path

EXIT_OK, EXIT_MISSING, EXIT_USAGE, EXIT_UNREADABLE = 0, 1, 2, 3

# npm prefixes every tarball member with ``package/``.
ASSETS_PREFIX = "package/bundle/assets/"
REQUIRED_FILES = (
    "package/package.json",
    "package/README.md",
    "package/LICENSE",
    "package/dist/cli.js",
)
# ``init`` copies these three trees. A bundle that holds only top-level files
# (CLAUDE.md, AGENTS.md, notices) would pass a bare "any file" check.
REQUIRED_TREES = (
    "package/bundle/assets/agents/",
    "package/bundle/assets/skills/",
    "package/bundle/assets/rules/",
)


def missing_entries(members: Sequence[tuple[str, bool, int]]) -> list[str]:
    """Return the required entries no member satisfies.

    Each member is ``(name, is_regular_file, size)``. A required file must be a
    non-empty regular file. A required tree must hold one non-empty regular file.
    """
    files = {name for name, is_file, size in members if is_file and size > 0}
    missing = [path for path in REQUIRED_FILES if path not in files]
    for tree in REQUIRED_TREES:
        if not any(name.startswith(tree) for name in files):
            missing.append(f"{tree}* (at least one non-empty file)")
    return missing


def find_tarball(directory: Path) -> Path:
    """Return the single ``.tgz`` in ``directory``. Raises ``ValueError`` otherwise."""
    tarballs = sorted(directory.glob("*.tgz"))
    if len(tarballs) != 1:
        raise ValueError(f"expected exactly one .tgz in {directory}, found {len(tarballs)}")
    return tarballs[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True, help="Directory holding the tarball")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        tarball = find_tarball(args.dir)
    except ValueError as exc:
        print(f"[FAIL] tarball contents: {exc}", file=sys.stderr)
        return EXIT_MISSING
    try:
        with tarfile.open(tarball, "r:gz") as archive:
            members = [(m.name, m.isfile(), m.size) for m in archive.getmembers()]
    except (OSError, tarfile.TarError) as exc:
        print(
            f"[BLOCKED] tarball contents: cannot read {tarball.name}, {type(exc).__name__}",
            file=sys.stderr,
        )
        return EXIT_UNREADABLE
    missing = missing_entries(members)
    if missing:
        for entry in missing:
            print(f"[FAIL] tarball contents: {tarball.name} lacks {entry}", file=sys.stderr)
        return EXIT_MISSING
    assets = sum(1 for name, is_file, _ in members if is_file and name.startswith(ASSETS_PREFIX))
    print(
        f"tarball contents OK: {tarball.name}, {len(members)} entries, {assets} in bundle/assets/"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
