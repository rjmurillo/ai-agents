"""Name the function that owns an argument ruff flagged, for ``check_unused_arguments.py``.

A baseline key carries the owner, as in ``a.py: ARG001 owner in main``. Two
findings with the same argument name in different functions of one file then
get different keys, so two pull requests that each fix one of them delete two
different baseline lines and merge to the right result. A key without the
owner would leave two identical lines, and git merges two deletions of
identical lines into a stale line that fails the gate on the base branch.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache

from scripts.validation.unused_arguments_git import GateConfigError

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


def _argument_nodes(node: _FunctionNode) -> list[ast.arg]:
    spec = node.args
    found = [*spec.posonlyargs, *spec.args, *spec.kwonlyargs]
    if spec.vararg is not None:
        found.append(spec.vararg)
    if spec.kwarg is not None:
        found.append(spec.kwarg)
    return found


@lru_cache(maxsize=64)
def _index(source: str, filename: str) -> dict[tuple[str, int], list[tuple[str, ast.arg]]]:
    """Map ``(argument name, row)`` to the ``(qualified owner, node)`` pairs on that row.

    One walk per file, so a file with many findings is parsed and walked once.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise GateConfigError(f"cannot parse {filename} to name an owner: {exc}") from exc
    found: dict[tuple[str, int], list[tuple[str, ast.arg]]] = {}

    def walk(parent: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, ast.ClassDef):
                walk(child, (*scope, child.name))
            elif isinstance(child, _FunctionNode):
                label = "<lambda>" if isinstance(child, ast.Lambda) else child.name
                inner = (*scope, label)
                for arg in _argument_nodes(child):
                    found.setdefault((arg.arg, arg.lineno), []).append((".".join(inner), arg))
                walk(child, inner)
            else:
                walk(child, scope)

    walk(tree, ())
    return found


def owning_function(source: str, filename: str, row: int, column: int, name: str) -> str:
    """Return the dotted scope of the function whose ``name`` argument ruff flagged.

    ``row`` and ``column`` are ruff's 1-based location of the argument. A
    nested function reads ``outer.inner``, a method ``Class.method``, a lambda
    ``<lambda>``. Raises ``GateConfigError`` when no argument is at that spot,
    so a ruff location the parser cannot match fails the gate instead of
    producing a key that hides the owner.
    """
    found = _index(source, filename).get((name, row), [])
    if len(found) > 1:
        # ast columns are 0-based UTF-8 byte offsets, ruff's are 1-based characters.
        line = _LINE_BREAK.split(source)[row - 1] if row >= 1 else ""
        byte_column = len(line[: max(column - 1, 0)].encode("utf-8"))
        found = [pair for pair in found if pair[1].col_offset == byte_column] or found
    if not found:
        raise GateConfigError(f"no argument `{name}` at {filename}:{row} to name an owner")
    return found[0][0]
