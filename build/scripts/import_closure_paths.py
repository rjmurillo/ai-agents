"""Directories a shipped module puts on ``sys.path`` itself (issue #7221).

``import_closure.py`` resolves an import against these directories. Only the
explicit top-level bootstrap idiom counts:
``sys.path.insert(0, os.path.dirname(...(os.path.abspath(__file__))))``, or
``sys.path.append`` of the same chain. Each ``dirname`` walks one level up.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _is_os_path(call: ast.Call, names: frozenset[str]) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in names
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "path"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )


def _dirname_depth(node: ast.AST) -> int | None:
    """N for ``os.path.dirname`` applied N times to ``os.path.abspath(__file__)``."""
    depth = 0
    current = node
    while isinstance(current, ast.Call) and len(current.args) == 1 and not current.keywords:
        if _is_os_path(current, frozenset({"abspath"})):
            arg = current.args[0]
            return depth if isinstance(arg, ast.Name) and arg.id == "__file__" else None
        if not _is_os_path(current, frozenset({"dirname"})):
            return None
        depth += 1
        current = current.args[0]
    return None


def _bootstrap_arg(node: ast.expr) -> ast.expr | None:
    match node:
        case ast.Call(
            func=ast.Attribute(
                value=ast.Attribute(value=ast.Name(id="sys"), attr="path"), attr=method
            ),
            args=args,
            keywords=[],
        ):
            match method, args:
                case "append", [arg]:
                    return arg
                case "insert", [ast.Constant(value=0), arg]:
                    return arg
    return None


def sys_path_inserts(tree: Path, path: Path, parsed: ast.Module) -> list[tuple[int, Path]]:
    """Return ``(statement index, directory)`` for modeled top-level path inserts.

    Only the explicit idiom ``sys.path.insert(0, os.path.dirname(...`` chain
    over ``os.path.abspath(__file__)`` (or ``sys.path.append`` of it) is
    modeled. Anything else keeps its imports unresolved.
    """
    inserts: list[tuple[int, Path]] = []
    for index, stmt in enumerate(parsed.body):
        arg = _bootstrap_arg(stmt.value) if isinstance(stmt, ast.Expr) else None
        depth = _dirname_depth(arg) if arg is not None else None
        if not depth:
            continue
        directory = path.parent
        for _ in range(depth - 1):
            directory = directory.parent
        if directory.is_relative_to(tree):
            inserts.append((index, directory))
    return inserts
