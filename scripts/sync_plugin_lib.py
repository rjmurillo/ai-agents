#!/usr/bin/env python3
"""Deprecated shim. The lib sync now runs inside `build/scripts/build_all.py`.

ADR-109 B5 (TASK-035) absorbed this script's `SYNC_PAIRS`, `SYNC_FILE_PAIRS`,
and `IMPORT_CONVERSIONS` copy logic into `build/scripts/lib_mirror.py`, run
by `build_all.py`'s lib step in the same invocation that renders every other
class. There is no longer a second command whose order relative to
`build_all.py` matters (issue #2613).

This file stays only because `.github/workflows/validate-generated-agents.yml`
("Plugin lib sync check (M7-T1)") still shells out to it directly, and
workflow files are out of scope for the PR that retired the rest of this
script (see that PR's description for the follow-up to repoint the
workflow at `build_all.py --check` and delete this shim). Every other
caller now calls `lib_mirror.compile_all` or `build_all.py` directly.

Usage (unchanged): `python3 scripts/sync_plugin_lib.py [--check]`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BUILD_SCRIPTS = _REPO_ROOT / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

from lib_mirror import (  # noqa: E402
    IMPORT_CONVERSIONS,  # noqa: F401  (re-exported for backward compatibility)
    PACKAGES,  # noqa: F401
    SYNC_PAIRS,  # noqa: F401  (scripts/validation/validate_sync_registry.py reads this)
    compile_all,
)

# Kept for backward compatibility with any remaining reader of the original
# name; lib_mirror.compile_all no longer takes a two-item pair list, so this
# is documentation, not a live registry, same shape as sync_plugin_lib.py's
# original SYNC_FILE_PAIRS.
SYNC_FILE_PAIRS: list[tuple[str, str]] = [
    ("scripts/hook_utilities/bootstrap.py", ".claude/lib/bootstrap.py"),
    (
        "scripts/validation/validate_review_marker.py",
        ".claude/skills/review/scripts/validate_review_marker.py",
    ),
]


def main(argv: list[str] | None = None) -> int:
    """Deprecated entry point. Delegates to `lib_mirror.compile_all`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Dry-run mode: exit 1 on drift.")
    args = parser.parse_args(argv)

    print(
        "DEPRECATED: scripts/sync_plugin_lib.py is a thin shim. Run "
        "`uv run python build/scripts/build_all.py` (or `--check`) directly; "
        "it now performs this same lib sync in the same invocation.",
        file=sys.stderr,
    )

    result = compile_all(_REPO_ROOT, check=args.check)
    if result.errors:
        for line in result.errors:
            print(line, file=sys.stderr)
        return 1
    if args.check and result.changes:
        print("Plugin lib copies are out of sync:", file=sys.stderr)
        for line in result.changes:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
