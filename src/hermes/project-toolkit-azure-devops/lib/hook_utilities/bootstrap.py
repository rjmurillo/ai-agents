"""Bootstrap helpers for plugin hooks and skill scripts.

This module provides setup_hook_lib_path() which locates the plugin's lib
directory and adds it to sys.path. Designed to be called with __file__ to
bootstrap hook imports.

DO NOT use setup_hook_lib_path() to replace the ADR-047 inline bootstrap.
Only `council.py` and `sol_loop.py` may replace it with load_skill_paths().
Other hooks and skill scripts keep the
inline `os.environ.get("CLAUDE_PLUGIN_ROOT")` + `os.path.isdir(_lib_dir)`
literals (this module also reads `COPILOT_PLUGIN_ROOT`, which the Copilot CLI
exports): `tests/test_plugin_path_resolution.py` grep-asserts them, and the
only exemption it grants is delegation to `_bootstrap.ensure_plugin_paths`
(the generated-tree helper, ADR-068), NOT this function. Migrating those
hooks here removes the literals and fails the ADR-047 test.
See ADR-047 (Path Resolution) for the sanctioned
inline pattern and issue #2898 for the history.

The setup_hook_lib_path function handles:
- Checking the COPILOT_PLUGIN_ROOT, then CLAUDE_PLUGIN_ROOT, environment variable
- Walking up directory tree to find .claude-plugin/plugin.json marker
- Adding the lib directory to sys.path
- Exiting with specified code if lib not found

The resolve_plugin_lib_dir function is also available for cases where you
need the lib path without auto-setup.

ADR-047 documents load_skill_paths() for llm-council and sol-loop.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from pathlib import Path
from types import ModuleType


def _resolve_skill_paths_lib(own_lib: Path) -> Path:
    """Find the first lib with paths.py in the two harness roots and own root."""
    roots = (os.environ.get("COPILOT_PLUGIN_ROOT"), os.environ.get("CLAUDE_PLUGIN_ROOT"))
    candidates = [Path(root) / "lib" for root in roots if root]
    candidates.append(own_lib)
    for lib_dir in candidates:
        if (lib_dir / "paths.py").is_file():
            return lib_dir.resolve()
    raise RuntimeError(f"paths.py not found in any of: {', '.join(map(str, candidates))}")


def load_skill_paths(own_lib: Path, script: str) -> ModuleType:
    """Load the selected paths file, then enable resolved sibling skill imports."""
    paths_file = _resolve_skill_paths_lib(own_lib) / "paths.py"
    spec = importlib.util.spec_from_file_location("_skill_paths", paths_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load skill paths from {paths_file}")
    paths = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paths)
    script_dir = str(Path(script).resolve().parent)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    return paths


def _plugin_root_from_env() -> str | None:
    """Return the plugin root a harness exported, Copilot first.

    Same order as the nested form the rule prescribes for commands,
    ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}``, and as the
    skill scripts' ``os.environ.get("COPILOT_PLUGIN_ROOT") or
    os.environ.get("CLAUDE_PLUGIN_ROOT")``. Empty values fall through.
    """
    copilot_root = os.environ.get("COPILOT_PLUGIN_ROOT")
    return copilot_root or os.environ.get("CLAUDE_PLUGIN_ROOT")


def resolve_plugin_lib_dir(hook_file: str | Path | None = None) -> str | None:
    """Resolve the plugin lib directory for hook imports.

    Checks the COPILOT_PLUGIN_ROOT, then CLAUDE_PLUGIN_ROOT, environment
    variable first, then walks up from the hook file location looking for
    .claude-plugin/plugin.json (the plugin manifest marker). The sibling lib/ is
    the plugin's lib dir.

    Args:
        hook_file: Path to the hook file (__file__). If None, uses the
            calling module's __file__ via stack inspection.

    Returns:
        Absolute path to the lib directory as a string, or None if not found.
    """
    plugin_root = _plugin_root_from_env()
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
        plugin_root = _plugin_root_from_env()
        print(
            f"Plugin lib directory not found: {lib_dir} (plugin root env={plugin_root!r})",
            file=sys.stderr,
        )
        sys.exit(fail_exit_code)
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    return lib_dir
