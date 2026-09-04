#!/usr/bin/env python3
# taste-lint: ignore file-size, flow-sensitive gate keeps one binding and control-flow model.
# taste-lint: ignore complexity, visitor branches mirror Python syntax with explicit state joins.
"""Require ``errors="replace"`` for UTF-8 subprocess text capture.

The scanner tracks subprocess imports and aliases through lexical scopes.
It flags literal UTF-8 calls that decode through text mode, capture flags,
PIPE streams, or unconditional decode entry points without replacement
error handling. Unknown ``**kwargs`` remain fail-closed. See issue #4261.

Canonical pattern:
``subprocess.run(argv, text=True, encoding="utf-8", errors="replace")``.
Exits follow ADR-035: 0 clean, 1 violations, 2 configuration error.
"""

from __future__ import annotations

import ast
import codecs
import os
import stat
import subprocess
import sys
from pathlib import Path

# subprocess entry points that accept keyword arguments
_TEXT_CAPTURING_CALLS: frozenset[str] = frozenset({"run", "Popen", "check_call"})

# Entry points that unconditionally return decoded text (no text= needed)
_UNCONDITIONAL_DECODE_CALLS: frozenset[str] = frozenset(
    {"check_output", "getoutput", "getstatusoutput"}
)

_ALL_SUBPROCESS_CALLS: frozenset[str] = _TEXT_CAPTURING_CALLS | _UNCONDITIONAL_DECODE_CALLS

_Binding = tuple[bool, frozenset[str], bool]
_BindingState = tuple[
    set[str],
    dict[str, frozenset[str]],
    set[str],
    dict[str, tuple[ast.expr, ...]],
]
_CONTEXTLIB_MODULE = "__contextlib_module__"
_CONTEXTLIB_NULLCONTEXT = "__contextlib_nullcontext__"


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for the first keyword matching ``name``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true_literal(node: ast.expr | None) -> bool:
    if node is None:
        return False
    return isinstance(node, ast.Constant) and node.value is True


def _is_utf8_literal(node: ast.expr | None) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    try:
        return codecs.lookup(node.value).name == "utf-8"
    except LookupError:
        return False


def _is_subprocess_pipe(
    node: ast.expr | None,
    module_aliases: set[str],
    pipe_aliases: set[str],
) -> bool:
    """Return whether *node* resolves to ``subprocess.PIPE``."""
    module_pipe = (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in module_aliases
        and node.attr == "PIPE"
    )
    imported_pipe = isinstance(node, ast.Name) and node.id in pipe_aliases
    return module_pipe or imported_pipe


def _subprocess_call_names(
    node: ast.Call,
    module_aliases: set[str],
    callable_aliases: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Return possible function names for a ``subprocess.*`` call."""
    func = node.func
    # subprocess.run(...) or an imported module alias such as sp.run(...)
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in module_aliases
        and func.attr in _ALL_SUBPROCESS_CALLS
    ):
        return frozenset({func.attr})
    # from subprocess import run; run(...), imported aliases, or direct rebinding.
    if isinstance(func, ast.Name):
        return callable_aliases.get(func.id, frozenset())
    return frozenset()


def _target_names(target: ast.expr) -> set[str]:
    """Return every name bound by an assignment target."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return {name for element in target.elts for name in _target_names(element)}
    return set()


def _target_value_pairs(
    target: ast.expr,
    assigned: ast.expr | None,
) -> list[tuple[str, ast.expr | None]]:
    """Pair target names with statically corresponding assigned values."""
    if isinstance(target, ast.Name):
        return [(target.id, assigned)]
    if isinstance(target, ast.Starred):
        return _target_value_pairs(target.value, assigned)
    if not isinstance(target, (ast.Tuple, ast.List)):
        return []
    if not isinstance(assigned, (ast.Tuple, ast.List)):
        return [(name, None) for name in _target_names(target)]

    stars = [index for index, element in enumerate(target.elts) if isinstance(element, ast.Starred)]
    if not stars:
        if len(target.elts) != len(assigned.elts):
            return [(name, None) for name in _target_names(target)]
        return [
            pair
            for target_item, value_item in zip(target.elts, assigned.elts, strict=True)
            for pair in _target_value_pairs(target_item, value_item)
        ]

    star_index = stars[0]
    trailing = len(target.elts) - star_index - 1
    if len(stars) != 1 or len(assigned.elts) < star_index + trailing:
        return [(name, None) for name in _target_names(target)]

    pairs = [
        pair
        for target_item, value_item in zip(
            target.elts[:star_index],
            assigned.elts[:star_index],
            strict=True,
        )
        for pair in _target_value_pairs(target_item, value_item)
    ]
    starred_values = assigned.elts[star_index : len(assigned.elts) - trailing or None]
    pairs.extend(
        _target_value_pairs(
            target.elts[star_index],
            ast.List(elts=starred_values, ctx=ast.Load()),
        )
    )
    if trailing:
        pairs.extend(
            pair
            for target_item, value_item in zip(
                target.elts[-trailing:],
                assigned.elts[-trailing:],
                strict=True,
            )
            for pair in _target_value_pairs(target_item, value_item)
        )
    return pairs


def _assignment_pairs(node: ast.AST) -> list[tuple[str, ast.expr | None]]:
    """Return target names paired with statically corresponding values."""
    if isinstance(node, ast.Assign):
        targets = node.targets
        value = node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets = [node.target]
        value = node.value
    else:
        return []

    return [pair for target in targets for pair in _target_value_pairs(target, value)]


def _resolve_value_binding(
    value: ast.expr | None,
    module_aliases: set[str],
    callable_aliases: dict[str, frozenset[str]],
    pipe_aliases: set[str],
) -> _Binding:
    """Resolve possible subprocess bindings for an expression."""
    if value is None:
        return False, frozenset(), False
    if isinstance(value, ast.IfExp):
        body = _resolve_value_binding(
            value.body,
            module_aliases,
            callable_aliases,
            pipe_aliases,
        )
        orelse = _resolve_value_binding(
            value.orelse,
            module_aliases,
            callable_aliases,
            pipe_aliases,
        )
        return (
            body[0] or orelse[0],
            body[1] | orelse[1],
            body[2] or orelse[2],
        )
    if (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id in module_aliases
    ):
        if value.attr in _ALL_SUBPROCESS_CALLS:
            return False, frozenset({value.attr}), False
        if value.attr == "PIPE":
            return False, frozenset(), True
    if isinstance(value, ast.Name):
        return (
            value.id in module_aliases,
            callable_aliases.get(value.id, frozenset()),
            value.id in pipe_aliases,
        )
    return False, frozenset(), False


def _is_flagged(
    call: ast.Call,
    module_aliases: set[str],
    callable_aliases: dict[str, frozenset[str]],
    pipe_aliases: set[str],
) -> bool:
    """Return True when this call violates the errors="replace" convention.

    A call is flagged when it reaches a subprocess text entry point, pins
    UTF-8 as the codec, enables text mode, and omits ``errors=``.
    """
    names = _subprocess_call_names(call, module_aliases, callable_aliases)
    if not names:
        return False

    encoding_node = _keyword_value(call, "encoding")
    errors_node = _keyword_value(call, "errors")
    has_keyword_splat = any(keyword.arg is None for keyword in call.keywords)
    replacement_is_explicit = (
        isinstance(errors_node, ast.Constant) and errors_node.value == "replace"
    )
    if not _is_utf8_literal(encoding_node):
        if encoding_node is None and has_keyword_splat and not replacement_is_explicit:
            return True
        # No explicit UTF-8 pin: not in scope for this checker.
        return False

    # Verify text mode is enabled (or the call decodes unconditionally).
    unconditional = not names.isdisjoint(_UNCONDITIONAL_DECODE_CALLS)
    text_enabled = (
        _is_true_literal(_keyword_value(call, "text"))
        or _is_true_literal(_keyword_value(call, "capture_output"))
        or _is_subprocess_pipe(_keyword_value(call, "stdout"), module_aliases, pipe_aliases)
        or _is_subprocess_pipe(_keyword_value(call, "stderr"), module_aliases, pipe_aliases)
    )
    if not unconditional and not text_enabled:
        if has_keyword_splat and not replacement_is_explicit:
            return True
        # Binary mode with an explicit encoding is unusual but not our concern.
        return False

    # Only replacement decoding satisfies the convention. Strict decoding must
    # use the line-scoped suppression marker when failure is intentional.
    if isinstance(errors_node, ast.Constant) and errors_node.value == "replace":
        return False

    # A **kwargs splat may carry errors= but we cannot verify; flag conservatively.
    # This is the deliberate over-approximation described in the module docstring.
    return True


class _SubprocessCallVisitor(ast.NodeVisitor):
    """Find violations while tracking bindings in statement and scope order."""

    def __init__(self) -> None:
        self.module_aliases: set[str] = set()
        self.callable_aliases: dict[str, frozenset[str]] = {}
        self.pipe_aliases: set[str] = set()
        self.known_values: dict[str, tuple[ast.expr, ...]] = {}
        self.flagged_lines: list[int] = []
        self._enclosing_summaries: list[tuple[set[str], dict[str, _Binding]]] = []
        self._active_module_state: _BindingState | None = None
        self._flow_terminated = False
        self._loop_break_states: list[list[_BindingState]] = []
        self._loop_continue_states: list[list[_BindingState]] = []
        self._return_states: list[list[_BindingState]] = []
        self._exception_boundary_states: list[list[_BindingState]] = []
        self._active_module_names: set[str] | None = None

    def _clear(self, name: str) -> None:
        self.module_aliases.discard(name)
        self.callable_aliases.pop(name, None)
        self.pipe_aliases.discard(name)
        self.known_values.pop(name, None)

    def _known_value_options(self, value: ast.expr | None) -> tuple[ast.expr, ...]:
        if isinstance(value, (ast.Constant, ast.List, ast.Tuple, ast.Set)):
            return (value,)
        if isinstance(value, ast.Name):
            return self.known_values.get(value.id, ())
        if isinstance(value, ast.IfExp):
            return self._known_value_options(value.body) + self._known_value_options(value.orelse)
        return ()

    def _constant_truth(self, value: ast.expr) -> bool | None:
        if isinstance(value, ast.Constant):
            return bool(value.value)
        if isinstance(value, ast.Name):
            options = self.known_values.get(value.id, ())
            constant_options = [option for option in options if isinstance(option, ast.Constant)]
            truths = {bool(option.value) for option in constant_options}
            if len(truths) == 1 and len(constant_options) == len(options):
                return truths.pop()
        return None

    def _bind(self, name: str, resolved: _Binding, value: ast.expr | None = None) -> None:
        self._clear(name)
        module, callables, pipe = resolved
        if module:
            self.module_aliases.add(name)
        if callables:
            self.callable_aliases[name] = callables
        if pipe:
            self.pipe_aliases.add(name)
        known = self._known_value_options(value)
        if known:
            self.known_values[name] = known

    def _snapshot(self) -> _BindingState:
        return (
            self.module_aliases.copy(),
            self.callable_aliases.copy(),
            self.pipe_aliases.copy(),
            self.known_values.copy(),
        )

    def _restore(self, state: _BindingState) -> None:
        modules, callables, pipes, known_values = state
        self.module_aliases = modules.copy()
        self.callable_aliases = callables.copy()
        self.pipe_aliases = pipes.copy()
        self.known_values = known_values.copy()

    @staticmethod
    def _merge_states(*states: _BindingState) -> _BindingState:
        modules: set[str] = set()
        callables: dict[str, frozenset[str]] = {}
        pipes: set[str] = set()
        common_known_names = (
            set.intersection(*(set(state[3]) for state in states)) if states else set()
        )
        known_values: dict[str, list[ast.expr]] = {name: [] for name in common_known_names}
        for state_modules, state_callables, state_pipes, state_known_values in states:
            modules.update(state_modules)
            pipes.update(state_pipes)
            for name, possible_calls in state_callables.items():
                callables[name] = callables.get(name, frozenset()) | possible_calls
            for name in common_known_names:
                destination = known_values[name]
                options = state_known_values[name]
                existing = {ast.dump(option) for option in destination}
                destination.extend(option for option in options if ast.dump(option) not in existing)
        return (
            modules,
            callables,
            pipes,
            {name: tuple(options) for name, options in known_values.items()},
        )

    def _visit_statements(self, body: list[ast.stmt]) -> None:
        for statement in body:
            if self._flow_terminated:
                break
            if self._exception_boundary_states and self._statement_may_raise(statement):
                self._exception_boundary_states[-1].append(self._snapshot())
            self.visit(statement)

    def _record_exception_boundary(self, state: _BindingState) -> None:
        if self._exception_boundary_states:
            self._exception_boundary_states[-1].append(state)

    def _run_branch_flow(
        self,
        body: list[ast.stmt],
        incoming: _BindingState,
    ) -> tuple[_BindingState, bool]:
        outer_terminated = self._flow_terminated
        self._restore(incoming)
        self._flow_terminated = False
        self._visit_statements(body)
        state = self._snapshot()
        terminated = self._flow_terminated
        self._flow_terminated = outer_terminated
        return state, terminated

    def _run_branch(self, body: list[ast.stmt], incoming: _BindingState) -> _BindingState:
        return self._run_branch_flow(body, incoming)[0]

    def _run_branch_flow_with_boundaries(
        self,
        body: list[ast.stmt],
        incoming: _BindingState,
    ) -> tuple[_BindingState, bool, list[_BindingState]]:
        """Run a branch and retain states where a statement may raise."""
        outer_terminated = self._flow_terminated
        self._restore(incoming)
        self._flow_terminated = False
        self._exception_boundary_states.append([])
        self._visit_statements(body)
        boundaries = self._exception_boundary_states.pop()
        state = self._snapshot()
        terminated = self._flow_terminated
        self._flow_terminated = outer_terminated
        return state, terminated, boundaries

    def _statement_may_raise(self, statement: ast.stmt) -> bool:
        """Return whether a statement can transfer control to an exception path."""

        def safe_target(target: ast.expr) -> bool:
            if isinstance(target, ast.Name):
                return True
            if isinstance(target, ast.Starred):
                return safe_target(target.value)
            if isinstance(target, (ast.Tuple, ast.List)):
                return all(safe_target(element) for element in target.elts)
            return False

        def safe_value(value: ast.expr) -> bool:
            if isinstance(value, ast.Constant):
                return True
            if isinstance(value, ast.Name):
                return (
                    value.id == "len"
                    or value.id in self.module_aliases
                    or value.id in self.callable_aliases
                    or value.id in self.pipe_aliases
                )
            if isinstance(value, ast.Attribute):
                return safe_value(value.value)
            if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                return all(safe_value(element) for element in value.elts)
            return False

        if isinstance(statement, ast.Assign):
            return not (
                all(safe_target(target) for target in statement.targets)
                and safe_value(statement.value)
            )
        if isinstance(statement, ast.Return):
            value = statement.value
            while isinstance(value, ast.NamedExpr):
                value = value.value
            return value is not None and not isinstance(
                value,
                (ast.Constant, ast.Name),
            )
        if isinstance(statement, ast.Try | ast.TryStar):
            # Nested try statements propagate their transformed escaping states
            # explicitly from _visit_try after handlers and finally execute.
            return False
        if isinstance(statement, ast.With | ast.AsyncWith):
            # Context-entry boundaries are recorded item by item in _visit_with.
            return False
        if isinstance(statement, ast.Pass | ast.Global | ast.Nonlocal):
            return False
        return True

    @staticmethod
    def _state_key(state: _BindingState) -> tuple[object, ...]:
        modules, callables, pipes, known_values = state
        return (
            frozenset(modules),
            frozenset(callables.items()),
            frozenset(pipes),
            frozenset(
                (name, frozenset(ast.dump(option) for option in options))
                for name, options in known_values.items()
            ),
        )

    def _bind_target_value(self, target: ast.expr, value: ast.expr | None) -> None:
        for name, assigned in _target_value_pairs(target, value):
            resolved = _resolve_value_binding(
                assigned,
                self.module_aliases,
                self.callable_aliases,
                self.pipe_aliases,
            )
            self._bind(name, resolved, assigned)

    def _iteration_state(
        self,
        target: ast.expr,
        iterable: ast.expr,
        incoming: _BindingState,
    ) -> tuple[_BindingState, bool]:
        """Return possible target bindings and whether an iteration may not run."""
        iterable_options = (
            self.known_values.get(iterable.id, ())
            if isinstance(iterable, ast.Name)
            else (iterable,)
        )
        static_iterables = [
            option
            for option in iterable_options
            if isinstance(option, (ast.List, ast.Tuple, ast.Set))
        ]
        if static_iterables and len(static_iterables) == len(iterable_options):
            elements = [element for option in static_iterables for element in option.elts]
            may_skip = any(not option.elts for option in static_iterables)
            if not elements:
                self._restore(incoming)
                for name in _target_names(target):
                    self._clear(name)
                return self._snapshot(), True
            states: list[_BindingState] = []
            for element in elements:
                self._restore(incoming)
                self._bind_target_value(target, element)
                states.append(self._snapshot())
            return self._merge_states(*states), may_skip

        self._restore(incoming)
        for name in _target_names(target):
            self._clear(name)
        return self._snapshot(), True

    def _static_iteration_elements(self, iterable: ast.expr) -> list[ast.expr] | None:
        options = (
            self.known_values.get(iterable.id, ())
            if isinstance(iterable, ast.Name)
            else (iterable,)
        )
        static = [
            option for option in options if isinstance(option, (ast.List, ast.Tuple, ast.Set))
        ]
        if len(options) != 1 or len(static) != 1:
            return None
        return [element for option in static for element in option.elts]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".", maxsplit=1)[0]
            resolved: _Binding = (
                (True, frozenset(), False)
                if alias.name == "subprocess"
                else (False, frozenset(), False)
            )
            self._bind(bound, resolved)
            if alias.name == "contextlib":
                self.known_values[bound] = (ast.Constant(value=_CONTEXTLIB_MODULE),)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name
            resolved: _Binding = False, frozenset(), False
            if node.module == "subprocess":
                if alias.name in _ALL_SUBPROCESS_CALLS:
                    resolved = False, frozenset({alias.name}), False
                elif alias.name == "PIPE":
                    resolved = False, frozenset(), True
            self._bind(bound, resolved)
            if node.module == "contextlib" and alias.name == "nullcontext":
                self.known_values[bound] = (ast.Constant(value=_CONTEXTLIB_NULLCONTEXT),)

    def _visit_assignment(self, node: ast.AST, value: ast.expr) -> None:
        self.visit(value)
        resolved = [
            (
                name,
                assigned,
                _resolve_value_binding(
                    assigned,
                    self.module_aliases,
                    self.callable_aliases,
                    self.pipe_aliases,
                ),
            )
            for name, assigned in _assignment_pairs(node)
        ]
        for name, assigned, binding in resolved:
            self._bind(name, binding, assigned)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._visit_assignment(node, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._visit_assignment(node, node.value)
        elif isinstance(node.target, ast.Name):
            self._clear(node.target.id)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._clear(node.target.id)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            resolved = _resolve_value_binding(
                node.value,
                self.module_aliases,
                self.callable_aliases,
                self.pipe_aliases,
            )
            self._bind(node.target.id, resolved, node.value)
            self._record_exception_boundary(self._snapshot())

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            for name in _target_names(target):
                self._clear(name)

    def visit_If(self, node: ast.If) -> None:
        """Join aliases from every reachable branch."""
        self.visit(node.test)
        incoming = self._snapshot()
        constant_truth = self._constant_truth(node.test)
        if constant_truth is not None:
            selected = node.body if constant_truth else node.orelse
            state, terminated = self._run_branch_flow(selected, incoming)
            self._restore(state)
            self._flow_terminated = terminated
            return
        body_state, body_terminated = self._run_branch_flow(node.body, incoming)
        orelse_state, orelse_terminated = self._run_branch_flow(node.orelse, incoming)
        normal_states = [
            state
            for state, terminated in (
                (body_state, body_terminated),
                (orelse_state, orelse_terminated),
            )
            if not terminated
        ]
        self._restore(
            self._merge_states(*normal_states)
            if normal_states
            else self._merge_states(body_state, orelse_state)
        )
        self._flow_terminated = not normal_states

    def visit_Break(self, node: ast.Break) -> None:
        if self._loop_break_states:
            self._loop_break_states[-1].append(self._snapshot())
        self._flow_terminated = True

    def visit_Continue(self, node: ast.Continue) -> None:
        if self._loop_continue_states:
            self._loop_continue_states[-1].append(self._snapshot())
        self._flow_terminated = True

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            self.visit(node.value)
        if self._return_states:
            self._return_states[-1].append(self._snapshot())
        self._flow_terminated = True

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is not None:
            self.visit(node.exc)
        if node.cause is not None:
            self.visit(node.cause)
        self._record_exception_boundary(self._snapshot())
        self._flow_terminated = True

    def _visit_loop(
        self,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
        incoming: _BindingState,
        iteration_state: _BindingState,
        may_skip: bool,
        may_break: bool,
        *,
        repeat: bool = False,
        natural_exit_possible: bool = True,
        repeated_test_may_raise: bool = False,
    ) -> None:
        del may_break
        if repeat:
            loop_entry = iteration_state
            while True:
                self._loop_break_states.append([])
                self._loop_continue_states.append([])
                self._restore(loop_entry)
                self._flow_terminated = False
                self._visit_statements(body)
                body_state = self._snapshot()
                break_states = self._loop_break_states.pop()
                continue_states = self._loop_continue_states.pop()
                continuation_states = [
                    *continue_states,
                    *([] if self._flow_terminated else [body_state]),
                ]
                if repeated_test_may_raise and continuation_states:
                    self._record_exception_boundary(self._merge_states(*continuation_states))
                next_entry = (
                    self._merge_states(iteration_state, *continuation_states)
                    if continuation_states
                    else iteration_state
                )
                if self._state_key(next_entry) == self._state_key(loop_entry):
                    break
                loop_entry = next_entry

            self._flow_terminated = False
            exit_states = break_states.copy()
            if natural_exit_possible:
                exit_states.append(self._run_branch(orelse, loop_entry))
            if exit_states:
                self._restore(self._merge_states(*exit_states))
                self._flow_terminated = False
            else:
                self._restore(body_state)
                self._flow_terminated = True
            return

        self._loop_break_states.append([])
        self._loop_continue_states.append([])
        self._restore(iteration_state)
        self._flow_terminated = False
        self._visit_statements(body)
        body_state = self._snapshot()
        break_states = self._loop_break_states.pop()
        continue_states = self._loop_continue_states.pop()
        continuation_states = [
            *continue_states,
            *([] if self._flow_terminated else [body_state]),
        ]
        if may_skip:
            continuation_states.append(incoming)
        if repeated_test_may_raise and continuation_states:
            self._record_exception_boundary(self._merge_states(*continuation_states))
        self._flow_terminated = False
        exit_states = break_states.copy()
        if continuation_states:
            loop_exit = self._merge_states(*continuation_states)
            exit_states.append(self._run_branch(orelse, loop_exit))
        if exit_states:
            self._restore(self._merge_states(*exit_states))
            self._flow_terminated = False
        else:
            self._restore(body_state)
            self._flow_terminated = True

    @classmethod
    def _body_may_break(cls, body: list[ast.stmt]) -> bool:
        """Return whether a break can exit the loop owning *body*."""
        for statement in body:
            if isinstance(statement, ast.Break):
                return True
            if isinstance(statement, ast.If) and isinstance(statement.test, ast.Constant):
                selected = statement.body if bool(statement.test.value) else statement.orelse
                if cls._body_may_break(selected):
                    return True
                continue
            if isinstance(
                statement,
                (
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                continue
            nested_bodies: list[list[ast.stmt]] = []
            if isinstance(statement, ast.If):
                nested_bodies.extend((statement.body, statement.orelse))
            elif isinstance(statement, ast.Try | ast.TryStar):
                nested_bodies.extend((statement.body, statement.orelse, statement.finalbody))
                nested_bodies.extend(handler.body for handler in statement.handlers)
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                nested_bodies.append(statement.body)
            elif isinstance(statement, ast.Match):
                nested_bodies.extend(case.body for case in statement.cases)
            if any(cls._body_may_break(nested) for nested in nested_bodies):
                return True
        return False

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        incoming = self._snapshot()
        elements = self._static_iteration_elements(node.iter)
        may_break = self._body_may_break(node.body)
        if elements is not None and not may_break:
            state = incoming
            self._loop_break_states.append([])
            self._loop_continue_states.append([])
            for element in elements:
                self._restore(state)
                self._bind_target_value(node.target, element)
                self._flow_terminated = False
                self._visit_statements(node.body)
                body_state = self._snapshot()
                continue_states = self._loop_continue_states[-1]
                candidates = [
                    *continue_states,
                    *([] if self._flow_terminated else [body_state]),
                ]
                self._loop_continue_states[-1] = []
                state = self._merge_states(*candidates) if candidates else body_state
            self._loop_break_states.pop()
            self._loop_continue_states.pop()
            self._flow_terminated = False
            self._restore(state)
            self._visit_statements(node.orelse)
            return
        iteration_state, may_skip = self._iteration_state(node.target, node.iter, incoming)
        self._visit_loop(
            node.body,
            node.orelse,
            incoming,
            iteration_state,
            may_skip,
            may_break,
            repeated_test_may_raise=True,
        )

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.iter)
        incoming = self._snapshot()
        iteration_state, may_skip = self._iteration_state(node.target, node.iter, incoming)
        self._visit_loop(
            node.body,
            node.orelse,
            incoming,
            iteration_state,
            may_skip,
            self._body_may_break(node.body),
            repeated_test_may_raise=True,
        )

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        incoming = self._snapshot()
        constant_truth = self._constant_truth(node.test)
        if constant_truth is False:
            self._restore(incoming)
            for statement in node.orelse:
                self.visit(statement)
            return
        self._visit_loop(
            node.body,
            node.orelse,
            incoming,
            incoming,
            constant_truth is not True,
            self._body_may_break(node.body),
            repeat=True,
            natural_exit_possible=constant_truth is not True,
            repeated_test_may_raise=not isinstance(node.test, (ast.Constant, ast.Name)),
        )

    @staticmethod
    def _handlers_catch_body_exceptions(
        body: list[ast.stmt],
        handlers: list[ast.ExceptHandler],
    ) -> bool:
        handled_names = {
            handler.type.id for handler in handlers if isinstance(handler.type, ast.Name)
        }
        if any(handler.type is None for handler in handlers) or "BaseException" in handled_names:
            return True

        def only_known_raises(statements: list[ast.stmt]) -> bool:
            catches_exception = "Exception" in handled_names
            for statement in statements:
                if isinstance(statement, ast.Raise):
                    if not isinstance(statement.exc, ast.Call) or not isinstance(
                        statement.exc.func, ast.Name
                    ):
                        return False
                    raised_name = statement.exc.func.id
                    if raised_name not in handled_names and not (
                        catches_exception
                        and raised_name
                        not in {
                            "BaseException",
                            "GeneratorExit",
                            "KeyboardInterrupt",
                            "SystemExit",
                        }
                    ):
                        return False
                    continue
                if isinstance(statement, (ast.Assign, ast.Delete, ast.Pass)):
                    continue
                if isinstance(statement, ast.If):
                    if not only_known_raises(statement.body) or not only_known_raises(
                        statement.orelse
                    ):
                        return False
                    continue
                return False
            return True

        return bool(handlers) and only_known_raises(body)

    def _visit_try(self, node: ast.Try | ast.TryStar) -> None:
        break_offsets = [len(states) for states in self._loop_break_states]
        continue_offsets = [len(states) for states in self._loop_continue_states]
        return_offsets = [len(states) for states in self._return_states]
        incoming = self._snapshot()
        body_state, body_terminated, body_exception_states = self._run_branch_flow_with_boundaries(
            node.body, incoming
        )
        exception_states = body_exception_states.copy()
        escaping_exception_states = (
            []
            if self._handlers_catch_body_exceptions(node.body, node.handlers)
            else body_exception_states.copy()
        )
        normal_states: list[_BindingState] = []
        if exception_states:
            exception_state = self._merge_states(*exception_states)
            for handler in node.handlers:
                self._restore(exception_state)
                self._flow_terminated = False
                if handler.type is not None:
                    self.visit(handler.type)
                if handler.name is not None:
                    self._clear(handler.name)
                handler_state, handler_terminated, handler_boundaries = (
                    self._run_branch_flow_with_boundaries(handler.body, self._snapshot())
                )
                exception_states.extend(handler_boundaries)
                escaping_exception_states.extend(handler_boundaries)
                self._restore(handler_state)
                if handler.name is not None:
                    self._clear(handler.name)
                if not handler_terminated:
                    normal_states.append(self._snapshot())
        if not body_terminated:
            else_state, else_terminated, else_boundaries = self._run_branch_flow_with_boundaries(
                node.orelse, body_state
            )
            exception_states.extend(else_boundaries)
            escaping_exception_states.extend(else_boundaries)
            if not else_terminated:
                normal_states.append(else_state)

        pending_breaks: list[tuple[list[_BindingState], _BindingState]] = []
        for states, offset in zip(
            self._loop_break_states,
            break_offsets,
            strict=True,
        ):
            pending_breaks.extend((states, state) for state in states[offset:])
            del states[offset:]
        pending_continues: list[tuple[list[_BindingState], _BindingState]] = []
        for states, offset in zip(
            self._loop_continue_states,
            continue_offsets,
            strict=True,
        ):
            pending_continues.extend((states, state) for state in states[offset:])
            del states[offset:]
        pending_returns: list[tuple[list[_BindingState], _BindingState]] = []
        for states, offset in zip(
            self._return_states,
            return_offsets,
            strict=True,
        ):
            pending_returns.extend((states, state) for state in states[offset:])
            del states[offset:]

        final_state: _BindingState | None = None
        final_terminated = True
        inspection_offsets = [
            *(len(states) for states in self._loop_break_states),
            *(len(states) for states in self._loop_continue_states),
            *(len(states) for states in self._return_states),
        ]
        if node.finalbody and exception_states:
            self._run_branch_flow(
                node.finalbody,
                self._merge_states(*exception_states),
            )
            loop_states = [
                *self._loop_break_states,
                *self._loop_continue_states,
                *self._return_states,
            ]
            for states, offset in zip(loop_states, inspection_offsets, strict=True):
                del states[offset:]
        transformed_escaping_states: list[_BindingState] = []
        for state in escaping_exception_states:
            transformed, terminated = self._run_branch_flow(node.finalbody, state)
            if not terminated:
                transformed_escaping_states.append(transformed)
        if normal_states:
            post_try = self._merge_states(*normal_states)
            final_state, final_terminated = self._run_branch_flow(node.finalbody, post_try)
        for destination, state in [
            *pending_breaks,
            *pending_continues,
            *pending_returns,
        ]:
            transformed, terminated = self._run_branch_flow(node.finalbody, state)
            if not terminated:
                destination.append(transformed)

        if final_state is not None:
            self._restore(final_state)
        else:
            self._restore(body_state)
        self._flow_terminated = final_terminated
        if transformed_escaping_states:
            self._record_exception_boundary(self._merge_states(*transformed_escaping_states))

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._visit_try(node)

    def _nullcontext_value(self, expression: ast.expr) -> ast.expr | None:
        if (
            not isinstance(expression, ast.Call)
            or len(expression.args) != 1
            or not self._is_nullcontext_call(expression)
        ):
            return None

        return expression.args[0]

    def _is_nullcontext_call(self, expression: ast.expr) -> bool:
        if not isinstance(expression, ast.Call):
            return False
        function = expression.func
        if isinstance(function, ast.Name):
            options = self.known_values.get(function.id, ())
            if any(
                isinstance(option, ast.Constant) and option.value == _CONTEXTLIB_NULLCONTEXT
                for option in options
            ):
                return True
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "nullcontext"
            and isinstance(function.value, ast.Name)
        ):
            options = self.known_values.get(function.value.id, ())
            if any(
                isinstance(option, ast.Constant) and option.value == _CONTEXTLIB_MODULE
                for option in options
            ):
                return True
        return False

    @classmethod
    def _expression_may_raise(cls, expression: ast.expr) -> bool:
        if isinstance(expression, (ast.Constant, ast.Name)):
            return False
        if isinstance(expression, ast.NamedExpr):
            return cls._expression_may_raise(expression.value)
        if isinstance(expression, ast.Attribute):
            return True
        if isinstance(expression, (ast.Tuple, ast.List, ast.Set)):
            return any(cls._expression_may_raise(element) for element in expression.elts)
        return True

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            context = item.context_expr
            nullcontext_is_safe = (
                self._is_nullcontext_call(context)
                and isinstance(context, ast.Call)
                and not any(
                    self._expression_may_raise(expression)
                    for expression in [
                        *context.args,
                        *(keyword.value for keyword in context.keywords),
                    ]
                )
            )
            if not nullcontext_is_safe:
                self._record_exception_boundary(self._snapshot())
            self.visit(context)
            if item.optional_vars is not None:
                self._bind_target_value(
                    item.optional_vars,
                    self._nullcontext_value(item.context_expr),
                )
        self._visit_statements(node.body)
        self._record_exception_boundary(self._snapshot())

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    @staticmethod
    def _pattern_names(pattern: ast.pattern) -> set[str]:
        names: set[str] = set()
        for descendant in ast.walk(pattern):
            if isinstance(descendant, ast.MatchAs) and descendant.name is not None:
                names.add(descendant.name)
            elif isinstance(descendant, ast.MatchStar) and descendant.name is not None:
                names.add(descendant.name)
            elif isinstance(descendant, ast.MatchMapping) and descendant.rest is not None:
                names.add(descendant.rest)
        return names

    def _bind_pattern(self, pattern: ast.pattern, value: ast.expr | None) -> None:
        if isinstance(pattern, ast.MatchAs):
            if pattern.pattern is not None:
                self._bind_pattern(pattern.pattern, value)
            if pattern.name is not None:
                self._bind_target_value(ast.Name(id=pattern.name), value)
            return
        if isinstance(pattern, ast.MatchStar):
            if pattern.name is not None:
                self._bind_target_value(ast.Name(id=pattern.name), value)
            return
        if isinstance(pattern, ast.MatchSequence):
            if isinstance(value, (ast.Tuple, ast.List)) and len(pattern.patterns) == len(
                value.elts
            ):
                for child_pattern, child_value in zip(
                    pattern.patterns,
                    value.elts,
                    strict=True,
                ):
                    self._bind_pattern(child_pattern, child_value)
            else:
                for name in self._pattern_names(pattern):
                    self._clear(name)
            return
        for name in self._pattern_names(pattern):
            self._clear(name)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        incoming = self._snapshot()
        case_states: list[_BindingState] = []
        for case in node.cases:
            self._restore(incoming)
            self._flow_terminated = False
            self._bind_pattern(case.pattern, node.subject)
            if case.guard is not None:
                self._record_exception_boundary(self._snapshot())
                self.visit(case.guard)
            self._visit_statements(case.body)
            if not self._flow_terminated:
                case_states.append(self._snapshot())
        exhaustive = any(
            isinstance(case.pattern, ast.MatchAs)
            and case.pattern.pattern is None
            and case.guard is None
            for case in node.cases
        )
        if case_states:
            self._restore(
                self._merge_states(*case_states)
                if exhaustive
                else self._merge_states(incoming, *case_states)
            )
            self._flow_terminated = False
        elif exhaustive:
            self._restore(incoming)
            self._flow_terminated = True
        else:
            self._restore(incoming)
            self._flow_terminated = False

    def visit_Lambda(self, node: ast.Lambda) -> None:
        positional = node.args.posonlyargs + node.args.args
        default_pairs = [
            *zip(
                positional[len(positional) - len(node.args.defaults) :],
                node.args.defaults,
                strict=True,
            ),
            *(
                (argument, value)
                for argument, value in zip(
                    node.args.kwonlyargs,
                    node.args.kw_defaults,
                    strict=True,
                )
                if value is not None
            ),
        ]
        for _, value in default_pairs:
            self.visit(value)
        default_bindings = {
            argument.arg: _resolve_value_binding(
                value,
                self.module_aliases,
                self.callable_aliases,
                self.pipe_aliases,
            )
            for argument, value in default_pairs
        }
        saved = self._snapshot()
        for name in self._argument_names(node.args):
            self._clear(name)
        for name, binding in default_bindings.items():
            self._bind(name, binding)
        self.visit(node.body)
        self._restore(saved)

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        values: list[ast.expr],
    ) -> None:
        saved = self._snapshot()
        may_skip = False
        for generator in generators:
            self.visit(generator.iter)
            incoming = self._snapshot()
            iteration_state, iteration_may_skip = self._iteration_state(
                generator.target,
                generator.iter,
                incoming,
            )
            may_skip = may_skip or iteration_may_skip or bool(generator.ifs)
            self._restore(iteration_state)
            for condition in generator.ifs:
                self.visit(condition)
        for value in values:
            self.visit(value)
        completed = self._snapshot()
        walrus_names = {
            descendant.target.id
            for expression in [*values, *(condition for gen in generators for condition in gen.ifs)]
            for descendant in ast.walk(expression)
            if isinstance(descendant, ast.NamedExpr) and isinstance(descendant.target, ast.Name)
        }
        final_state = self._merge_states(saved, completed) if may_skip else completed
        walrus_bindings = {
            name: self._binding_from_state(name, final_state) for name in walrus_names
        }
        self._restore(saved)
        for name, binding in walrus_bindings.items():
            self._bind(name, binding)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        saved = self._snapshot()
        self._visit_comprehension(node.generators, [node.elt])
        # Generator bodies execute only when iterated. Their assignments do not
        # affect the enclosing scope at generator creation time.
        self._restore(saved)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, [node.key, node.value])

    def _visit_scope(self, body: list[ast.stmt], shadowed: set[str]) -> None:
        saved = self._snapshot()
        outer_terminated = self._flow_terminated
        for name in shadowed:
            self._clear(name)
        self._flow_terminated = False
        self._visit_statements(body)
        self._restore(saved)
        self._flow_terminated = outer_terminated

    @staticmethod
    def _scope_declarations(body: list[ast.stmt]) -> tuple[set[str], set[str]]:
        global_names: set[str] = set()
        nonlocal_names: set[str] = set()

        def inspect(statement: ast.stmt) -> None:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return
            if isinstance(statement, ast.Global):
                global_names.update(statement.names)
                return
            if isinstance(statement, ast.Nonlocal):
                nonlocal_names.update(statement.names)
                return
            for child in ast.iter_child_nodes(statement):
                if isinstance(child, ast.stmt):
                    inspect(child)
                elif isinstance(child, ast.ExceptHandler):
                    for nested in child.body:
                        inspect(nested)

        for statement in body:
            inspect(statement)
        return global_names, nonlocal_names

    def _scope_binding_summary(
        self,
        body: list[ast.stmt],
        initial_declared: set[str],
        initial_summary: dict[str, _Binding],
        global_names: set[str],
        nonlocal_names: set[str],
    ) -> tuple[set[str], dict[str, _Binding]]:
        modules = self.module_aliases.copy()
        callables = self.callable_aliases.copy()
        pipes = self.pipe_aliases.copy()
        declared = initial_declared.copy()
        summary = initial_summary.copy()

        def record(name: str, binding: _Binding) -> None:
            if name in global_names or name in nonlocal_names:
                return
            declared.add(name)
            modules.discard(name)
            callables.pop(name, None)
            pipes.discard(name)
            module, possible_calls, pipe = binding
            if module:
                modules.add(name)
            if possible_calls:
                callables[name] = possible_calls
            if pipe:
                pipes.add(name)
            previous = summary.get(name, (False, frozenset(), False))
            summary[name] = (
                previous[0] or module,
                previous[1] | possible_calls,
                previous[2] or pipe,
            )

        def resolve(value: ast.expr | None) -> _Binding:
            return _resolve_value_binding(value, modules, callables, pipes)

        def inspect(statement: ast.stmt) -> None:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                record(statement.name, (False, frozenset(), False))
                return
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    bound = alias.asname or alias.name.split(".", maxsplit=1)[0]
                    imported_binding: _Binding = (
                        (True, frozenset(), False)
                        if alias.name == "subprocess"
                        else (False, frozenset(), False)
                    )
                    record(bound, imported_binding)
                return
            if isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    bound = alias.asname or alias.name
                    imported_binding = False, frozenset(), False
                    if statement.module == "subprocess":
                        if alias.name in _ALL_SUBPROCESS_CALLS:
                            imported_binding = False, frozenset({alias.name}), False
                        elif alias.name == "PIPE":
                            imported_binding = False, frozenset(), True
                    record(bound, imported_binding)
                return
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                for name, value in _assignment_pairs(statement):
                    record(name, resolve(value))
            elif isinstance(statement, ast.AugAssign):
                for name in _target_names(statement.target):
                    record(name, (False, frozenset(), False))
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                for name in _target_names(statement.target):
                    record(name, (False, frozenset(), False))
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    if item.optional_vars is not None:
                        for name in _target_names(item.optional_vars):
                            record(name, (False, frozenset(), False))
            elif isinstance(statement, ast.Try | ast.TryStar):
                for handler in statement.handlers:
                    if handler.name is not None:
                        record(handler.name, (False, frozenset(), False))
            elif isinstance(statement, ast.Match):
                for case in statement.cases:
                    for name in self._pattern_names(case.pattern):
                        record(name, (False, frozenset(), False))

            for child in ast.iter_child_nodes(statement):
                if isinstance(child, ast.stmt):
                    inspect(child)
                elif isinstance(child, ast.ExceptHandler):
                    for nested in child.body:
                        inspect(nested)
                elif isinstance(child, ast.expr):
                    inspect_expression(child)

        def inspect_expression(expression: ast.expr) -> None:
            if isinstance(expression, ast.Lambda):
                return
            if isinstance(expression, ast.NamedExpr):
                for name in _target_names(expression.target):
                    record(name, resolve(expression.value))
            for child in ast.iter_child_nodes(expression):
                if isinstance(child, ast.expr):
                    inspect_expression(child)
                elif isinstance(child, ast.comprehension):
                    inspect_expression(child.iter)
                    for condition in child.ifs:
                        inspect_expression(condition)

        for statement in body:
            inspect(statement)
        declared.difference_update(global_names | nonlocal_names)
        return declared, summary

    @staticmethod
    def _binding_from_state(name: str, state: _BindingState) -> _Binding:
        modules, callables, pipes, _ = state
        return name in modules, callables.get(name, frozenset()), name in pipes

    @staticmethod
    def _argument_names(arguments: ast.arguments) -> set[str]:
        args = arguments.posonlyargs + arguments.args + arguments.kwonlyargs
        names = {arg.arg for arg in args}
        if arguments.vararg is not None:
            names.add(arguments.vararg.arg)
        if arguments.kwarg is not None:
            names.add(arguments.kwarg.arg)
        return names

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        positional = node.args.posonlyargs + node.args.args
        default_pairs = [
            *zip(
                positional[len(positional) - len(node.args.defaults) :],
                node.args.defaults,
                strict=True,
            ),
            *(
                (argument, value)
                for argument, value in zip(
                    node.args.kwonlyargs,
                    node.args.kw_defaults,
                    strict=True,
                )
                if value is not None
            ),
        ]
        defaults = [value for _, value in default_pairs]
        for expression in [*node.decorator_list, *defaults]:
            self.visit(expression)
        default_bindings = {
            argument.arg: _resolve_value_binding(
                value,
                self.module_aliases,
                self.callable_aliases,
                self.pipe_aliases,
            )
            for argument, value in default_pairs
        }
        global_names, nonlocal_names = self._scope_declarations(node.body)
        declared, summary = self._scope_binding_summary(
            node.body,
            self._argument_names(node.args),
            default_bindings,
            global_names,
            nonlocal_names,
        )
        saved = self._snapshot()
        top_level_function = not self._enclosing_summaries
        for name in self._argument_names(node.args):
            self._clear(name)
        for name, binding in default_bindings.items():
            self._bind(name, binding)
        if self._active_module_state is not None:
            module_names = (
                (self._active_module_names or set())
                | self._active_module_state[0]
                | set(self._active_module_state[1])
                | self._active_module_state[2]
                | set(self._active_module_state[3])
            )
            visible_module_names = global_names | (
                module_names - declared if top_level_function else set()
            )
            for name in visible_module_names:
                self._bind(name, self._binding_from_state(name, self._active_module_state))
                if name in self._active_module_state[3]:
                    self.known_values[name] = self._active_module_state[3][name]
        for name in nonlocal_names:
            for outer_declared, outer_summary in reversed(self._enclosing_summaries):
                if name in outer_declared:
                    self._bind(
                        name,
                        outer_summary.get(name, (False, frozenset(), False)),
                    )
                    break
        inherited_names: set[str] = set()
        for outer_declared, outer_summary in reversed(self._enclosing_summaries):
            for name in outer_declared - declared - inherited_names - global_names - nonlocal_names:
                self._bind(
                    name,
                    outer_summary.get(name, (False, frozenset(), False)),
                )
                inherited_names.add(name)
        self._enclosing_summaries.append((declared, summary))
        outer_terminated = self._flow_terminated
        self._flow_terminated = False
        self._return_states.append([])
        self._visit_statements(node.body)
        self._return_states.pop()
        self._enclosing_summaries.pop()
        self._restore(saved)
        self._clear(node.name)
        self._flow_terminated = outer_terminated

    def visit_Module(self, node: ast.Module) -> None:
        _, summary = self._scope_binding_summary(
            node.body,
            set(),
            {},
            set(),
            set(),
        )
        prepass = _SubprocessCallVisitor()
        for statement in node.body:
            prepass.visit(statement)
        binding_counts: dict[str, int] = {}

        def count(name: str) -> None:
            binding_counts[name] = binding_counts.get(name, 0) + 1

        def count_bindings(item: ast.AST) -> None:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count(item.name)
                for expression in [
                    *item.decorator_list,
                    *item.args.defaults,
                    *(value for value in item.args.kw_defaults if value is not None),
                ]:
                    count_bindings(expression)
                return
            if isinstance(item, ast.ClassDef):
                count(item.name)
                for expression in [*item.decorator_list, *item.bases]:
                    count_bindings(expression)
                for keyword in item.keywords:
                    count_bindings(keyword)
                return
            if isinstance(item, ast.Lambda):
                for expression in [
                    *item.args.defaults,
                    *(value for value in item.args.kw_defaults if value is not None),
                ]:
                    count_bindings(expression)
                return
            if isinstance(item, ast.Import):
                for alias in item.names:
                    count(alias.asname or alias.name.split(".", maxsplit=1)[0])
                return
            if isinstance(item, ast.ImportFrom):
                for alias in item.names:
                    count(alias.asname or alias.name)
                return
            if isinstance(item, ast.ExceptHandler) and item.name is not None:
                count(item.name)
            elif isinstance(item, ast.MatchAs) and item.name is not None:
                count(item.name)
            elif isinstance(item, ast.MatchStar) and item.name is not None:
                count(item.name)
            elif isinstance(item, ast.MatchMapping) and item.rest is not None:
                count(item.rest)
            elif isinstance(item, ast.Name) and isinstance(item.ctx, (ast.Store, ast.Del)):
                count(item.id)
            for child in ast.iter_child_nodes(item):
                count_bindings(child)

        for statement in node.body:
            count_bindings(statement)
        globally_declared = {
            name
            for descendant in ast.walk(node)
            if isinstance(descendant, ast.Global)
            for name in descendant.names
        }
        direct_assignment_names = {
            name
            for statement in node.body
            if isinstance(statement, (ast.Assign, ast.AnnAssign))
            for name, _ in _assignment_pairs(statement)
        }
        stable_known_values = {
            name: options
            for name, options in prepass.known_values.items()
            if name in direct_assignment_names
            and binding_counts.get(name) == 1
            and name not in globally_declared
        }
        self._active_module_names = set(summary)
        self._active_module_state = (
            {name for name, binding in summary.items() if binding[0]},
            {name: binding[1] for name, binding in summary.items() if binding[1]},
            {name for name, binding in summary.items() if binding[2]},
            stable_known_values,
        )
        self._visit_statements(node.body)
        self._active_module_state = None
        self._active_module_names = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(expression)
        self._visit_scope(node.body, set())
        self._clear(node.name)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_flagged(
            node,
            self.module_aliases,
            self.callable_aliases,
            self.pipe_aliases,
        ):
            self.flagged_lines.append(node.lineno)
        self.generic_visit(node)


_SUPPRESSION_COMMENT = "# subprocess-encoding: strict-ok"

# The one token every flaggable binding must contain. See `_scan_all`.
_SUBPROCESS_TOKEN = "subprocess"


class ScanError(RuntimeError):
    """Raised when the gate cannot inspect its declared source corpus."""


def _clean_git_env() -> dict[str, str]:
    """Return the process environment without ambient Git repository pointers."""
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def find_violations(source: str, filename: str = "<string>") -> list[int]:
    """Return line numbers of flagged calls in *source*.

    A call on a line that ends with ``# subprocess-encoding: strict-ok`` is
    suppressed. Use this only when strict decoding is intentional and
    documented (for example, when the stream is guaranteed valid UTF-8 and a
    decode failure should propagate as an error rather than silently produce
    replacement characters).
    """
    return _violations_in_tree(ast.parse(source, filename=filename), source)


def _violations_in_tree(tree: ast.Module, source: str) -> list[int]:
    """Return flagged line numbers for an already-parsed *tree*.

    Split out of :func:`find_violations` so :func:`_scan_all` can parse a file
    once and then decide whether the walk is worth doing. See the probe there.
    """
    visitor = _SubprocessCallVisitor()
    visitor.visit(tree)

    source_lines = source.splitlines()

    def _suppressed(lineno: int) -> bool:
        if lineno < 1 or lineno > len(source_lines):
            return False
        return _SUPPRESSION_COMMENT in source_lines[lineno - 1]

    return sorted({lineno for lineno in visitor.flagged_lines if not _suppressed(lineno)})


def _collect_sources(repo_root: Path) -> list[Path]:
    """Return tracked Python files under ``scripts/`` that are not in cache dirs."""
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "scripts/*.py",
                "scripts/**/*.py",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(f"git could not list tracked scripts: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"git exited {completed.returncode}"
        raise ScanError(f"git could not list tracked scripts: {detail}")

    rels = [entry for entry in completed.stdout.split("\0") if entry]
    sources = [repo_root / rel for rel in rels if rel.endswith(".py")]
    if not sources:
        raise ScanError("git reported zero tracked Python files under scripts/")
    return sources


def _scan_all(
    repo_root: Path,
    sources: list[Path] | None = None,
) -> tuple[list[tuple[Path, int]], int]:
    """Return violations and the number of source files examined."""
    sources = _collect_sources(repo_root) if sources is None else sources
    results: list[tuple[Path, int]] = []
    for path in sources:
        try:
            mode = path.stat(follow_symlinks=False).st_mode
        except OSError as exc:
            raise ScanError(f"tracked source is missing: {path}") from exc
        if not stat.S_ISREG(mode):
            raise ScanError(f"tracked source is not a regular file: {path}")
        try:
            source = path.read_text(encoding="utf-8")
            # Parse every file, walk only the ones that can hold a violation.
            #
            # Every binding this gate can flag is anchored on the literal token
            # `subprocess`: `_SubprocessCallVisitor` binds an alias only from
            # `import subprocess` or `from subprocess import ...`. A file whose
            # source omits that token can bind nothing, so walking it is pure
            # cost.
            #
            # The walk is the cost, not the parse. Measured over all 2246
            # tracked Python files on an 8 core host: 7.24s to parse them all,
            # 63.16s to parse and walk them all. So the parse stays
            # unconditional and only the walk is skipped, which keeps the
            # ScanError this gate raises on an unparseable tracked file. An
            # earlier revision skipped the parse too and broke
            # `test_main_exits_two_on_tracked_syntax_error`, which is the test
            # that owns that contract.
            #
            # Why it matters: issue #5482 registered this scanner against the
            # whole tree, which fixed a real 78% blind spot and made it the
            # critical path of the concurrent `count-ratchets` registry.
            # Measured after #5546 merged, at load average 7.7:
            # subprocess-encoding 67.31s alone, whole registry 80.61s to 82.03s,
            # against a 85s deadline and a 90s lefthook cap.
            #
            # 989 of 2246 tracked files mention subprocess, so the walk is
            # skipped for 56% of the corpus.
            #
            # Equivalence was replayed, not argued: the unconditional-walk
            # implementation over all 2246 files returns 238 violations, this
            # one returns the same 238, 0 mismatches. See
            # `test_the_probe_matches_an_unprobed_scan_over_the_whole_corpus`.
            tree = ast.parse(source, filename=str(path))
            lines = _violations_in_tree(tree, source) if _SUBPROCESS_TOKEN in source else []
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise ScanError(f"could not analyze tracked source {path}: {exc}") from exc
        for lineno in lines:
            results.append((path, lineno))
    return results, len(sources)


def find_all_violations(
    repo_root: Path,
    sources: list[Path] | None = None,
) -> list[tuple[Path, int]]:
    """Return ``(path, lineno)`` pairs for every flagged call site."""
    return _scan_all(repo_root, sources)[0]


def validate_subprocess_encoding(repo_root: Path) -> bool:
    """Return True when no violation is found.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used
    by ``pre_pr_sequence.py``.
    """
    violations, scanned_files = _scan_all(repo_root)
    if not violations:
        print(
            f"[OK] Scanned {scanned_files} tracked Python file(s) under scripts/; "
            "0 subprocess encoding violations."
        )
        return True
    count = len(violations)
    print(
        f"[FAIL] {count} subprocess call(s) in {scanned_files} tracked file(s) "
        'pin UTF-8 encoding without errors="replace":',
        file=sys.stderr,
    )
    for path, lineno in violations:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{lineno}", file=sys.stderr)
    print(
        '\nFix: add errors="replace" to each flagged call.',
        file=sys.stderr,
    )
    print(
        "Reason: a child process on Windows can emit bytes invalid for UTF-8.",
        file=sys.stderr,
    )
    print(
        'Without errors="replace", the decode raises before the caller can report '
        "the real failure.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        return 0 if validate_subprocess_encoding(repo_root) else 1
    except ScanError as exc:
        print(f"[FAIL] Subprocess encoding scan did not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
