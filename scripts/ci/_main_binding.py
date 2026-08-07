"""Per-call-site module-scope main-binding state for CLI exit-contract coverage.

Tracks the binding state of ``main`` through module-level execution order,
evaluating at MODULE END (runtime semantics: global name resolution happens at
call time, after the module finishes executing).

Also detects function-local ``main`` bindings (parameters, local assignments,
imports, for/with/except/match targets, walrus) which shadow the global at
compile time and deny credit regardless of module state.

State model:
- UNBOUND: main has never been bound; sole-fallback logic applies separately
- TARGET(stems): main resolves to known script stems via import or re-export
- LOCAL: main is bound to something unrelated (deny credit)
- UNKNOWN: ambiguous due to wildcard, conditional, or deletion (deny credit)

Conservative branch join: only credit when ALL reachable states agree.
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
        return self.stems if self.kind == _Kind.TARGET else frozenset()

    @property
    def is_unbound(self) -> bool:
        return self.kind == _Kind.UNBOUND


def _join(a: MainState, b: MainState) -> MainState:
    """Conservative join: credit only when ALL paths agree."""
    if a == b:
        return a
    if a.kind == _Kind.UNBOUND and b.kind == _Kind.UNBOUND:
        return MainState.unbound()
    if _Kind.UNKNOWN in (a.kind, b.kind) or _Kind.LOCAL in (a.kind, b.kind):
        return MainState.unknown()
    if a.kind == _Kind.TARGET and b.kind == _Kind.TARGET:
        shared = a.stems & b.stems
        return MainState.target(shared) if shared else MainState.unknown()
    return MainState.unknown()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Ctx:
    stems: frozenset[str]
    aliases: dict[str, str]
    referenced: set[str]
    alias_established: set[str] = field(default_factory=set)


def compute_bare_credit(
    tree: ast.Module,
    stems: frozenset[str],
    aliases: dict[str, str],
    referenced: set[str],
) -> dict[int, frozenset[str]]:
    """Map function/class definition lineno -> stems bare main() should credit.

    Python resolves global names at CALL TIME.  All test functions see the
    module-end state of ``main``.  Functions with a local ``main`` binding
    shadow the global and get empty credit.
    """
    ctx = _Ctx(stems=stems, aliases=dict(aliases), referenced=referenced)
    end_state = _walk_module(tree.body, MainState.unbound(), ctx)
    module_credit = _credit_at(end_state, ctx)

    result: dict[int, frozenset[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "main":
                continue
            credit = frozenset() if _function_has_local_main(node) else module_credit
            result[node.lineno] = credit
        elif isinstance(node, ast.ClassDef) and node.name != "main":
            result[node.lineno] = module_credit
    return result


def _credit_at(state: MainState, ctx: _Ctx) -> frozenset[str]:
    if state.kind == _Kind.TARGET:
        return state.stems
    if state.kind == _Kind.UNBOUND and len(ctx.referenced) == 1:
        return frozenset(ctx.referenced)
    return frozenset()


# ---------------------------------------------------------------------------
# Function-local main detection
# ---------------------------------------------------------------------------


def _function_has_local_main(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if ``main`` is bound locally (compile-time local shadow)."""
    if _params_bind_main(func.args):
        return True
    return _stmts_bind_main(func.body)


def _params_bind_main(args: ast.arguments) -> bool:
    all_args = args.args + args.posonlyargs + args.kwonlyargs
    if any(a.arg == "main" for a in all_args):
        return True
    if args.vararg and args.vararg.arg == "main":
        return True
    return bool(args.kwarg and args.kwarg.arg == "main")


def _stmts_bind_main(stmts: Sequence[ast.stmt]) -> bool:
    """Check if main is bound (not descending into nested scopes)."""
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if _stmt_binds_main_locally(node) or _has_walrus_main(node):
            return True
        for body in _child_bodies(node):
            if _stmts_bind_main(body):
                return True
    return False


def _stmt_binds_main_locally(node: ast.stmt) -> bool:
    """True if this single statement directly binds main (no recursion)."""
    if isinstance(node, ast.Assign):
        return any(_target_binds_name(t, "main") for t in node.targets)
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return _target_binds_name(node.target, "main")
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any((a.asname or a.name) == "main" for a in node.names)
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return _target_binds_name(node.target, "main")
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return any(
            i.optional_vars and _target_binds_name(i.optional_vars, "main")
            for i in node.items
        )
    if isinstance(node, ast.Delete):
        return any(isinstance(t, ast.Name) and t.id == "main" for t in node.targets)
    if hasattr(ast, "Match") and isinstance(node, ast.Match):
        return any(_pattern_binds_main(c.pattern) for c in node.cases)
    return _is_try(node) and any(h.name == "main" for h in node.handlers)


def _child_bodies(node: ast.stmt) -> list[Sequence[ast.stmt]]:
    """Return sub-statement bodies to recurse into (excluding nested scopes)."""
    if isinstance(node, ast.If):
        return [node.body, node.orelse]
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        return [node.body, node.orelse]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [node.body]
    if _is_try(node):
        bodies: list[Sequence[ast.stmt]] = [node.body, node.orelse, node.finalbody]
        bodies.extend(h.body for h in node.handlers)
        return bodies
    if hasattr(ast, "Match") and isinstance(node, ast.Match):
        return [c.body for c in node.cases]
    return []


def _pattern_binds_main(pattern: ast.AST) -> bool:
    """Check if a match pattern captures ``main``."""
    if hasattr(ast, "MatchAs") and isinstance(pattern, ast.MatchAs):
        if pattern.name == "main":
            return True
        return bool(pattern.pattern and _pattern_binds_main(pattern.pattern))
    if hasattr(ast, "MatchStar") and isinstance(pattern, ast.MatchStar):
        return pattern.name == "main" if pattern.name else False
    if hasattr(ast, "MatchMapping") and isinstance(pattern, ast.MatchMapping):
        if pattern.rest == "main":
            return True
    # Recurse into composite patterns
    children = getattr(pattern, "patterns", [])
    if not children:
        children = getattr(pattern, "kwd_patterns", [])
    return any(_pattern_binds_main(p) for p in children)


# ---------------------------------------------------------------------------
# Module-level state walk
# ---------------------------------------------------------------------------


def _walk_module(
    stmts: Sequence[ast.stmt], state: MainState, ctx: _Ctx
) -> MainState:
    """Walk module statements in source order, compute end state."""
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "main":
                state = MainState.local()
            continue
        if isinstance(node, ast.ClassDef):
            if node.name == "main":
                state = MainState.local()
            continue
        _update_aliases(node, ctx)
        new = _stmt_effect(node, state, ctx)
        if new is not None:
            state = new
        else:
            state = _control_flow(node, state, ctx)
    return state


def _update_aliases(node: ast.stmt, ctx: _Ctx) -> None:
    """Track alias establishment and invalidation in source order."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            eff = alias.asname or alias.name
            if eff in ctx.aliases:
                ctx.alias_established.add(eff)
        return
    for name in _stmt_assigned_names(node):
        if name == "main" or name not in ctx.aliases:
            continue
        if name not in ctx.alias_established:
            ctx.alias_established.add(name)
        else:
            ctx.aliases.pop(name)


def _stmt_assigned_names(node: ast.stmt) -> list[str]:
    """Names assigned by this statement (top-level targets only)."""
    if isinstance(node, ast.Assign):
        result: list[str] = []
        for t in node.targets:
            result.extend(_assigned_names(t))
        return result
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return _assigned_names(node.target)
    if isinstance(node, ast.Delete):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    return []


def _assigned_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: list[str] = []
        for elt in target.elts:
            out.extend(_assigned_names(elt))
        return out
    if isinstance(target, ast.Starred):
        return _assigned_names(target.value)
    return []


# ---------------------------------------------------------------------------
# Statement effects on main state
# ---------------------------------------------------------------------------


def _stmt_effect(node: ast.stmt, state: MainState, ctx: _Ctx) -> MainState | None:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return _assign_effect(node, ctx)
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return _import_effect(node, ctx)
    if isinstance(node, ast.Delete):
        if any(isinstance(t, ast.Name) and t.id == "main" for t in node.targets):
            return MainState.unknown()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name == "main":
            return MainState.local()
    if _has_walrus_main(node):
        return MainState.local()
    return None


def _assign_effect(node: ast.stmt, ctx: _Ctx) -> MainState | None:
    if isinstance(node, ast.Assign):
        if not any(_target_binds_name(t, "main") for t in node.targets):
            return MainState.local() if _has_walrus_main(node) else None
        return _resolve_value(node.value, ctx)
    if isinstance(node, ast.AugAssign):
        return MainState.local() if _target_binds_name(node.target, "main") else None
    # AnnAssign
    if node.value is not None and _target_binds_name(node.target, "main"):
        return _resolve_value(node.value, ctx)
    return MainState.local() if _has_walrus_main(node) else None


def _resolve_value(value: ast.expr, ctx: _Ctx) -> MainState:
    if (
        isinstance(value, ast.Attribute)
        and value.attr == "main"
        and isinstance(value.value, ast.Name)
    ):
        stem = ctx.aliases.get(value.value.id)
        if stem is not None and stem in ctx.stems:
            return MainState.target(frozenset({stem}))
    return MainState.local()


def _import_effect(node: ast.stmt, ctx: _Ctx) -> MainState | None:
    if isinstance(node, ast.ImportFrom):
        if any(a.name == "*" for a in node.names):
            return MainState.unknown()
        for alias in node.names:
            eff = alias.asname or alias.name
            if eff != "main":
                continue
            if alias.name == "main" and alias.asname is None:
                module = node.module or ""
                stem = module.rsplit(".", 1)[-1]
                if stem in ctx.stems:
                    return MainState.target(frozenset({stem}))
            return MainState.local()
        return None
    for alias in node.names:
        if (alias.asname or alias.name) == "main":
            return MainState.local()
    return None


# ---------------------------------------------------------------------------
# Control flow with conservative joins
# ---------------------------------------------------------------------------


def _control_flow(node: ast.stmt, state: MainState, ctx: _Ctx) -> MainState:
    branches = list(_branch_bodies(node))
    if not branches:
        return state

    entry = _loop_entry(node, state)
    exit_states = [_walk_module(body, e, ctx) for body, e in _iter_branches(branches, state, entry)]

    if isinstance(node, ast.If) and not node.orelse:
        exit_states.append(state)
    if isinstance(node, (ast.While, ast.For, ast.AsyncFor)) and not node.orelse:
        exit_states.append(state)

    joined = exit_states[0] if exit_states else state
    for s in exit_states[1:]:
        joined = _join(joined, s)

    if _is_try(node) and node.finalbody:
        joined = _walk_module(node.finalbody, joined, ctx)
    return joined


def _loop_entry(node: ast.stmt, state: MainState) -> MainState:
    if isinstance(node, (ast.For, ast.AsyncFor)):
        if _target_binds_name(node.target, "main"):
            return MainState.local()
    if isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if item.optional_vars and _target_binds_name(item.optional_vars, "main"):
                return MainState.local()
    return state


def _iter_branches(
    branches: list[tuple[Sequence[ast.stmt], str]],
    state: MainState,
    loop_entry: MainState,
) -> Iterator[tuple[Sequence[ast.stmt], MainState]]:
    for body, kind in branches:
        if kind == "loop":
            yield body, loop_entry
        elif kind == "except_main":
            yield body, MainState.local()
        elif kind == "match":
            yield body, MainState.unknown()
        else:
            yield body, state


def _branch_bodies(node: ast.stmt) -> list[tuple[Sequence[ast.stmt], str]]:
    if isinstance(node, ast.If):
        return _if_branches(node)
    if isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
        return _loop_branches(node)
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [(node.body, "loop")]
    if _is_try(node):
        return _try_branches(node)
    if hasattr(ast, "Match") and isinstance(node, ast.Match):
        return [(c.body, "match") for c in node.cases]
    return []


def _if_branches(node: ast.If) -> list[tuple[Sequence[ast.stmt], str]]:
    result: list[tuple[Sequence[ast.stmt], str]] = [(node.body, "normal")]
    if node.orelse:
        result.append((node.orelse, "normal"))
    return result


def _loop_branches(node: ast.stmt) -> list[tuple[Sequence[ast.stmt], str]]:
    result: list[tuple[Sequence[ast.stmt], str]] = [(node.body, "loop")]
    if node.orelse:
        result.append((node.orelse, "normal"))
    return result


def _try_branches(node: ast.stmt) -> list[tuple[Sequence[ast.stmt], str]]:
    result: list[tuple[Sequence[ast.stmt], str]] = [(node.body, "normal")]
    for h in node.handlers:
        result.append((h.body, "except_main" if h.name == "main" else "normal"))
    if node.orelse:
        result.append((node.orelse, "normal"))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_try(node: ast.stmt) -> bool:
    if isinstance(node, ast.Try):
        return True
    return hasattr(ast, "TryStar") and isinstance(node, ast.TryStar)


def _target_binds_name(node: ast.expr, name: str) -> bool:
    if isinstance(node, ast.Name):
        return node.id == name
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_target_binds_name(elt, name) for elt in node.elts)
    if isinstance(node, ast.Starred):
        return _target_binds_name(node.value, name)
    return False


def _has_walrus_main(node: ast.stmt) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.NamedExpr):
            if isinstance(child.target, ast.Name) and child.target.id == "main":
                return True
    return False
