"""Per-call-site module-scope main-binding state for CLI exit-contract coverage.

Tracks the binding state of ``main`` through module-level execution order and
records, at each test function/class definition point, what stems a bare
``main()`` call should credit.

State model:
- UNBOUND: main has never been bound; sole-fallback logic applies separately
- TARGET(stems): main resolves to known script stems via import or re-export
- LOCAL: main is bound to something unrelated (deny credit)
- UNKNOWN: ambiguous due to wildcard, conditional, or deletion (deny credit)

Conservative branch join: only credit when ALL reachable states agree on the
same target stems.  If any path produces a different state, the join is UNKNOWN.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# State types
# ---------------------------------------------------------------------------


class _Kind(Enum):
    UNBOUND = "unbound"
    TARGET = "target"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MainState:
    """Binding state of ``main`` at a program point."""

    kind: _Kind
    stems: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def unbound(cls) -> MainState:
        return cls(_Kind.UNBOUND)

    @classmethod
    def target(cls, stems: frozenset[str]) -> MainState:
        return cls(_Kind.TARGET, stems) if stems else cls(_Kind.LOCAL)

    @classmethod
    def local(cls) -> MainState:
        return cls(_Kind.LOCAL)

    @classmethod
    def unknown(cls) -> MainState:
        return cls(_Kind.UNKNOWN)

    @property
    def credits(self) -> frozenset[str]:
        """Stems bare main() should credit (empty = deny)."""
        return self.stems if self.kind == _Kind.TARGET else frozenset()

    @property
    def is_unbound(self) -> bool:
        return self.kind == _Kind.UNBOUND


def _join(a: MainState, b: MainState) -> MainState:
    """Conservative join: credit only when ALL paths agree."""
    if a == b:
        return a
    # Both unbound = unbound; one unbound one not = unknown
    if a.kind == _Kind.UNBOUND and b.kind == _Kind.UNBOUND:
        return MainState.unbound()
    if _Kind.UNKNOWN in (a.kind, b.kind):
        return MainState.unknown()
    if _Kind.LOCAL in (a.kind, b.kind):
        return MainState.unknown()
    # Both TARGET but different stems
    if a.kind == _Kind.TARGET and b.kind == _Kind.TARGET:
        shared = a.stems & b.stems
        return MainState.target(shared) if shared else MainState.unknown()
    # Mismatch (TARGET + UNBOUND, etc.)
    return MainState.unknown()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_bare_credit(
    tree: ast.Module,
    stems: frozenset[str],
    aliases: dict[str, str],
    referenced: set[str],
) -> dict[int, frozenset[str]]:
    """Map function/class definition lineno -> stems bare main() should credit.

    For UNBOUND state at a function definition, the sole-fallback applies:
    credit the sole referenced stem if exactly one stem is referenced.
    For TARGET state, credit the target stems directly.
    For LOCAL/UNKNOWN, no credit (empty set).
    """
    ctx = _Ctx(stems=stems, aliases=aliases, referenced=referenced)
    state = MainState.unbound()
    result: dict[int, frozenset[str]] = {}

    state = _walk_stmts(tree.body, state, ctx, result)
    return result


# ---------------------------------------------------------------------------
# Walk context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Ctx:
    stems: frozenset[str]
    aliases: dict[str, str]
    referenced: set[str]


# ---------------------------------------------------------------------------
# Statement walker -- source-ordered
# ---------------------------------------------------------------------------


def _walk_stmts(
    stmts: Sequence[ast.stmt],
    state: MainState,
    ctx: _Ctx,
    result: dict[int, frozenset[str]],
) -> MainState:
    """Walk statements in source order, updating state and recording at funcs."""
    for node in stmts:
        # Record state at function/class definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "main":
                # def main is a local binding, not a test function
                state = MainState.local()
                continue
            result[node.lineno] = _credit_at(state, ctx)
            continue  # don't descend into function body
        if isinstance(node, ast.ClassDef):
            if node.name != "main":
                credit = _credit_at(state, ctx)
                result[node.lineno] = credit
                # Record same credit for all methods within the class
                for item in ast.walk(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        result[item.lineno] = credit
                continue
            # class main: is a local binding
            state = MainState.local()
            continue

        # Update state based on this statement
        new_state = _stmt_effect(node, state, ctx)
        if new_state is not None:
            state = new_state
            continue

        # Control flow: descend with conservative joins
        state = _control_flow(node, state, ctx, result)
    return state


def _credit_at(state: MainState, ctx: _Ctx) -> frozenset[str]:
    """Compute credit stems at a definition point."""
    if state.kind == _Kind.TARGET:
        return state.stems
    if state.kind == _Kind.UNBOUND and len(ctx.referenced) == 1:
        return frozenset(ctx.referenced)
    return frozenset()


# ---------------------------------------------------------------------------
# Statement effect -- returns new state or None if not a binding statement
# ---------------------------------------------------------------------------


def _stmt_effect(
    node: ast.stmt, state: MainState, ctx: _Ctx
) -> MainState | None:
    """Return new state if this statement binds main, else None."""
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return _assign_effect(node, ctx)
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return _import_effect(node, ctx)
    if isinstance(node, ast.Delete):
        if any(isinstance(t, ast.Name) and t.id == "main" for t in node.targets):
            return MainState.unknown()
        return None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # Already handled above for test functions; here for nested definitions
        if node.name == "main":
            return MainState.local()
        return None
    # Walrus in expression statement
    if _has_walrus_main(node):
        return MainState.local()
    return None


def _assign_effect(node: ast.stmt, ctx: _Ctx) -> MainState | None:
    """Assignment/augmented/annotated effect on main."""
    if isinstance(node, ast.Assign):
        if not any(_target_binds_name(t, "main") for t in node.targets):
            # Check walrus in value
            if _has_walrus_main(node):
                return MainState.local()
            return None
        return _resolve_value(node.value, ctx)
    if isinstance(node, ast.AugAssign):
        if _target_binds_name(node.target, "main"):
            return MainState.local()
        return None
    # AnnAssign
    if node.value is not None and _target_binds_name(node.target, "main"):
        return _resolve_value(node.value, ctx)
    if _has_walrus_main(node):
        return MainState.local()
    return None


def _resolve_value(value: ast.expr, ctx: _Ctx) -> MainState:
    """Determine if an assignment value resolves to a target stem's main."""
    # Re-export: main = X.main where X is in aliases
    if (
        isinstance(value, ast.Attribute)
        and value.attr == "main"
        and isinstance(value.value, ast.Name)
    ):
        stem = ctx.aliases.get(value.value.id)
        if stem is not None and stem in ctx.stems:
            return MainState.target(frozenset({stem}))
    # Any other value = local
    return MainState.local()


def _import_effect(node: ast.stmt, ctx: _Ctx) -> MainState | None:
    """Import/from-import effect on main."""
    if isinstance(node, ast.ImportFrom):
        # Wildcard import: unknown
        if any(alias.name == "*" for alias in node.names):
            return MainState.unknown()
        for alias in node.names:
            effective_name = alias.asname if alias.asname else alias.name
            if effective_name != "main":
                continue
            # from X import main (or alias): resolve module
            if alias.name == "main" and alias.asname is None:
                # Direct from-import: check if module is a known stem
                module = node.module or ""
                stem = module.rsplit(".", 1)[-1]
                if stem in ctx.stems:
                    return MainState.target(frozenset({stem}))
            # from X import Y as main: local
            return MainState.local()
        return None
    # import X as main
    for alias in node.names:
        effective_name = alias.asname if alias.asname else alias.name
        if effective_name == "main":
            return MainState.local()
    return None


# ---------------------------------------------------------------------------
# Control flow -- conservative join
# ---------------------------------------------------------------------------


def _control_flow(
    node: ast.stmt,
    state: MainState,
    ctx: _Ctx,
    result: dict[int, frozenset[str]],
) -> MainState:
    """Handle control-flow nodes with conservative branch joins."""
    branches = list(_branch_bodies(node))
    if not branches:
        return state

    # For/while: target binds main before body executes
    loop_state = state
    if isinstance(node, (ast.For, ast.AsyncFor)):
        if _target_binds_name(node.target, "main"):
            loop_state = MainState.local()
    if isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if item.optional_vars and _target_binds_name(item.optional_vars, "main"):
                loop_state = MainState.local()
                break

    # Walk each branch, collect exit states
    exit_states: list[MainState] = []
    for body, entry in branches:
        if entry == "loop":
            entry_state = loop_state
        elif entry == "except_main":
            entry_state = MainState.local()
        elif entry == "match":
            # Match patterns can capture names; conservatively treat as unknown
            entry_state = MainState.unknown()
        else:
            entry_state = state
        exit_s = _walk_stmts(body, entry_state, ctx, result)
        exit_states.append(exit_s)

    # For if without else, the else branch is the incoming state
    if isinstance(node, ast.If) and not node.orelse:
        exit_states.append(state)
    # For while without else AND zero-iteration possibility
    if isinstance(node, (ast.While, ast.AsyncFor, ast.For)):
        if not node.orelse:
            exit_states.append(state)  # zero iterations

    # Join all exit states
    if not exit_states:
        joined = state
    else:
        joined = exit_states[0]
        for s in exit_states[1:]:
            joined = _join(joined, s)

    # Finally block is a continuation, not a branch
    if isinstance(node, (ast.Try, ast.TryStar)) and node.finalbody:
        joined = _walk_stmts(node.finalbody, joined, ctx, result)

    return joined


def _branch_bodies(
    node: ast.stmt,
) -> Iterator[tuple[Sequence[ast.stmt], str]]:
    """Yield (body, entry_kind) for control-flow branches."""
    if isinstance(node, ast.If):
        yield node.body, "normal"
        if node.orelse:
            yield node.orelse, "normal"
    elif isinstance(node, (ast.While,)):
        yield node.body, "loop"
        if node.orelse:
            yield node.orelse, "normal"
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        yield node.body, "loop"
        if node.orelse:
            yield node.orelse, "normal"
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        yield node.body, "loop"
    elif isinstance(node, (ast.Try, ast.TryStar)):
        yield node.body, "normal"
        for handler in node.handlers:
            # ExceptHandler name binding
            body = handler.body
            if handler.name == "main":
                yield body, "except_main"
            else:
                yield body, "normal"
        if node.orelse:
            yield node.orelse, "normal"
        # finalbody handled as continuation in _control_flow, not a branch
    elif hasattr(ast, "Match") and isinstance(node, ast.Match):
        for case in node.cases:
            yield case.body, "match"


# ---------------------------------------------------------------------------
# Target helpers
# ---------------------------------------------------------------------------


def _target_binds_name(node: ast.expr, name: str) -> bool:
    """True if an assignment-target expression binds *name*."""
    if isinstance(node, ast.Name):
        return node.id == name
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_target_binds_name(elt, name) for elt in node.elts)
    if isinstance(node, ast.Starred):
        return _target_binds_name(node.value, name)
    return False


def _has_walrus_main(node: ast.stmt) -> bool:
    """True if any expression in *node* contains ``(main := ...)``."""
    for child in ast.walk(node):
        if isinstance(child, ast.NamedExpr):
            if isinstance(child.target, ast.Name) and child.target.id == "main":
                return True
    return False


# Legacy compatibility shim -- removed; callers use compute_bare_credit.
def has_local_main_definition(tree: ast.Module) -> bool:
    raise NotImplementedError("Use compute_bare_credit instead")
