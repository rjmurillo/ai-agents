"""Resolve GitHub skill libraries without depending on a caller's directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

Discovery = Literal["relative", "ancestors", "manifest"]
WorkspaceFallback = tuple[str, str]


def _relative_lib_dir(script_file: str) -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(script_file), "..", "..", "..", "..", "lib")
    )


def _ancestor_lib_dir(script_file: str) -> str:
    ancestor = os.path.abspath(os.path.dirname(script_file))
    while True:
        candidate = os.path.join(ancestor, "lib", "github_core")
        if os.path.isdir(candidate):
            return os.path.dirname(candidate)
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            return ""
        ancestor = parent


def _manifest_lib_dir(script_file: str) -> str:
    for parent in Path(script_file).resolve().parents:
        if (parent / ".claude-plugin" / "plugin.json").is_file():
            return str(parent / "lib")
    return _relative_lib_dir(script_file)


_DISCOVERERS = {
    "relative": _relative_lib_dir,
    "ancestors": _ancestor_lib_dir,
    "manifest": _manifest_lib_dir,
}


def ensure_plugin_paths(
    script_file: str,
    workspace: WorkspaceFallback | None = None,
    *,
    discovery: Discovery = "relative",
) -> None:
    """Apply caller-selected workspace path components only when opted in."""
    _plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    _workspace_root = os.environ.get("GITHUB_WORKSPACE") if workspace else None
    if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
        _lib_dir = os.path.join(_plugin_root, "lib")
    elif workspace and _workspace_root:
        _lib_dir = os.path.join(_workspace_root, *workspace)
    else:
        _lib_dir = _DISCOVERERS[discovery](script_file)
    if not os.path.isdir(_lib_dir):
        print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
        sys.exit(2)
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)
