#!/usr/bin/env python3
# DELETE-AFTER-MERGE: This script is one-shot. It is idempotent on re-run
# but unnecessary post-PR-1819-merge: every production hook is already on
# the inline manifest-walk-up bootstrap. Delete with the next housekeeping
# pass once PR #1819 has shipped to consumers.
"""REQ-003: replace `setup_hook_lib_path` call with inline bootstrap.

ADR-047 ships a test (`tests/test_plugin_path_resolution.py`) that
pattern-matches the literal strings ``os.environ.get("CLAUDE_PLUGIN_ROOT")``
and ``os.path.isdir(_lib_dir)`` in every hook that imports from
``hook_utilities`` or ``github_core``. The earlier M7-T2 cleanup
extracted this logic into ``setup_hook_lib_path`` in
``.claude/lib/bootstrap.py``, which deletes those literal strings from the
hook source. The grep-style ADR-047 test then fails.

This migration restores the inline bootstrap pattern in every hook that
currently uses ``setup_hook_lib_path``. It is functionally identical to
the helper (it walks up looking for ``.claude-plugin/plugin.json`` and
checks ``CLAUDE_PLUGIN_ROOT`` first) but contains the literal strings
the ADR-047 test expects.

Idempotent: detects the inline pattern and skips already-migrated files.

Run with:
    python3 scripts/migrations/req003_inline_plugin_root_bootstrap.py
    python3 scripts/migrations/req003_inline_plugin_root_bootstrap.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

# The bootstrap shape introduced by M7-T3 (refactor extracting to bootstrap.py).
# Three lines of marker walk + sys.path.insert + import + setup call.
OLD_PATTERN = re.compile(
    r"""# Bootstrap: find lib directory and set up imports \(see bootstrap\.py for details\)\n"""
    r"""_p = Path\(__file__\)\.resolve\(\)\.parent\n"""
    r"""while _p\.parent != _p and not \(_p / "\.claude-plugin" / "plugin\.json"\)\.is_file\(\):\n"""
    r"""    _p = _p\.parent\n"""
    r"""sys\.path\.insert\(0, str\(_p / "lib"\)\)\n"""
    r"""from bootstrap import setup_hook_lib_path  # noqa: E402\n"""
    r"""setup_hook_lib_path\(__file__, fail_exit_code=(\d)\)""",
    re.MULTILINE,
)

NEW_TEMPLATE = '''# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {{_lib_dir}} (CLAUDE_PLUGIN_ROOT={{_plugin_root!r}})", file=sys.stderr)
    sys.exit({exit_code})
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)'''

ALREADY_MIGRATED_MARKER = 'os.environ.get("CLAUDE_PLUGIN_ROOT")'


def migrate_file(path: Path, *, dry_run: bool = False) -> str:
    """Return one of: migrated, already-migrated, skipped-no-pattern, error.

    When ``dry_run`` is True the file on disk is not modified, but the
    return value is identical to a real run. ``migrated`` then means
    "would have been migrated".
    """
    text = path.read_text(encoding="utf-8")
    match = OLD_PATTERN.search(text)
    if match is None:
        if ALREADY_MIGRATED_MARKER in text:
            return "already-migrated"
        return "skipped-no-pattern"
    exit_code = match.group(1)
    replacement = NEW_TEMPLATE.format(exit_code=exit_code)
    new_text = OLD_PATTERN.sub(lambda _m: replacement, text, count=1)
    if new_text == text:
        return "error"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return "migrated"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate hooks from setup_hook_lib_path to the inline "
            "manifest-walk-up bootstrap pattern."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing to disk.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not HOOKS_DIR.is_dir():
        print(f"hooks dir not found: {HOOKS_DIR}", file=sys.stderr)
        return 2

    results: dict[str, list[str]] = {
        "migrated": [],
        "already-migrated": [],
        "skipped-no-pattern": [],
        "error": [],
    }

    for path in sorted(HOOKS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        content = path.read_text(encoding="utf-8")
        # Only consider hooks that actually import from the shared lib.
        if "from hook_utilities" not in content and "from github_core" not in content:
            continue
        outcome = migrate_file(path, dry_run=args.dry_run)
        results[outcome].append(str(path.relative_to(REPO_ROOT)))

    if args.dry_run:
        print("(dry-run: no files modified)")
    for outcome, files in results.items():
        print(f"{outcome}: {len(files)}")
        for f in files:
            print(f"  {f}")

    return 1 if results["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
