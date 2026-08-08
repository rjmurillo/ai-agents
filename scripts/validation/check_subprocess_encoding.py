#!/usr/bin/env python3
# taste-lint: ignore file-size -- issue #4261 keeps scope-walk and ratchet policy together.
"""Gate: subprocess calls with text-mode UTF-8 must pair errors="replace".

A ``subprocess.run`` (or any ``subprocess.*`` call) that sets both
``encoding="utf-8"`` (case-insensitive, common aliases accepted) and
text-capturing mode (``text=True``, ``capture_output=True``, or decoded
``stdout=PIPE`` / ``stderr=PIPE`` captures) must also pass
``errors="replace"``.

Without ``errors="replace"``, a child process that emits bytes invalid for
UTF-8 raises ``UnicodeDecodeError`` on the calling side. On Windows CI
runners, ``git`` and ``gh`` can emit such bytes in branch names, commit
messages, or file-system paths. The decode fails before the caller can
report the real assertion, hiding the underlying failure. See issue #4261.

Canonical house pattern (in ``scripts/ci/verify_code_env.py``):

    subprocess.run(
        argv,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

What this scanner checks:
    A call is flagged when ALL of these hold:
    1. It reaches a subprocess text-capturing entry point (``subprocess.run``,
       ``subprocess.check_output``, ``subprocess.Popen``,
       ``subprocess.check_call``).
    2. It has a literal ``encoding=`` keyword whose value is a UTF-8 alias
       (``"utf-8"``, ``"utf8"``, ``"UTF-8"``, ``"UTF8"``, ``"utf_8"``).
    3. The call enables text mode: ``text=True`` or ``capture_output=True``
       are present as literal ``True``-valued keywords, or the call captures
       decoded ``stdout=PIPE`` / ``stderr=PIPE`` output, or the entry point
       decodes unconditionally (``check_output``).
    4. No ``errors=`` keyword is present.

Deliberate over-approximation:
    When a call site uses ``**kwargs``, we cannot know whether ``errors`` was
    supplied by the caller. Rather than silently wave it through, we flag the
    site. The author must either add ``errors="replace"`` or restructure to
    avoid the splat. One extra keyword in the rare-but-valid call is worth
    never missing a decode on the common violating call.

Exits (ADR-035):
    0 - No violations found.
    1 - One or more violations detected.
    2 - Configuration error (invalid repository root).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_UTF8_ALIASES: frozenset[str] = frozenset({"utf-8", "utf8", "utf_8", "UTF-8", "UTF8", "UTF_8"})

# subprocess entry points that accept keyword arguments
_TEXT_CAPTURING_CALLS: frozenset[str] = frozenset({"run", "Popen", "check_call"})

# Entry points that unconditionally return decoded text (no text= needed)
_UNCONDITIONAL_DECODE_CALLS: frozenset[str] = frozenset({"check_output", "getoutput"})

_ALL_SUBPROCESS_CALLS: frozenset[str] = _TEXT_CAPTURING_CALLS | _UNCONDITIONAL_DECODE_CALLS

_SKIP_DIRS: frozenset[str] = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for the first keyword matching ``name``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _has_keyword(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _has_splat(call: ast.Call) -> bool:
    """True when the call has a ``**kwargs`` expansion."""
    return any(kw.arg is None for kw in call.keywords)


def _is_true_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value is True


def _is_utf8_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value in _UTF8_ALIASES


@dataclass
class _DeferredCallable:
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    call_states: list[_AliasState]


@dataclass
class _AliasState:
    module_aliases: set[str]
    callable_aliases: dict[str, str]
    pipe_aliases: set[str]
    function_bindings: dict[str, list[_DeferredCallable]]


def _copy_alias_state(state: _AliasState) -> _AliasState:
    return _AliasState(
        set(state.module_aliases),
        dict(state.callable_aliases),
        set(state.pipe_aliases),
        {
            name: list(bindings)
            for name, bindings in state.function_bindings.items()
        },
    )


def _snapshot_alias_state(
    state: _AliasState,
) -> tuple[frozenset[str], dict[str, str], frozenset[str]]:
    return (
        frozenset(state.module_aliases),
        dict(state.callable_aliases),
        frozenset(state.pipe_aliases),
    )


def _parameter_names(args: ast.arguments) -> set[str]:
    names = {
        arg.arg
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]
    }
    if args.vararg is not None:
        names.add(args.vararg.arg)
    if args.kwarg is not None:
        names.add(args.kwarg.arg)
    return names


def _bound_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Starred):
        return _bound_names(node.value)
    if isinstance(node, (ast.List, ast.Tuple)):
        names: list[str] = []
        for element in node.elts:
            names.extend(_bound_names(element))
        return names
    return []


def _resolve_assignment_aliases(
    node: ast.expr,
    state: _AliasState,
) -> tuple[bool, str | None, bool]:
    module_aliases, callable_aliases, pipe_aliases = _snapshot_alias_state(state)
    return (
        _is_subprocess_module_alias(node, module_aliases),
        _subprocess_callable_name(node, module_aliases, callable_aliases),
        _is_pipe_capture_target(node, module_aliases, pipe_aliases),
    )


def _is_subprocess_module_alias(
    node: ast.expr | None,
    module_aliases: frozenset[str],
) -> bool:
    """Return True when *node* resolves to the subprocess module."""
    return isinstance(node, ast.Name) and node.id in module_aliases


def _clear_alias_binding(
    name: str,
    module_aliases: set[str],
    callable_aliases: dict[str, str],
    pipe_aliases: set[str],
    function_bindings: dict[str, list[_DeferredCallable]] | None = None,
) -> None:
    """Remove any alias binding currently attached to *name*."""
    module_aliases.discard(name)
    callable_aliases.pop(name, None)
    pipe_aliases.discard(name)
    if function_bindings is not None:
        function_bindings.pop(name, None)


def _merge_function_bindings(
    states: list[_AliasState],
) -> dict[str, list[_DeferredCallable]]:
    merged: dict[str, list[_DeferredCallable]] = {}
    for state in states:
        for name, bindings in state.function_bindings.items():
            target = merged.setdefault(name, [])
            seen = {id(binding) for binding in target}
            for binding in bindings:
                if id(binding) in seen:
                    continue
                target.append(binding)
                seen.add(id(binding))
    return merged


def _merge_alias_states(states: list[_AliasState]) -> _AliasState:
    merged_callables: dict[str, str] = {}
    for state in states:
        for name, target in state.callable_aliases.items():
            current = merged_callables.get(name)
            if current is None or (
                target in _UNCONDITIONAL_DECODE_CALLS
                and current not in _UNCONDITIONAL_DECODE_CALLS
            ):
                merged_callables[name] = target
    return _AliasState(
        {
            alias
            for state in states
            for alias in state.module_aliases
        },
        merged_callables,
        {
            alias
            for state in states
            for alias in state.pipe_aliases
        },
        _merge_function_bindings(states),
    )


def _is_pipe_capture_target(
    node: ast.expr | None,
    module_aliases: frozenset[str],
    pipe_aliases: frozenset[str],
) -> bool:
    """Return True when *node* resolves to subprocess.PIPE."""
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in pipe_aliases
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in module_aliases
        and node.attr == "PIPE"
    )


def _subprocess_call_name(
    node: ast.Call,
    module_aliases: frozenset[str],
    callable_aliases: dict[str, str],
) -> str | None:
    """Return the canonical subprocess function name, or None."""
    return _subprocess_callable_name(node.func, module_aliases, callable_aliases)


def _subprocess_callable_name(
    node: ast.expr,
    module_aliases: frozenset[str],
    callable_aliases: dict[str, str],
) -> str | None:
    """Return the canonical subprocess callable for *node*, or None."""
    func = node
    # subprocess.run(...)
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in module_aliases
        and func.attr in _ALL_SUBPROCESS_CALLS
    ):
        return func.attr
    # from subprocess import run; run(...)
    if isinstance(func, ast.Name) and func.id in callable_aliases:
        return callable_aliases[func.id]
    return None


def _is_flagged(
    call: ast.Call,
    module_aliases: frozenset[str],
    callable_aliases: dict[str, str],
    pipe_aliases: frozenset[str],
) -> bool:
    """Return True when this call violates the errors="replace" convention.

    A call is flagged when it reaches a subprocess text entry point, pins
    UTF-8 as the codec, captures decoded text, and omits ``errors=``.
    """
    name = _subprocess_call_name(call, module_aliases, callable_aliases)
    if name is None:
        return False

    encoding_node = _keyword_value(call, "encoding")
    if not _is_utf8_literal(encoding_node):
        # No explicit UTF-8 pin: not in scope for this checker.
        return False

    # If errors= is already present, the call is compliant.
    if _has_keyword(call, "errors"):
        return False

    # A **kwargs splat may carry errors=, text=, capture_output=, or PIPE-based
    # captures. We cannot verify any of those statically, so fail closed.
    if _has_splat(call):
        return True

    # Verify text mode is enabled (or the call decodes unconditionally).
    unconditional = name in _UNCONDITIONAL_DECODE_CALLS
    pipe_capture = _is_pipe_capture_target(
        _keyword_value(call, "stdout"), module_aliases, pipe_aliases
    ) or _is_pipe_capture_target(
        _keyword_value(call, "stderr"), module_aliases, pipe_aliases
    )
    text_enabled = (
        _is_true_literal(_keyword_value(call, "text"))
        or _is_true_literal(_keyword_value(call, "universal_newlines"))
        or _is_true_literal(_keyword_value(call, "capture_output"))
        or pipe_capture
    )
    if not unconditional and not text_enabled:
        # Binary mode with an explicit encoding is unusual but not our concern.
        return False

    return True


def _iter_immediate_calls(node: ast.AST) -> list[ast.Call]:
    """Return calls that execute when *node* itself executes."""
    calls: list[ast.Call] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Call):
            calls.append(current)
        if isinstance(
            current,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))
    return calls


def _iter_nested_lambdas(node: ast.AST) -> list[ast.Lambda]:
    lambdas: list[ast.Lambda] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Lambda):
            lambdas.append(current)
            continue
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))
    return lambdas


_SUPPRESSION_COMMENT = "# subprocess-encoding: strict-ok"


def _record_call_violations(
    node: ast.AST,
    state: _AliasState,
    source_lines: list[str],
    violations: list[int],
) -> None:
    module_aliases, callable_aliases, pipe_aliases = _snapshot_alias_state(state)
    for call in _iter_immediate_calls(node):
        lineno = call.lineno
        if lineno < 1 or lineno > len(source_lines):
            continue
        if _SUPPRESSION_COMMENT in source_lines[lineno - 1]:
            continue
        if _is_flagged(call, module_aliases, callable_aliases, pipe_aliases):
            violations.append(lineno)


def _scan_scope(
    statements: list[ast.stmt],
    state: _AliasState,
    source_lines: list[str],
) -> list[int]:
    """Return violations discovered by executing *statements* in order."""
    violations: list[int] = []
    deferred_callables: list[_DeferredCallable] = []
    deferred_lookup: dict[int, _DeferredCallable] = {}

    def _scan_block(block: list[ast.stmt], current_state: _AliasState) -> None:
        def _register_deferred(
            node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        ) -> _DeferredCallable:
            deferred = deferred_lookup.get(id(node))
            if deferred is None:
                deferred = _DeferredCallable(node, [])
                deferred_lookup[id(node)] = deferred
                deferred_callables.append(deferred)
            return deferred

        def _clear(name: str) -> None:
            _clear_alias_binding(
                name,
                current_state.module_aliases,
                current_state.callable_aliases,
                current_state.pipe_aliases,
                current_state.function_bindings,
            )

        def _set_state(next_state: _AliasState) -> None:
            current_state.module_aliases = set(next_state.module_aliases)
            current_state.callable_aliases = dict(next_state.callable_aliases)
            current_state.pipe_aliases = set(next_state.pipe_aliases)
            current_state.function_bindings = {
                name: list(bindings)
                for name, bindings in next_state.function_bindings.items()
            }

        def _record_expr(node: ast.AST | None) -> None:
            if node is None:
                return
            _record_call_violations(node, current_state, source_lines, violations)
            for call in _iter_immediate_calls(node):
                if not isinstance(call.func, ast.Name):
                    continue
                for binding in current_state.function_bindings.get(call.func.id, []):
                    binding.call_states.append(_copy_alias_state(current_state))

        def _bind_name(
            name: str,
            value: ast.expr,
            source_state: _AliasState | None = None,
        ) -> None:
            binding_state = current_state if source_state is None else source_state
            function_bindings = (
                list(binding_state.function_bindings.get(value.id, []))
                if isinstance(value, ast.Name)
                else []
            )
            resolved_module, resolved_callable, resolved_pipe = _resolve_assignment_aliases(
                value,
                binding_state,
            )
            _clear(name)
            if function_bindings:
                current_state.function_bindings[name] = function_bindings
            elif isinstance(value, ast.Lambda):
                current_state.function_bindings[name] = [_register_deferred(value)]
            if resolved_module:
                current_state.module_aliases.add(name)
            elif resolved_callable is not None:
                current_state.callable_aliases[name] = resolved_callable
            elif resolved_pipe:
                current_state.pipe_aliases.add(name)

        def _bind_target(
            target: ast.AST,
            value: ast.expr,
            source_state: _AliasState | None = None,
        ) -> None:
            binding_state = current_state if source_state is None else source_state
            if isinstance(target, ast.Name):
                _bind_name(target.id, value, binding_state)
                return
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(
                value,
                (ast.Tuple, ast.List),
            ):
                snapshot_state = _copy_alias_state(binding_state)
                for target_item, value_item in zip(target.elts, value.elts, strict=False):
                    _bind_target(target_item, value_item, snapshot_state)
                for target_item in target.elts[len(value.elts) :]:
                    for name in _bound_names(target_item):
                        _clear(name)
                return
            for name in _bound_names(target):
                _bind_name(name, value, binding_state)

        for stmt in block:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    bound_name = alias.asname or alias.name
                    _clear(bound_name)
                    if alias.name == "subprocess":
                        current_state.module_aliases.add(bound_name)
                continue

            if isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    if alias.name == "*":
                        if stmt.module == "subprocess":
                            current_state.callable_aliases.update(
                                {name: name for name in _ALL_SUBPROCESS_CALLS}
                            )
                            current_state.pipe_aliases.add("PIPE")
                        continue
                    bound_name = alias.asname or alias.name
                    _clear(bound_name)
                    if stmt.module != "subprocess":
                        continue
                    if alias.name in _ALL_SUBPROCESS_CALLS:
                        current_state.callable_aliases[bound_name] = alias.name
                    elif alias.name == "PIPE":
                        current_state.pipe_aliases.add(bound_name)
                continue

            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in stmt.decorator_list:
                    _record_expr(decorator)
                for default in [*stmt.args.defaults, *stmt.args.kw_defaults]:
                    _record_expr(default)
                _record_expr(stmt.returns)
                _clear(stmt.name)
                current_state.function_bindings[stmt.name] = [_register_deferred(stmt)]
                continue

            if isinstance(stmt, ast.ClassDef):
                for decorator in stmt.decorator_list:
                    _record_expr(decorator)
                for base in stmt.bases:
                    _record_expr(base)
                for keyword in stmt.keywords:
                    _record_expr(keyword.value)
                _clear(stmt.name)
                class_state = _copy_alias_state(current_state)
                _clear_alias_binding(
                    stmt.name,
                    class_state.module_aliases,
                    class_state.callable_aliases,
                    class_state.pipe_aliases,
                    class_state.function_bindings,
                )
                violations.extend(_scan_scope(stmt.body, class_state, source_lines))
                continue

            if isinstance(stmt, ast.Assign):
                _record_expr(stmt.value)
                for target in stmt.targets:
                    _bind_target(target, stmt.value)
                continue

            if isinstance(stmt, ast.AnnAssign):
                _record_expr(stmt.value)
                if stmt.value is not None:
                    _bind_target(stmt.target, stmt.value)
                continue

            if isinstance(stmt, ast.AugAssign):
                _record_expr(stmt.value)
                for name in _bound_names(stmt.target):
                    _clear(name)
                continue

            if isinstance(stmt, ast.Delete):
                for target in stmt.targets:
                    for name in _bound_names(target):
                        _clear(name)
                continue

            if isinstance(stmt, (ast.For, ast.AsyncFor)):
                _record_expr(stmt.iter)
                zero_state = _copy_alias_state(current_state)
                body_state = _copy_alias_state(current_state)
                for name in _bound_names(stmt.target):
                    _clear_alias_binding(
                        name,
                        body_state.module_aliases,
                        body_state.callable_aliases,
                        body_state.pipe_aliases,
                        body_state.function_bindings,
                    )
                _scan_block(stmt.body, body_state)
                after_states = [zero_state, body_state]
                if stmt.orelse:
                    zero_orelse_state = _copy_alias_state(zero_state)
                    body_orelse_state = _copy_alias_state(body_state)
                    _scan_block(stmt.orelse, zero_orelse_state)
                    _scan_block(stmt.orelse, body_orelse_state)
                    after_states.extend([zero_orelse_state, body_orelse_state])
                _set_state(_merge_alias_states(after_states))
                continue

            if isinstance(stmt, ast.While):
                _record_expr(stmt.test)
                zero_state = _copy_alias_state(current_state)
                body_state = _copy_alias_state(current_state)
                _scan_block(stmt.body, body_state)
                after_states = [zero_state, body_state]
                if stmt.orelse:
                    zero_orelse_state = _copy_alias_state(zero_state)
                    body_orelse_state = _copy_alias_state(body_state)
                    _scan_block(stmt.orelse, zero_orelse_state)
                    _scan_block(stmt.orelse, body_orelse_state)
                    after_states.extend([zero_orelse_state, body_orelse_state])
                _set_state(_merge_alias_states(after_states))
                continue

            if isinstance(stmt, ast.If):
                _record_expr(stmt.test)
                then_state = _copy_alias_state(current_state)
                else_state = _copy_alias_state(current_state)
                _scan_block(stmt.body, then_state)
                _scan_block(stmt.orelse, else_state)
                _set_state(_merge_alias_states([then_state, else_state]))
                continue

            if isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    _record_expr(item.context_expr)
                    if item.optional_vars is not None:
                        for name in _bound_names(item.optional_vars):
                            _clear(name)
                _scan_block(stmt.body, current_state)
                continue

            if isinstance(stmt, ast.Try):
                base_state = _copy_alias_state(current_state)
                body_state = _copy_alias_state(current_state)
                _scan_block(stmt.body, body_state)
                branch_states = [base_state, body_state]
                for handler in stmt.handlers:
                    _record_expr(handler.type)
                    handler_state = _copy_alias_state(current_state)
                    if handler.name is not None:
                        _clear_alias_binding(
                            handler.name,
                            handler_state.module_aliases,
                            handler_state.callable_aliases,
                            handler_state.pipe_aliases,
                            handler_state.function_bindings,
                        )
                    _scan_block(handler.body, handler_state)
                    branch_states.append(handler_state)
                if stmt.orelse:
                    orelse_state = _copy_alias_state(body_state)
                    _scan_block(stmt.orelse, orelse_state)
                    branch_states.append(orelse_state)
                merged_state = _merge_alias_states(branch_states)
                if stmt.finalbody:
                    final_state = _copy_alias_state(merged_state)
                    _scan_block(stmt.finalbody, final_state)
                    merged_state = final_state
                _set_state(merged_state)
                continue

            if isinstance(stmt, ast.Match):
                _record_expr(stmt.subject)
                case_states = [_copy_alias_state(current_state)]
                for case in stmt.cases:
                    case_state = _copy_alias_state(current_state)
                    if case.guard is not None:
                        _record_expr(case.guard)
                    _scan_block(case.body, case_state)
                    case_states.append(case_state)
                _set_state(_merge_alias_states(case_states))
                continue

            if isinstance(stmt, ast.Assert):
                _record_expr(stmt.test)
                _record_expr(stmt.msg)
                continue

            if isinstance(stmt, ast.Raise):
                _record_expr(stmt.exc)
                _record_expr(stmt.cause)
                continue

            if isinstance(stmt, ast.Return):
                _record_expr(stmt.value)
                continue

            if isinstance(stmt, ast.Expr):
                _record_expr(stmt.value)
                continue

    _scan_block(statements, state)

    for deferred in deferred_callables:
        if isinstance(deferred.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_state = _copy_alias_state(state)
            _clear_alias_binding(
                deferred.node.name,
                fn_state.module_aliases,
                fn_state.callable_aliases,
                fn_state.pipe_aliases,
                fn_state.function_bindings,
            )
            for name in _parameter_names(deferred.node.args):
                _clear_alias_binding(
                    name,
                    fn_state.module_aliases,
                    fn_state.callable_aliases,
                    fn_state.pipe_aliases,
                    fn_state.function_bindings,
                )
            violations.extend(_scan_scope(deferred.node.body, fn_state, source_lines))
            for call_state in deferred.call_states:
                direct_call_state = _copy_alias_state(call_state)
                _clear_alias_binding(
                    deferred.node.name,
                    direct_call_state.module_aliases,
                    direct_call_state.callable_aliases,
                    direct_call_state.pipe_aliases,
                    direct_call_state.function_bindings,
                )
                for name in _parameter_names(deferred.node.args):
                    _clear_alias_binding(
                        name,
                        direct_call_state.module_aliases,
                        direct_call_state.callable_aliases,
                        direct_call_state.pipe_aliases,
                        direct_call_state.function_bindings,
                    )
                violations.extend(
                    _scan_scope(deferred.node.body, direct_call_state, source_lines)
                )
            continue

        lambda_state = _copy_alias_state(state)
        for name in _parameter_names(deferred.node.args):
            _clear_alias_binding(
                name,
                lambda_state.module_aliases,
                lambda_state.callable_aliases,
                lambda_state.pipe_aliases,
                lambda_state.function_bindings,
            )
        _record_call_violations(
            deferred.node.body,
            lambda_state,
            source_lines,
            violations,
        )
        for call_state in deferred.call_states:
            direct_call_state = _copy_alias_state(call_state)
            for name in _parameter_names(deferred.node.args):
                _clear_alias_binding(
                    name,
                    direct_call_state.module_aliases,
                    direct_call_state.callable_aliases,
                    direct_call_state.pipe_aliases,
                    direct_call_state.function_bindings,
                )
            _record_call_violations(
                deferred.node.body,
                direct_call_state,
                source_lines,
                violations,
            )

    return violations


def find_violations(source: str, filename: str = "<string>") -> list[int]:
    """Return line numbers of flagged calls in *source*.

    A call on a line that ends with ``# subprocess-encoding: strict-ok`` is
    suppressed. Use this only when strict decoding is intentional and
    documented (for example, when the stream is guaranteed valid UTF-8 and a
    decode failure should propagate as an error rather than silently produce
    replacement characters).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    if not isinstance(tree, ast.Module):
        return []

    return sorted(
        set(
            _scan_scope(
                tree.body,
                _AliasState({"subprocess"}, {}, set(), {}),
                source_lines,
            )
        )
    )


def _is_scannable_source(repo_root: Path, path: Path) -> bool:
    """Return True when ``path`` is a safe Python file inside ``repo_root``."""
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return (
        path.is_file()
        and path.suffix == ".py"
        and not any(part in _SKIP_DIRS for part in relative.parts)
    )


def _collect_sources(repo_root: Path, explicit_paths: list[Path] | None = None) -> list[Path]:
    """Return Python sources to scan."""
    if explicit_paths is not None:
        return sorted(path for path in explicit_paths if _is_scannable_source(repo_root, path))

    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "scripts/*.py", "scripts/**/*.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
        if completed.returncode == 0:
            rels = [line for line in completed.stdout.splitlines() if line.strip()]
            return [repo_root / r for r in rels if _is_scannable_source(repo_root, repo_root / r)]
    except (OSError, subprocess.SubprocessError):
        pass
    # Fallback: walk the tree
    found: list[Path] = []
    for path in (repo_root / "scripts").rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        found.append(path)
    return sorted(found)


def find_all_violations(
    repo_root: Path, explicit_paths: list[Path] | None = None
) -> list[tuple[Path, int]]:
    """Return ``(path, lineno)`` pairs for every flagged call site."""
    results: list[tuple[Path, int]] = []
    for path in _collect_sources(repo_root, explicit_paths):
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno in find_violations(source, str(path)):
            results.append((path, lineno))
    return results


def validate_subprocess_encoding(
    repo_root: Path, explicit_paths: list[Path] | None = None
) -> bool:
    """Return True when no violation is found.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used
    by ``pre_pr_sequence.py``.
    """
    violations = find_all_violations(repo_root, explicit_paths)
    if not violations:
        return True
    count = len(violations)
    print(
        f"[FAIL] {count} subprocess call(s) pin UTF-8 encoding without errors=\"replace\":",
        file=sys.stderr,
    )
    for path, lineno in violations:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{lineno}", file=sys.stderr)
    print(
        "\nFix: add errors=\"replace\" to each flagged call.",
        file=sys.stderr,
    )
    print(
        "Reason: a child process on Windows can emit bytes invalid for UTF-8.",
        file=sys.stderr,
    )
    print(
        "Without errors=\"replace\", the decode raises before the caller can report "
        "the real failure.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[2]
    explicit_paths: list[Path] | None = None
    if len(args) == 1:
        single_arg = Path(args[0]).resolve()
        if single_arg.is_dir():
            repo_root = single_arg
        elif single_arg.suffix == ".py":
            explicit_paths = [single_arg]
        else:
            repo_root = single_arg
    elif args:
        explicit_paths = [Path(arg) if Path(arg).is_absolute() else repo_root / arg for arg in args]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_subprocess_encoding(repo_root, explicit_paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
