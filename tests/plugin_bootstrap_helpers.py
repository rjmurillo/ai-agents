"""AST delegation checks shared by plugin bootstrap contract tests."""

from __future__ import annotations

import ast
from pathlib import Path

_BOOTSTRAP_MODULE = "_bootstrap"
_BOOTSTRAP_FUNC = "ensure_plugin_paths"


def delegates_to_shared_bootstrap(content: str) -> bool:
    """Check if the file delegates plugin-path resolution to ``_bootstrap``.

    Uses AST analysis (not substring matching) so a docstring or comment
    that happens to contain the import or call text cannot grant the
    exemption. A file qualifies only when its parsed AST contains:

    1. ``from _bootstrap import ... ensure_plugin_paths ...`` AND
    2. an actual call to ``ensure_plugin_paths()`` (bare name) or
       ``_bootstrap.ensure_plugin_paths()`` (attribute form).

    A SyntaxError or any AST traversal failure conservatively denies
    the exemption: a file the test cannot parse has not proven
    delegation, so it must satisfy the inline-pattern checks instead.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    has_import = False
    has_call = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _BOOTSTRAP_MODULE:
            for alias in node.names:
                if alias.name == _BOOTSTRAP_FUNC:
                    has_import = True
                    break
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == _BOOTSTRAP_FUNC:
                has_call = True
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == _BOOTSTRAP_FUNC
                and isinstance(func.value, ast.Name)
                and func.value.id == _BOOTSTRAP_MODULE
            ):
                has_call = True
        if has_import and has_call:
            return True
    return False


def skill_resolution_source(script_path: Path) -> str:
    """Inspect an actual shared skill bootstrap without dropping its consumer."""
    content = script_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content
    imports: set[str] = set()
    calls: set[str] = set()
    for node in tree.body:
        match node:
            case ast.ImportFrom(module="skill_bootstrap", names=names):
                imports.update(
                    alias.asname or alias.name
                    for alias in names
                    if alias.name == "ensure_plugin_paths"
                )
            case ast.Expr(
                value=ast.Call(func=ast.Name(id=name), args=[ast.Name(id="__file__"), *_])
            ):
                calls.add(name)
    helper = script_path.parent.parent / "skill_bootstrap.py"
    if imports & calls and helper.is_file():
        return content + "\n" + helper.read_text(encoding="utf-8")
    return content
