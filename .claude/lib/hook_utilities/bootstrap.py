"""Canonical: scripts/hook_utilities/bootstrap.py. Sync via scripts/sync_plugin_lib.py.

This module provides setup_hook_lib_path() which locates the plugin's lib
directory and adds it to sys.path. Designed to be called with __file__ to
bootstrap hook imports.

DO NOT use this helper to replace the inline bootstrap in `.claude/hooks/`
hooks or in skill scripts governed by ADR-047. Those files MUST keep the
inline `os.environ.get("CLAUDE_PLUGIN_ROOT")` + `os.path.isdir(_lib_dir)`
literals: `tests/test_plugin_path_resolution.py` grep-asserts them, and the
only exemption it grants is delegation to `_bootstrap.ensure_plugin_paths`
(the generated-tree helper, ADR-068), NOT this function. Migrating those
hooks here removes the literals and fails the ADR-047 test.
`scripts/migrations/req003_inline_plugin_root_bootstrap.py` exists precisely
to revert such a migration. See ADR-047 (Path Resolution) for the sanctioned
inline pattern and issue #2898 for the history.

The setup_hook_lib_path function handles:
- Checking CLAUDE_PLUGIN_ROOT environment variable
- Walking up directory tree to find .claude-plugin/plugin.json marker
- Adding the lib directory to sys.path
- Exiting with specified code if lib not found

The resolve_plugin_lib_dir function is also available for cases where you
need the lib path without auto-setup.
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path


def resolve_plugin_lib_dir(hook_file: str | Path | None = None) -> str | None:
    """Resolve the plugin lib directory for hook imports.

    Checks CLAUDE_PLUGIN_ROOT environment variable first, then walks up
    from the hook file location looking for .claude-plugin/plugin.json
    (the plugin manifest marker). The sibling lib/ is the plugin's lib dir.

    Args:
        hook_file: Path to the hook file (__file__). If None, uses the
            calling module's __file__ via stack inspection.

    Returns:
        Absolute path to the lib directory as a string, or None if not found.
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return str(Path(plugin_root).resolve() / "lib")

    if hook_file is None:
        frame = inspect.currentframe()
        if frame is not None and frame.f_back is not None:
            hook_file = frame.f_back.f_globals.get("__file__")
        if hook_file is None:
            return None

    cur = Path(hook_file).resolve().parent
    while True:
        if (cur / ".claude-plugin" / "plugin.json").is_file():
            return str(cur / "lib")
        if cur.parent == cur:
            break
        cur = cur.parent

    return None


def setup_hook_lib_path(hook_file: str | Path, fail_exit_code: int = 2) -> str:
    """Resolve and add plugin lib directory to sys.path.

    This is the main bootstrap function for hook scripts. It finds the lib
    directory, validates it exists, and adds it to sys.path.

    Args:
        hook_file: Path to the hook file (pass __file__).
        fail_exit_code: Exit code to use if lib not found. Use 2 for blocking
            hooks, 0 for non-blocking hooks.

    Returns:
        The lib directory path (for reference).

    Exits:
        Calls sys.exit(fail_exit_code) if lib directory not found.
    """
    lib_dir = resolve_plugin_lib_dir(hook_file)
    if lib_dir is None or not os.path.isdir(lib_dir):
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        print(
            f"Plugin lib directory not found: {lib_dir} "
            f"(CLAUDE_PLUGIN_ROOT={plugin_root!r})",
            file=sys.stderr,
        )
        sys.exit(fail_exit_code)
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    return lib_dir
