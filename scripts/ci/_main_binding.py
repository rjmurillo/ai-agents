"""Module-scope main-binding analysis for CLI exit-contract coverage.

Determines whether a test file locally defines ``main`` at module scope,
which suppresses the sole-fallback credit path.  Walks module-level
statements in source order, descending into control-flow blocks that
execute at import time (if/try/with/for/match).  Stops at function and
class bodies (new scope) except that the definition name itself is
a module-level binding.

Recognised binding forms (every form that introduces a name in Python):
function/class def, assignment, annotated/augmented assignment,
destructuring, import/from-import (including ``as``), named expression,
for/with/except/match targets, and ``del`` (which kills an imported name).

Re-export assignments (``main = _mod.main``) and direct from-imports
(``from X import main``) are excluded because the bound value IS the
module's real ``main`` and sole credit remains valid.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Sequence

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def has_local_main_definition(tree: ast.Module) -> bool:
    """True when ``main`` is locally bound at module scope.

    Uses conservative branch join: if ANY branch of a control-flow node binds
    ``main``, the result after the node is "locally bound".
    """

    def _scans_main(stmts: Iterable[ast.stmt]) -> bool:
        for node in stmts:
            if _stmt_binds_main(node):
                return True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # new scope -- do not descend
            for child_block in _control_flow_bodies(node):
                if _scans_main(child_block):
                    return True
        return False

    return _scans_main(tree.body)


# ---------------------------------------------------------------------------
# Binding helpers -- split for complexity
# ---------------------------------------------------------------------------


def _target_binds_name(node: ast.expr, name: str) -> bool:
    """True if an assignment-target expression binds *name*.

    Handles ``ast.Name``, tuple/list unpacking, and starred targets.
    """
    if isinstance(node, ast.Name):
        return node.id == name
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_target_binds_name(elt, name) for elt in node.elts)
    if isinstance(node, ast.Starred):
        return _target_binds_name(node.value, name)
    return False


def _stmt_binds_main(node: ast.stmt) -> bool:
    """True when *node* itself binds ``main`` at its scope level.

    Delegates to specialised helpers to stay under the complexity ceiling.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == "main"
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        if _assignment_binds_main(node):
            return True
        # Fall through to walrus check on the value expression.
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return _import_binds_main(node)
    if isinstance(node, ast.Delete):
        return any(isinstance(t, ast.Name) and t.id == "main" for t in node.targets)
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return _target_binds_name(node.target, "main")
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return _with_binds_main(node)
    if isinstance(node, ast.ExceptHandler):
        return node.name == "main"
    # Named expression can appear inside any expression-statement.
    return _has_walrus_main(node)


def _assignment_binds_main(node: ast.stmt) -> bool:
    """True when an Assign/AnnAssign/AugAssign locally defines ``main``.

    Re-export assignments (``main = _mod.main``) are excluded because the
    bound value IS the module's real ``main`` and sole credit remains valid.
    """
    if isinstance(node, ast.Assign):
        if not any(_target_binds_name(t, "main") for t in node.targets):
            return False
        return not _is_main_reexport(node.value)
    if isinstance(node, ast.AugAssign):
        return _target_binds_name(node.target, "main")
    # AnnAssign -- only if there is a value (bare annotation is not a binding)
    if node.value is not None and _target_binds_name(node.target, "main"):
        return not _is_main_reexport(node.value)
    return False


def _is_main_reexport(value: ast.expr) -> bool:
    """True when the value is ``X.main`` -- a re-export of a module's main."""
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "main"
        and isinstance(value.value, ast.Name)
    )


def _import_binds_main(node: ast.stmt) -> bool:
    """True when an import/from-import locally defines ``main``.

    ``from X import main`` (no alias) binds ``main`` to the module's real
    ``main`` and is NOT a local definition.  ``from X import Y as main`` or
    ``import X as main`` ARE local definitions because main is aliased to
    something else.
    """
    if isinstance(node, ast.ImportFrom):
        return any(
            alias.asname == "main" and alias.name != "main"
            for alias in node.names
        )
    # import X as main -- always a local binding
    return any(
        alias.asname == "main"
        for alias in node.names
    )


def _with_binds_main(node: ast.stmt) -> bool:
    """True when a with/async-with ``as`` clause binds ``main``."""
    return any(
        item.optional_vars is not None
        and _target_binds_name(item.optional_vars, "main")
        for item in node.items
    )


def _has_walrus_main(node: ast.stmt) -> bool:
    """True if any expression in *node* contains ``(main := ...)``."""
    for child in ast.walk(node):
        if isinstance(child, ast.NamedExpr):
            if isinstance(child.target, ast.Name) and child.target.id == "main":
                return True
    return False


def _control_flow_bodies(
    node: ast.stmt,
) -> Iterator[Sequence[ast.stmt]]:
    """Yield statement lists from control-flow nodes that execute at module level."""
    if isinstance(node, ast.If):
        yield node.body
        yield node.orelse
    elif isinstance(node, (ast.Try, ast.TryStar)):
        yield node.body
        # Yield handlers as a statement list so _stmt_binds_main sees
        # ExceptHandler nodes (which can bind main via ``except E as main``).
        yield list(node.handlers)
        for handler in node.handlers:
            yield handler.body
        yield node.orelse
        yield node.finalbody
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        yield node.body
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        yield node.body
        yield node.orelse
    elif hasattr(ast, "Match") and isinstance(node, ast.Match):
        for case in node.cases:
            yield case.body
