#!/usr/bin/env python3
# Delete after PR #1819 merges. Idempotent but unnecessary once all
# source hooks under .claude/hooks/ have been migrated to the marker-walk
# bootstrap; the script no-ops on already-migrated files.
"""M7-T2 one-shot migration: replace `parents[N]` lib resolution in hooks.

Source hooks under `.claude/hooks/` resolve their sibling `lib/` via
``Path(__file__).resolve().parents[N] / "lib"``, where N is brittle to
the copy depth. After REQ-003-007's hook generator copies a hook to
``src/copilot-cli/hooks/<event>/<name>.py`` (one level deeper), the
existing ``parents[N]`` calculation lands at the wrong directory and
the hook crashes on import.

Fix: rewrite the bootstrap to walk upward looking for the plugin
manifest ``.claude-plugin/plugin.json``. The marker lives at the
plugin root regardless of layout, so the sibling ``lib/`` is always
findable.

This script is idempotent: it detects the new pattern and skips files
that already migrated.

Run once with:
    python3 scripts/migrations/m7t2_rewrite_hook_bootstrap.py

The script exits 0 on success, 1 if any file failed validation, 2 on
configuration error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

OLD_PATTERN = re.compile(
    r"""_plugin_root\s*=\s*os\.environ\.get\("CLAUDE_PLUGIN_ROOT"\)\n"""
    r"""if\s+_plugin_root:\n"""
    r"""\s+_lib_dir\s*=\s*(?:str\(Path\(_plugin_root\)\.resolve\(\)\s*/\s*"lib"\)|os\.path\.join\(_plugin_root,\s*"lib"\))\n"""
    r"""(?:else:\n)?"""
    r"""\s+_lib_dir\s*=\s*str\(Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\s*/\s*"lib"\)\n"""
    r"""(?:if\s+not\s+os\.path\.isdir\(_lib_dir\):\n"""
    r"""\s+print\(f"Plugin lib directory not found: \{_lib_dir\}",\s*file=sys\.stderr\)\n"""
    r"""\s+sys\.exit\([02]\)(?:\s*#[^\n]*)?\n"""
    r"""if\s+_lib_dir\s+not\s+in\s+sys\.path:\n"""
    r"""\s+sys\.path\.insert\(0,\s*_lib_dir\)"""
    r"""|if\s+os\.path\.isdir\(_lib_dir\)\s+and\s+_lib_dir\s+not\s+in\s+sys\.path:\n"""
    r"""\s+sys\.path\.insert\(0,\s*_lib_dir\))""",
    re.MULTILINE,
)

NEW_BOOTSTRAP = '''_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    # Walk up from this hook looking for .claude-plugin/plugin.json
    # (the plugin manifest marker). The sibling lib/ is the plugin's
    # lib dir. Works regardless of source vs install layout depth;
    # robust to the M5 generator copying this file to a different
    # directory level under src/<provider>/hooks/<event>/.
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
    print("Plugin lib directory not found", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)'''

NEW_MARKER = ".claude-plugin"


def migrate_file(path: Path) -> str:
    """Return one of: "migrated", "already-migrated", "skipped-no-pattern", "error"."""
    text = path.read_text(encoding="utf-8")
    if NEW_MARKER in text and "Walk up from this hook" in text:
        return "already-migrated"
    if not OLD_PATTERN.search(text):
        return "skipped-no-pattern"
    new_text = OLD_PATTERN.sub(NEW_BOOTSTRAP, text, count=1)
    if new_text == text:
        return "error"
    path.write_text(new_text, encoding="utf-8")
    return "migrated"


def main() -> int:
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
        if "hook_utilities" not in path.read_text(encoding="utf-8"):
            continue
        outcome = migrate_file(path)
        results[outcome].append(str(path.relative_to(REPO_ROOT)))

    for outcome, files in results.items():
        print(f"{outcome}: {len(files)}")
        for f in files:
            print(f"  {f}")

    return 1 if results["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
