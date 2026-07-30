"""Every subprocess call that captures text under ``scripts/`` pins its codec.

``subprocess`` with ``text=True`` and no explicit ``encoding`` decodes captured
bytes with ``locale.getpreferredencoding(False)``. That is UTF-8 on the Linux
runners and something else on the Windows runner in this repo's CI matrix.

The tools we shell out to emit raw UTF-8, not escaped ASCII. ``gh`` writes
non-ASCII straight into JSON string values, and ``git`` hands back filesystem
paths, branch names, and commit messages as raw bytes. Decoding those under a
legacy codec does not raise: cp1252 maps almost every byte, so the call
succeeds and returns different characters than the tool wrote. ``json.loads``
accepts the result, so the corruption reaches the caller silently.

This module is the standing guard. It walks the AST rather than the text so a
reformatted call site cannot slip past.

It checks ``encoding`` only. ``errors`` is deliberately left to each call site:
the default is ``strict``, which fails loudly, and a lenient handler would
reintroduce the silent corruption this guard exists to prevent.

The checks below are deliberately conservative, because a guard meant to hold
forever is worth more than any single call site it protects. Four rounds of
adversarial review found genuinely locale-decoding calls that earlier, looser
versions waved through. Each one has a case in
``test_detector_closes_the_evasions``:

* ``encoding=None``, and ``utf-8-sig``, which strips a BOM and so is not the
  pinned codec.
* An aliased or directly imported ``run``.
* A non-literal ``text`` or ``capture_output`` flag, such as ``text=1``.
* ``getoutput`` and ``getstatusoutput``, which always decode and take no flag.
* A ``**kwargs`` splat, which can carry ``text=True`` with no literal keyword
  left in the source to read.
* Any binding that reaches an entry point without an import: ``_run =
  subprocess.run``, a chain of those, an annotated assignment, a binding made
  inside a function body, ``functools.partial``, and ``getattr``.

The last group is why name resolution runs to a fixed point rather than in a
single pass, and why a ``partial`` that selects text mode counts even with no
capture keyword beside it.

What this cannot see, stated plainly: a subprocess reference that crosses a
module boundary, one stored in an attribute, and one produced by a call this
module does not model. The scan is a ratchet against the shapes people
actually write, not a proof.

Where it deliberately says too much rather than too little, see
``test_detector_over_approximates_deliberately``. Every rule here is tuned to
fail towards a redundant keyword, never towards a missed decode.
"""

from __future__ import annotations

import ast
import codecs
import time
from collections import Counter
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

_CAPTURING_ATTRS = frozenset({"run", "check_output", "Popen"})

# getoutput and getstatusoutput take no capture or text flags. They always
# return decoded text, and their encoding parameter defaults to None.
_ALWAYS_TEXT_ATTRS = frozenset({"getoutput", "getstatusoutput"})

_SUBPROCESS_ATTRS = _CAPTURING_ATTRS | _ALWAYS_TEXT_ATTRS

# check_output passes stdout=PIPE itself, so it captures whatever the call
# site says. Nothing in the source has to ask for capture, which means text
# mode on its own is enough to decode. run and Popen are not like this: with
# no capture keyword their output goes to the inherited handles and never
# becomes a str.
_ALWAYS_CAPTURING_ATTRS = frozenset({"check_output"})

_PINNED_CODEC = "utf-8"
_OS_POPEN = "os.popen"

# Modules whose aliases have to be followed. Held as a table rather than a
# hardcoded owner check, so ``import os as myos`` cannot disagree with
# ``import subprocess as sp`` about which module a name stands for.
_TRACKED_MODULES = frozenset({"subprocess", "os"})

# Attributes that hand back the callable they are read from. ``__get__`` is
# deliberately absent: it returns a fresh binding rather than the callable, so
# calling its result starts no process and flagging it would be noise.
_FORWARDING_ATTRS = frozenset({"__call__", "__func__", "__wrapped__"})
# Stands for a subprocess entry point selected at runtime, which no static
# scan can name. Because it may be getoutput, which decodes with no flag to
# read, invoking one counts as decoding text whatever keywords are present.
_DYNAMIC = "subprocess.<dynamic>"

# Marks a name that reaches functools.partial. Held in the same map as the
# subprocess names for want of a second one to thread, and filtered out of
# every path that answers "is this a subprocess entry point".
_ATTRIBUTE = "."
_UNKNOWN = object()
_PARTIAL = "functools.partial"
# Marks the null sink. Held beside the entry points so an imported ``DEVNULL``
# is recognised at a call site, and filtered out of every path that answers
# "is this a subprocess entry point".
_DEVNULL = "subprocess.DEVNULL"
# The two sentinels that ask for a pipe. Recognised by value so a positional
# capture argument can be found without reading which slot it sits in, since
# slot order is a property of one CPython release rather than of the API.
_PIPE = "subprocess.PIPE"
_STDOUT = "subprocess.STDOUT"
_CAPTURE_SENTINELS = frozenset({_PIPE, _STDOUT})
_NOT_ENTRY_POINTS = frozenset({_PARTIAL, _DEVNULL, _PIPE, _STDOUT})

# Calls that hand back the object they were given. Each one is a place a
# subprocess reference can pass through with no assignment statement to find.
# ``classmethod`` is deliberately absent: it binds the owning class as the
# first argument, so what comes out is not the callable that went in.
_PASSTHROUGH = frozenset({"nullcontext", "staticmethod", "enter_context"})

# Methods that hand back an element of their receiver. The index is not
# modelled, so the receiver is read whole, exactly as a subscript is.
_ELEMENT_METHODS = frozenset({"get", "setdefault", "pop", "popleft", "popitem"})

# Of those, the ones whose second argument is a fallback the receiver may
# never hold. That argument is a second path to the value and is read too.
_DEFAULTING_METHODS = frozenset({"get", "setdefault"})

# Builtins that select from or rebuild a container handed to them.
_ELEMENT_BUILTINS = frozenset(
    {"min", "max", "sorted", "reversed", "next", "iter", "list", "tuple", "set"}
)

# The literal container shapes an index can be read out of. Named so the
# non-mapping branch of _element is known to carry elts.
_Container = ast.Dict | ast.List | ast.Tuple
_Assign = ast.Assign | ast.AnnAssign | ast.NamedExpr | ast.AugAssign

# Nodes that open a namespace of their own. A walrus inside one of these binds
# there, not in the body that holds it.
_SCOPED = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)

# Entry points that hand back str no matter what keywords a call passes.
_DECODES_UNCONDITIONALLY = _ALWAYS_TEXT_ATTRS | frozenset({_DYNAMIC})

# Per module, the names worth binding from a ``from ... import`` and what each
# one resolves to. A table rather than a branch per module, so a new source of
# subprocess entry points is one row.
_IMPORTED_NAMES: dict[str, dict[str, str]] = {
    "subprocess": {attr: attr for attr in _SUBPROCESS_ATTRS}
    | {"DEVNULL": _DEVNULL, "PIPE": _PIPE, "STDOUT": _STDOUT},
    "functools": {"partial": _PARTIAL},
    "os": {"popen": _OS_POPEN},
}


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for keyword *name*, or ``None`` when absent."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _has_splat(call: ast.Call) -> bool:
    """Report whether *call* forwards ``**kwargs``.

    Live, and load bearing. This helper was dead once, and the reason it was
    dead was a hole in :func:`_captures_text`, not an excess of caution. See
    the splat cases in ``test_detector_closes_the_evasions``.
    """
    return any(keyword.arg is None for keyword in call.keywords)


def _is_falsy_literal(node: ast.expr | None) -> bool:
    """Report whether *node* is a constant Python reads as false.

    ``subprocess`` tests these keywords for truth, not against ``False``, so
    ``capture_output=0`` captures nothing and ``text=None`` decodes nothing.
    Only a constant qualifies: a name could hold anything, and reading it as
    off would be the quiet direction.
    """
    return isinstance(node, ast.Constant) and not node.value


def _constant_str(node: ast.expr | None) -> str | None:
    """Return the string *node* spells at parse time, or ``None``.

    An f-string with no placeholders and a concatenation of literals are both
    ordinary ways to write a codec name, and both reach the runtime as the
    same string. Refusing them flags a call that is already correct.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = [_constant_str(value) for value in node.values]
        return None if None in parts else "".join(part for part in parts if part)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _constant_str(node.left), _constant_str(node.right)
        return None if left is None or right is None else left + right
    return None


def _call_label(call: ast.Call) -> str:
    """Return the bare name being called, dropping any dotted owner."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _is_partial(label: str, functions: dict[str, str]) -> bool:
    """Report whether *label* names functools.partial under any spelling.

    The bare name is accepted on sight rather than anchored to a functools
    import, because ``partial`` from any library applies arguments the same
    way, and anchoring would drop every re-export. An aliased import needs the
    name map, since ``from functools import partial as p`` leaves no ``partial``
    anywhere at the call site.
    """
    return label == "partial" or functions.get(label) == _PARTIAL


def _resolve_indirect(
    call: ast.Call, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Resolve a wrapper call that yields a subprocess entry point.

    Covers ``functools.partial(subprocess.run, ...)`` and
    ``getattr(subprocess, "run")``. Both are static references wearing a
    disguise: the name is right there in the source.
    """
    label = _call_label(call)
    if _is_partial(label, functions) and call.args:
        return _resolve_callable(call.args[0], modules, functions)
    if label in _PASSTHROUGH and call.args:
        # ``nullcontext(subprocess.run)`` and ``staticmethod(subprocess.run)``
        # hand the reference straight back out, so the wrapper is not a wall.
        return _resolve_callable(call.args[0], modules, functions)
    if label in _ELEMENT_METHODS and isinstance(call.func, ast.Attribute):
        # ``TABLE.get("run")`` selects an element exactly as ``TABLE["run"]``
        # does, and the fallback of ``get`` and ``setdefault`` is a second
        # path to a value the receiver may never hold.
        reached = [call.func.value]
        if label in _DEFAULTING_METHODS:
            reached.extend(call.args[1:])
        return _resolve_elements(reached, modules, functions)
    if label in _ELEMENT_BUILTINS and call.args:
        return _resolve_elements(list(call.args), modules, functions)
    if label == "getattr" and len(call.args) >= 2:
        owner, attr = call.args[0], call.args[1]
        if isinstance(attr, ast.Constant) and attr.value in _FORWARDING_ATTRS:
            # ``getattr(subprocess.run, "__call__")`` composes the two shapes
            # below, so resolving the owner answers for the pair.
            return _resolve_callable(owner, modules, functions)
        held = modules.get(owner.id) if isinstance(owner, ast.Name) else None
        if held is None:
            return None
        if not isinstance(attr, ast.Constant):
            # ``getattr(subprocess, name)`` hides which entry point it reaches.
            # Nothing in this repository needs that, so the safe reading is
            # that it reaches one of them.
            return _DYNAMIC
        if held == "subprocess" and attr.value in _SUBPROCESS_ATTRS:
            return str(attr.value)
        if held == "os" and attr.value == "popen":
            return _OS_POPEN
    return None


def _resolve_elements(
    values: list[ast.expr], modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Return the entry point a container of *values* yields when subscripted.

    The index is deliberately not modelled, so any element reaching subprocess
    taints the whole container. Elements that disagree resolve to the member
    that is hardest to make compliant, because the subscript may select it.
    """
    found = {
        resolved
        for resolved in (
            _resolve_callable(value, modules, functions) for value in values
        )
        if resolved is not None
    }
    if not found:
        return None
    if len(found) == 1:
        return found.pop()
    if _OS_POPEN in found:
        return _OS_POPEN
    if found & _DECODES_UNCONDITIONALLY:
        return _DYNAMIC
    # Every remaining member decodes only when the same keywords say so, so the
    # call site answers for all of them and any one of them stands in.
    return sorted(found)[0]


def _literal(node: ast.expr) -> object:
    """Return the constant *node* spells, or ``_UNKNOWN`` when it spells none.

    ``ast.literal_eval`` reads a negative index, which the parser stores as a
    unary operation rather than a constant, and refuses anything computed. It
    evaluates no code, so a hostile subscript cannot reach this scan.
    """
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _UNKNOWN


def _element(node: ast.Subscript, containers: dict[str, _Container]) -> ast.expr | None:
    """Return the one element *node* selects, when the scan can name it.

    Only a literal index into a name bound exactly once to a literal container
    qualifies. Everything else returns ``None``, which leaves the caller
    holding the whole container. That is the safe direction: a dispatch table
    is flagged wholesale rather than read wrongly.
    """
    if not isinstance(node.value, ast.Name):
        return None
    literal = containers.get(node.value.id)
    if literal is None:
        return None
    key = _literal(node.slice)
    if key is _UNKNOWN:
        return None
    if isinstance(literal, ast.Dict):
        # A ``**splat`` key reads as ``None`` and can carry any name, so the
        # keys on show are not the whole mapping. No test can pin the
        # conditional, because ``_literal`` answers ``_UNKNOWN`` for ``None``
        # anyway. It is the type checker that requires it: ``keys`` holds
        # ``expr | None`` and ``_literal`` takes an ``expr``.
        stored = [_literal(k) if k is not None else _UNKNOWN for k in literal.keys]
        if _UNKNOWN in stored:
            return None
        for held, value in zip(stored, literal.values, strict=True):
            # ``True`` equals ``1`` and ``1`` equals ``1.0`` in Python, but a
            # dict written with one of them was not written with the other.
            if type(held) is type(key) and held == key:
                return value
        return None
    if not isinstance(key, int) or isinstance(key, bool):
        return None
    if any(isinstance(element, ast.Starred) for element in literal.elts):
        # A starred element expands to an unknown count, so every index after
        # it names something the scan cannot see.
        return None
    return literal.elts[key] if -len(literal.elts) <= key < len(literal.elts) else None


def _attribute(
    node: ast.Attribute, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Return the subprocess entry point ``owner.attr`` names, or ``None``."""
    if isinstance(node.value, ast.Name):
        owner, attr = modules.get(node.value.id), node.attr
        if owner == "subprocess" and attr in _SUBPROCESS_ATTRS:
            return attr
        if owner == "os" and attr == "popen":
            return _OS_POPEN
    if node.attr in _FORWARDING_ATTRS:
        # ``subprocess.run.__call__`` is the same callable read through an
        # attribute that hands it back, so the owner answers for it.
        return _resolve_callable(node.value, modules, functions)
    # No partial filter here, unlike the bare-name branch in the caller. The
    # sentinel is only ever written for an imported name, and every attribute
    # binding is resolved through that branch, which drops it.
    return functions.get(_ATTRIBUTE + node.attr)


def _resolve_callable(
    node: ast.expr,
    modules: dict[str, str],
    functions: dict[str, str],
    containers: dict[str, _Container] | None = None,
) -> str | None:
    """Return the subprocess entry point *node* evaluates to, or ``None``."""
    while isinstance(node, ast.Subscript):
        # ``RUNNERS[0](...)`` reaches whatever the container holds. A literal
        # index into a literal container names one element, so a dispatch
        # table does not taint every handler in it. Anything less certain
        # resolves the base instead, which means a computed index cannot slip
        # a subprocess reference past this scan. A subscript chain is left
        # recursive, so the parser caps no depth and unwinding it must not
        # recurse.
        selected = _element(node, containers) if containers else None
        node = node.value if selected is None else selected
    if isinstance(node, ast.Name):
        resolved = functions.get(node.id)
        return None if resolved in _NOT_ENTRY_POINTS else resolved
    if isinstance(node, ast.Attribute):
        return _attribute(node, modules, functions)
    if isinstance(node, ast.Starred):
        # ``(*RUNNERS,)[0]`` spreads a container into another one, and the
        # element that lands there is whatever the spread held.
        return _resolve_callable(node.value, modules, functions, containers)
    if isinstance(node, ast.BinOp):
        # ``([subprocess.run] + others)[0]`` and ``([subprocess.run] * 2)[0]``
        # both build a container holding what either side held.
        return _resolve_elements([node.left, node.right], modules, functions)
    if isinstance(node, ast.BoolOp):
        # ``cached or subprocess.run`` evaluates to either operand.
        return _resolve_elements(list(node.values), modules, functions)
    if isinstance(node, ast.IfExp):
        # ``subprocess.run if flag else None`` picks a branch at runtime, so
        # both branches are values the name can take.
        return _resolve_elements([node.body, node.orelse], modules, functions)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        # A comprehension yields whatever its element expression evaluates to,
        # and the index that selects one of them is not modelled.
        return _resolve_callable(node.elt, modules, functions, containers)
    if isinstance(node, ast.DictComp):
        return _resolve_callable(node.value, modules, functions, containers)
    if isinstance(node, ast.Call):
        return _resolve_indirect(node, modules, functions)
    if isinstance(node, ast.NamedExpr):
        # ``(r := subprocess.run)(...)`` binds and calls in one expression.
        return _resolve_callable(node.value, modules, functions, containers)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return _resolve_elements(list(node.elts), modules, functions)
    if isinstance(node, ast.Dict):
        return _resolve_elements(
            [value for value in node.values if value is not None], modules, functions
        )
    return None


def _unpack(target: ast.expr, value: ast.expr) -> list[tuple[str, ast.expr]]:
    """Pair every name in an assignment *target* with the value it may receive.

    Shapes that line up are matched element by element. When they do not line
    up the right side is unknown, so every name on the left is paired with the
    whole of it rather than dropped. An attribute target binds under its own
    key, because the object holding it is out of reach of this scan.
    """
    if isinstance(target, ast.Name):
        return [(target.id, value)]
    if isinstance(target, ast.Starred):
        return _unpack(target.value, value)
    if isinstance(target, ast.Attribute):
        # Which object holds the attribute is not modelled, so the attribute
        # name alone carries the binding. The leading dot cannot appear in an
        # identifier, so these keys never collide with a plain name.
        return [(_ATTRIBUTE + target.attr, value)]
    if isinstance(target, ast.Subscript):
        return _subscripted(target, value)
    if not isinstance(target, (ast.Tuple, ast.List)):
        return []
    if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
        return [
            pair
            for sub, item in zip(target.elts, value.elts, strict=True)
            for pair in _unpack(sub, item)
        ]
    return [pair for sub in target.elts for pair in _unpack(sub, value)]


def _subscripted(target: ast.Subscript, value: ast.expr) -> list[tuple[str, ast.expr]]:
    """Pair the name a subscript write binds with the value it receives.

    Two shapes bind through a subscript, and which one this is depends on what
    the base of the subscript holds rather than on the subscript itself.
    """
    if isinstance(target.value, ast.Call):
        # ``globals()["runner"] = subprocess.run`` binds a module-level name
        # with no name anywhere on the left of the assignment to read.
        if _call_label(target.value) not in {"globals", "vars"}:
            return []
        key = _literal(target.slice)
        return [(key, value)] if isinstance(key, str) else []
    if isinstance(target.value, ast.Name):
        # ``H[0] = subprocess.run`` puts the value into H without rebinding
        # the name, so the base takes the binding. Which slot it lands in
        # does not matter: the write is what stops H being read from its
        # literal, so the whole container has to answer for it.
        return [(target.value.id, value)]
    return []


def _iterated(target: ast.expr, iterable: ast.expr) -> list[tuple[str, ast.expr]]:
    """Pair the names a loop target binds with the values it may take.

    A loop target does not line up with the iterable, it lines up with one
    item of it at a time, so unpacking it against the iterable reads the
    wrong column: ``for label, runner in [(check_call, run)]`` would give
    ``label`` the whole first item and ``runner`` the whole second, when the
    source has only one item and two columns.

    A literal iterable makes its items visible, so each name is paired with
    every item it can take, one binding per item. Anything else is opaque and
    keeps the old reading, where every name may hold any part of it.
    """
    if not isinstance(iterable, (ast.List, ast.Tuple, ast.Set)):
        return _unpack(target, iterable)
    return [pair for item in iterable.elts for pair in _unpack(target, item)]


def _defaults(spec: ast.arguments) -> list[tuple[str, ast.expr]]:
    """Pair each parameter of *spec* with its default, where it has one.

    ``def go(runner=subprocess.run)`` binds the name once, when the function is
    defined, and every call that leaves the argument out reads that binding.
    """
    positional = spec.posonlyargs + spec.args
    filled = positional[len(positional) - len(spec.defaults) :]
    found = [(arg.arg, default) for arg, default in zip(filled, spec.defaults, strict=True)]
    found.extend(
        (arg.arg, default)
        for arg, default in zip(spec.kwonlyargs, spec.kw_defaults, strict=True)
        if default is not None
    )
    return found


def _installed(call: ast.Call) -> list[tuple[str, ast.expr]]:
    """Pair the attribute ``setattr`` writes with the value handed to it.

    ``setattr(holder, "runner", subprocess.run)`` is an attribute assignment
    spelled as a call, and it binds under the same dotted key one written with
    an equals sign would.
    """
    if _call_label(call) != "setattr" or len(call.args) != 3:
        return []
    name = _literal(call.args[1])
    return [(_ATTRIBUTE + name, call.args[2])] if isinstance(name, str) else []


def _entered(node: ast.With | ast.AsyncWith) -> list[tuple[str, ast.expr]]:
    """Pair each ``with`` target with the expression it takes its value from.

    ``with nullcontext(subprocess.run) as runner:`` binds a name with no
    assignment statement in sight, and the passthrough table is what decides
    whether the context manager hands the reference back out.
    """
    return [
        pair
        for item in node.items
        if item.optional_vars is not None
        for pair in _unpack(item.optional_vars, item.context_expr)
    ]


def _receives(call: ast.Call) -> list[tuple[str, ast.expr]]:
    """Pair the receiver of a method call with everything handed to it.

    ``H.append(subprocess.run)`` puts a reference into H, and so does
    ``H.update(k=subprocess.run)``. Telling a method that stores its argument
    from one that only reads it needs the type of the receiver, which this
    scan does not have, so every argument is treated as flowing in. The
    direction is safe: a name that takes on a value it never really holds is
    read too loudly, never too quietly.
    """
    if not isinstance(call.func, ast.Attribute):
        return []
    if not isinstance(call.func.value, ast.Name):
        return []
    name = call.func.value.id
    handed = [*call.args, *(keyword.value for keyword in call.keywords)]
    return [(name, value) for value in handed]


def _written(tree: ast.AST) -> set[str]:
    """Return every name whose object may change without receiving a value.

    A literal answers for a name only while the object it built is untouched,
    and most ways of touching one hand it something, so ``_bindings`` records
    them and the count rule retires the name. Two shapes hand over nothing.
    ``H.reverse()`` reorders in place, and no static scan can tell a method
    that mutates from one that reads without knowing the type, so every
    method call on a name counts. ``del H[0]`` drops an element and shifts
    the rest. Both leave the literal stale with no value to record, which is
    why they need a rule of their own.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                found.add(node.func.value.id)
        elif isinstance(node, ast.Delete):
            found.update(
                target.value.id
                for target in node.targets
                if isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
            )
    return found


def _class_walrus(statement: ast.stmt) -> list[tuple[str, ast.expr]]:
    """Pair every class attribute a walrus binds inside one statement.

    A walrus binds wherever it appears, not only where it stands alone as a
    statement, so ``if (runner := subprocess.run):`` in a class body sets a
    class attribute exactly as a plain assignment would. The walk stops at any
    node that opens a namespace of its own, because a walrus inside a nested
    function or class binds there rather than here.
    """
    found: list[tuple[str, ast.expr]] = []
    if isinstance(statement, _SCOPED):
        return found
    stack: list[ast.AST] = [statement]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            found.append((_ATTRIBUTE + node.target.id, node.value))
        stack.extend(
            child for child in ast.iter_child_nodes(node)
            if not isinstance(child, _SCOPED)
        )
    return found


def _class_bindings(node: ast.ClassDef) -> list[tuple[str, ast.expr]]:
    """Pair every attribute a class body binds with the value it receives.

    A class body binds attributes without ever naming ``self``, so the names
    are recorded under the attribute prefix and read back the same way. The
    walrus pass is additive rather than an arm of the same branch, because
    ``x = (runner := subprocess.run)`` binds two attributes at once.
    """
    found: list[tuple[str, ast.expr]] = []
    for statement in node.body:
        found.extend(_class_walrus(statement))
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            found.extend(
                (_ATTRIBUTE + name, bound)
                for name, bound in _unpack(target, statement.value)
            )
    return found


def _assigned(node: _Assign) -> list[tuple[str, ast.expr]]:
    """Pair the names an assignment statement writes with the value it writes.

    The four shapes differ only in where the target sits. An annotated
    assignment with no value declares a type and binds nothing, so it is the
    one shape that can come back empty.
    """
    if isinstance(node, ast.Assign):
        return [pair for target in node.targets for pair in _unpack(target, node.value)]
    if isinstance(node, ast.AnnAssign):
        if node.value is None:
            return []
        return _unpack(node.target, node.value)
    if isinstance(node, ast.NamedExpr):
        return [(node.target.id, node.value)]
    # ``H += [subprocess.run]`` rebinds H to something the first literal
    # never showed, with no assignment statement to find.
    return _unpack(node.target, node.value)


def _captured(node: ast.Match) -> list[tuple[str, ast.expr]]:
    """Pair every name a match statement captures with the subject it reads.

    Structural patterns name a capture in exactly three places: ``case r``
    and ``case P as r`` set ``MatchAs.name``, ``case [*rest]`` sets
    ``MatchStar.name``, and ``case {**rest}`` sets ``MatchMapping.rest``.
    Every other pattern is a shape holding those, so walking each case finds
    all of them. ``case _`` leaves the name unset and captures nothing.

    Which part of the subject a capture receives depends on the shape that
    matched, which is a runtime question, so each one is paired with the
    whole subject. That reads a sequence element as the whole sequence, and
    the direction is safe: too loud, never too quiet.
    """
    found: list[tuple[str, ast.expr]] = []
    for case in node.cases:
        for pattern in ast.walk(case.pattern):
            if isinstance(pattern, (ast.MatchAs, ast.MatchStar)):
                name = pattern.name
            elif isinstance(pattern, ast.MatchMapping):
                name = pattern.rest
            else:
                continue
            if name is not None:
                found.append((name, node.subject))
    return found


def _bindings(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    """Collect every ``name = value`` binding at any depth.

    Covers plain assignment, annotated assignment, the walrus, loop and
    comprehension targets, class bodies, match captures, values handed to a
    method, and default arguments, every one of which binds a name without an
    assignment statement to find.
    Assignment targets are unpacked, so a name bound by destructuring is as
    visible as one bound on its own.
    """
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, _Assign):
            found.extend(_assigned(node))
        elif isinstance(node, ast.Call):
            found.extend(_receives(node))
            found.extend(_installed(node))
        elif isinstance(node, ast.Match):
            found.extend(_captured(node))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            found.extend(_entered(node))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            # ``for runner in (subprocess.run,)`` binds a name with no
            # assignment statement anywhere in sight.
            found.extend(_iterated(node.target, node.iter))
        elif isinstance(node, ast.ClassDef):
            found.extend(_class_bindings(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            found.extend(_defaults(node.args))
    return found


def _containers(
    tree: ast.AST, bindings: list[tuple[str, ast.expr]]
) -> dict[str, _Container]:
    """Map each name bound once to an untouched literal container, to that literal.

    Two guarantees, and the literal is only worth reading when both hold.
    Bound exactly once: a second binding anywhere, including a loop target or
    a parameter default, means the name may hold something the literal does
    not show. Never written to: a subscript write, a delete, or any method
    call can change the object the literal built while the name stays put.
    Indexing a stale literal answers for the wrong object either way, so such
    names are left out and the caller falls back to tainting the container
    whole.
    """
    counts = Counter(name for name, _ in bindings)
    written = _written(tree)
    found: dict[str, _Container] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not isinstance(value, (ast.Dict, ast.List, ast.Tuple)):
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or target.id in written:
                continue
            if counts.get(target.id) == 1:
                found[target.id] = value
    return found


def _imports(tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
    """Collect the module aliases and imported names that reach a spawn point.

    ``import subprocess as sp``, ``import os as myos``, and
    ``from subprocess import run`` are all ordinary Python, and an owner-name
    check that only knows the literal words misses every one of them. Aliases
    map to the module they name rather than to a bare set, so ``os`` and
    ``subprocess`` cannot be confused for one another.
    """
    modules = {"subprocess": "subprocess", "os": "os"}
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TRACKED_MODULES:
                    modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            wanted = _IMPORTED_NAMES.get(node.module or "", {})
            for alias in node.names:
                if alias.name == "*":
                    # ``from subprocess import *`` binds every public name,
                    # entry points included, with none of them written down.
                    functions.update(wanted)
                elif alias.name in wanted:
                    functions[alias.asname or alias.name] = wanted[alias.name]
    return modules, functions


def _dependents(groups: dict[int, tuple[ast.expr, list[str]]]) -> dict[str, list[int]]:
    """Map each name a binding group reads to the groups that read it."""
    found: dict[str, list[int]] = {}
    for key, (value, _) in groups.items():
        for free in {
            node.id for node in ast.walk(value) if isinstance(node, ast.Name)
        }:
            found.setdefault(free, []).append(key)
    return found


def _rebound_modules(
    bindings: list[tuple[str, ast.expr]], modules: dict[str, str]
) -> dict[str, str]:
    """Grow *modules* with every name bound to a module already in it.

    ``sp = subprocess`` needs no import statement and leaves an owner name an
    import scan never sees. A chain of them settles because each pass can only
    add names, and there are finitely many.
    """
    grown = dict(modules)
    changed = True
    while changed:
        changed = False
        for name, value in bindings:
            if isinstance(value, ast.Name) and value.id in grown and name not in grown:
                grown[name] = grown[value.id]
                changed = True
    return grown


def _supplies_capture(
    call: ast.Call, modules: dict[str, str], functions: dict[str, str]
) -> bool:
    """Report whether *call* pre-binds the keywords that route output back."""
    capture = _keyword(call, "capture_output")
    if capture is not None and not _is_falsy_literal(capture):
        return True
    return _is_capturing_stream(
        _keyword(call, "stdout"), modules, functions
    ) or _is_capturing_stream(_keyword(call, "stderr"), modules, functions)


def _presupplied(
    bindings: list[tuple[str, ast.expr]],
    modules: dict[str, str],
    functions: dict[str, str],
) -> set[str]:
    """Name every callable whose capture keywords were fixed where it was built.

    ``partial(subprocess.run, capture_output=True)`` decides capture at the
    construction site, and the call site that adds ``text=True`` carries no
    capture keyword for :func:`_captures_text` to find. Without this the two
    halves of one decoding call read as compliant apart. An alias inherits the
    mark, because rebinding the name changes nothing about what it holds.
    """
    marked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, value in bindings:
            if name in marked:
                continue
            if isinstance(value, ast.Call) and _is_partial(
                _call_label(value), functions
            ):
                found = _supplies_capture(value, modules, functions)
            else:
                found = isinstance(value, ast.Name) and value.id in marked
            if found:
                marked.add(name)
                changed = True
    return marked


def _parameter_bindings(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    """Pair each function parameter with every value a call site hands it.

    Every other resolution arm reads a binding visible in the same scope as
    the use. A parameter is not: its value arrives from a call site elsewhere
    in the module. Pairing the parameter name with each argument feeds those
    values to the same fixpoint that resolves assignments, so a runner passed
    in resolves exactly as one assigned in would, including through a chain of
    definitions that forward it.

    The join is a union: any call site that hands a runner in makes the
    parameter a runner, because a parameter that is a runner at one call site
    and something else at another still decodes at runtime. Call sites are
    matched by name within the module only, so a function reached from another
    module or through a     reference is not covered. Call sites are indexed in the same walk that
    finds the definitions, because walking the tree once per definition is
    quadratic in a file that holds many of both.
    """
    definitions: dict[str, ast.arguments] = {}
    sites: dict[str, list[ast.Call]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            definitions.setdefault(node.name, node.args)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            sites.setdefault(node.func.id, []).append(node)

    found: list[tuple[str, ast.expr]] = []
    for name, spec in definitions.items():
        positional = [argument.arg for argument in spec.posonlyargs + spec.args]
        named = {
            argument.arg
            for argument in spec.posonlyargs + spec.args + spec.kwonlyargs
        }
        for site in sites.get(name, ()):
            found.extend(_matched(site, positional, named))
    return found


def _matched(
    site: ast.Call, positional: list[str], named: set[str]
) -> list[tuple[str, ast.expr]]:
    """Pair one call site's arguments with the parameters they land in."""
    found: list[tuple[str, ast.expr]] = []
    for index, argument in enumerate(site.args):
        if isinstance(argument, ast.Starred):
            # A splat fills an unknown run of slots, so every parameter it
            # could reach reads it, exactly as an unindexed container is read
            # whole elsewhere in this scan.
            found.extend((parameter, argument.value) for parameter in positional[index:])
            break
        if index < len(positional):
            found.append((positional[index], argument))
    for keyword in site.keywords:
        if keyword.arg is None:
            found.extend((parameter, keyword.value) for parameter in named)
        elif keyword.arg in named:
            found.append((keyword.arg, keyword.value))
    return found


def _subprocess_names(
    tree: ast.Module,
) -> tuple[dict[str, str], dict[str, str], dict[str, _Container], set[str]]:
    """Collect every name in *tree* that reaches a subprocess entry point.

    Imports seed the search, and every binding is then resolved against what
    is known so far. ``_run = subprocess.run`` needs no import statement at
    all, so the binding pass is what closes that shape.
    """
    modules, functions = _imports(tree)

    # Assignments resolve against names discovered so far, so one pass is not
    # enough: ``ast.walk`` is breadth first, so ``b = a`` at the top level is
    # visited before an ``a = subprocess.run`` nested in an ``if`` body, even
    # though the source reads the other way round.
    #
    # Rather than sweep every binding repeatedly, each one is queued again only
    # when a name it reads becomes known. A name resolves at most once, so the
    # queue takes at most one push per binding plus one per dependency edge,
    # which makes the work linear in the size of the file. A repeated sweep is
    # quadratic instead, and measurably so: a reverse-ordered chain of 2000
    # bindings took 0.41 seconds that way.
    # Bindings that share a value node are read together. A left side that
    # does not line up with the right side pairs every name with the whole of
    # it, so one node can be shared by thousands of names, and reading it once
    # per name is quadratic: 4000 names took 17.76 seconds that way. Every
    # name in a group reads the same node, so one read answers for all of them.
    bindings = _bindings(tree) + _parameter_bindings(tree)
    modules = _rebound_modules(bindings, modules)
    containers = _containers(tree, bindings)
    groups: dict[int, tuple[ast.expr, list[str]]] = {}
    for name, value in bindings:
        groups.setdefault(id(value), (value, []))[1].append(name)

    dependents = _dependents(groups)
    queue = list(groups)
    while queue:
        value, names = groups[queue.pop()]
        # A group whose names are all known has nothing left to learn, and
        # reading it again would walk the whole value for nothing. That walk
        # is what turns one value reading many names quadratic, because each
        # of those names resolving queues the group afresh: 4000 names took
        # 3.28 seconds that way.
        if all(name in functions for name in names):
            continue
        resolved = _resolve_callable(value, modules, functions, containers)
        if resolved is None:
            continue
        for name in names:
            # The first binding of a name wins. That is what bounds the queue,
            # and it is why a name rebound to an unrelated callable keeps
            # reading as a subprocess entry point.
            if name in functions:
                continue
            functions[name] = resolved
            queue.extend(dependents.get(name, ()))
    return modules, functions, containers, _presupplied(bindings, modules, functions)


def _target(
    call: ast.Call,
    modules: dict[str, str],
    functions: dict[str, str],
    containers: dict[str, _Container] | None = None,
) -> str | None:
    """Return the subprocess entry point *call* reaches, or ``None``."""
    direct = _resolve_callable(call.func, modules, functions, containers)
    if direct is not None:
        return direct
    # ``functools.partial(subprocess.run, text=True)`` decides the codec where
    # the partial is built, not where the result is finally called, so the
    # partial itself has to be treated as the subprocess call.
    fallback = _resolve_indirect(call, modules, functions)
    if fallback == _DYNAMIC:
        # A bare ``getattr(subprocess, name)`` only fetches. It decodes
        # nothing until something calls the result, and that call is the node
        # this scan flags instead.
        return None
    return fallback


def _positional_capture(
    call: ast.Call, modules: dict[str, str], functions: dict[str, str]
) -> bool:
    """Say whether a positional argument asks for a pipe.

    Capture can be requested without naming a parameter, and reading which
    slot holds it would pin this scan to one release's signature. Matching the
    sentinel by value instead asks the version-independent question: does any
    argument past the command name a pipe? The command itself is skipped
    because it is the one slot whose meaning never moves.
    """
    return any(
        _sentinel(argument, modules, functions) in _CAPTURE_SENTINELS
        for argument in call.args[1:]
    )


def _sentinel(
    node: ast.expr, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Name the subprocess constant an expression stands for, if any."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if modules.get(node.value.id) == "subprocess":
            return _IMPORTED_NAMES["subprocess"].get(node.attr)
        return None
    if isinstance(node, ast.Name):
        return functions.get(node.id)
    return None


def _captures_text(
    call: ast.Call,
    functions: dict[str, str],
    target: str,
    modules: dict[str, str],
    presupplied: set[str],
) -> bool:
    """Report whether *call* may decode captured output into ``str``.

    Deliberately conservative. Anything other than a literal ``False`` counts,
    because ``text=1`` and ``capture_output=flag`` both decode at runtime while
    reading as compliant to a check that only recognises ``True``.

    A ``functools.partial`` that selects text mode counts even with no capture
    keyword, because the capture can be supplied where the partial is called.
    So does an entry point in :data:`_ALWAYS_CAPTURING_ATTRS`, which captures
    without being asked, so *target* has to be known here rather than inferred
    from the spelling at the call site.

    A ``**kwargs`` splat is treated as text mode outright. The keywords it
    carries are not visible here, so ``text`` may be among them, and reading
    the absence of a literal keyword as proof of bytes mode is the hole an
    adversarial review walked through.
    """
    if _has_splat(call):
        return True
    if _positional_capture(call, modules, functions):
        # ``subprocess.run(cmd, -1, None, None, subprocess.PIPE, text=True)``
        # asks for a pipe without naming the parameter. Once capture arrives
        # positionally the mode flags sit in unread slots beside it, so text
        # mode cannot be ruled out and the decoding reading is the safe one.
        return True
    text = _keyword(call, "text")
    legacy = _keyword(call, "universal_newlines")
    if (text is None or _is_falsy_literal(text)) and (
        legacy is None or _is_falsy_literal(legacy)
    ):
        return False
    if _is_partial(_call_label(call), functions):
        # A partial can select text mode here and be handed capture_output at
        # the eventual call site, which this scan has no way to reach.
        return True
    if _call_label(call) in presupplied:
        # The mirror image: capture was fixed where the partial was built, so
        # this site adding text mode completes a decoding call between them.
        return True
    if target in _ALWAYS_CAPTURING_ATTRS:
        # The callee captures on its own behalf, so there is no capture
        # keyword for this scan to find and none is needed.
        return True
    capture = _keyword(call, "capture_output")
    if capture is not None and not _is_falsy_literal(capture):
        return True
    return _is_capturing_stream(_keyword(call, "stdout"), modules, functions) or (
        _is_capturing_stream(_keyword(call, "stderr"), modules, functions)
    )


def _is_capturing_stream(
    node: ast.expr | None, modules: dict[str, str], functions: dict[str, str]
) -> bool:
    """Report whether a ``stdout``/``stderr`` value routes output back here.

    Absent means inherit, and ``DEVNULL`` throws the stream away. Neither
    decodes anything, so neither can raise. Every other value is treated as a
    capture, including a file object, because whether its mode decodes is not
    visible to this scan and the loud reading is the safe one.
    """
    if node is None or _is_falsy_literal(node):
        return False
    if isinstance(node, ast.Attribute) and node.attr == "DEVNULL":
        return modules.get(node.value.id) != "subprocess" if (
            isinstance(node.value, ast.Name)
        ) else True
    if isinstance(node, ast.Name) and functions.get(node.id) == _DEVNULL:
        return False
    return True


def _pins_utf8(call: ast.Call) -> bool:
    """Report whether *call* proves its codec is UTF-8 at the call site.

    ``encoding=None`` is an explicit request for the locale codec, a name or
    attribute cannot be resolved statically, and ``utf-8-sig`` quietly strips a
    byte order mark, so only a string the parser can spell out counts.

    The spelling is normalised the way Python normalises it. ``UTF-8``,
    ``utf8``, ``UTF_8``, and ``u8`` all reach the same codec as ``utf-8``, so
    flagging them would be noise. ``utf-8-sig`` normalises to itself and stays
    excluded, and an unknown name raises, which leaves the call flagged.
    """
    encoding = _keyword(call, "encoding")
    if encoding is None:
        return False
    spelled = _constant_str(encoding)
    if spelled is None:
        return False
    try:
        return codecs.lookup(spelled).name == _PINNED_CODEC
    except LookupError:
        # A codec name Python cannot resolve raises at the first decode, so
        # the call is not pinned to anything and stays flagged.
        return False


def unpinned_lines(source: str) -> list[int]:
    """Return the line numbers of text-capturing calls that do not pin UTF-8."""
    tree = ast.parse(source)
    modules, functions, containers, presupplied = _subprocess_names(tree)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _target(node, modules, functions, containers)
        if target is None:
            continue
        if target == "os.popen":
            # os.popen has no encoding parameter at all, so the only compliant
            # move is to not use it.
            offenders.append(node.lineno)
            continue
        if target not in _DECODES_UNCONDITIONALLY and not _captures_text(
            node, functions, target, modules, presupplied
        ):
            continue
        if not _pins_utf8(node):
            offenders.append(node.lineno)
    return sorted(offenders)


def _python_sources() -> list[Path]:
    """Return every Python file under ``scripts/``, skipping caches."""
    return [
        path
        for path in sorted(_SCRIPTS_DIR.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def test_every_capturing_call_under_scripts_pins_utf8() -> None:
    """No text-capturing subprocess call may inherit the locale's codec."""
    offenders: list[str] = []
    for path in _python_sources():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        offenders.extend(f"{rel}:{line}" for line in unpinned_lines(path.read_text("utf-8")))
    assert offenders == [], (
        "text-capturing subprocess calls must pass encoding=\"utf-8\": "
        + ", ".join(offenders)
    )


def test_the_scan_actually_reaches_files() -> None:
    """Guard the guard: an empty file list would make the policy test vacuous."""
    sources = _python_sources()
    assert len(sources) > 50, f"only found {len(sources)} sources under scripts/"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=True)",
            "capture_output plus text",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], stdout=subprocess.PIPE, text=True)",
            "an explicit stdout pipe",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], text=True, stderr=None)",
            "check_output",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], text=True)",
            "check_output captures stdout with no capture keyword to read",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], universal_newlines=True)",
            "check_output under the legacy text spelling",
        ),
        (
            "from subprocess import check_output as co\nco(['x'], text=True)",
            "an alias of check_output captures just the same",
        ),
        (
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, universal_newlines=True)",
            "the legacy universal_newlines spelling",
        ),
    ],
)
def test_detector_flags_an_unpinned_call(source: str, why: str) -> None:
    """A detector that never fires would let the policy test pass on anything."""
    assert unpinned_lines(source) == [2], f"missed {why}"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "a pinned call is compliant",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True)',
            "no text means bytes, so nothing is decoded",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], text=True)',
            "nothing captured means nothing to decode",
        ),
        (
            'import subprocess\nsubprocess.check_output(["x"])',
            "check_output without text mode hands back bytes",
        ),
        (
            'import subprocess\nH = [subprocess.check_call, subprocess.run]\n'
            'H[0](["x"], capture_output=True, text=True)',
            "a table nobody writes to still reads one element",
        ),
        (
            'import subprocess\nH = [subprocess.check_call, subprocess.run]\n'
            'G = [subprocess.run]\nG[0] = subprocess.run\n'
            'H[0](["x"], capture_output=True, text=True)',
            "writing to one table does not cost another its precision",
        ),
        (
            'import subprocess\nsubprocess.check_output(["x"], text=True, encoding="utf-8")',
            "check_output that pins its codec is compliant",
        ),
        (
            'import subprocess\nsubprocess.Popen(["x"], text=True)',
            "Popen captures nothing unless the call site asks it to",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, text=False)',
            "text=False is an explicit bytes request",
        ),
        (
            'import shutil\nshutil.run(["x"], capture_output=True, text=True)',
            "a same-named method on another module is not ours",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], encoding="utf-8", **kw)',
            "a splat is harmless once the codec is pinned at the call site",
        ),
        (
            'import subprocess\n_run = subprocess.run\n'
            '_run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "an alias that pins the codec is exactly as safe as the original",
        ),
        (
            'import functools, subprocess\n'
            '_run = functools.partial(subprocess.run, text=True, encoding="utf-8")',
            "a partial that pins the codec has nothing left to decide",
        ),
        (
            'import functools, subprocess\n'
            '_popen = functools.partial(subprocess.Popen, stdout=subprocess.PIPE)',
            "a partial that never selects text mode returns bytes",
        ),
        (
            'import json\n_loads = json.loads\n_loads("{}")',
            "binding an unrelated callable is ordinary Python",
        ),
        (
            'import subprocess\nrunners = [subprocess.run, subprocess.Popen]\n'
            'runners[0](["echo", "hi"])',
            "two entry points that both need keywords decode nothing without one",
        ),
        (
            'import subprocess\nclass C:\n    def __init__(self):\n'
            '        self.run = subprocess.run\n'
            'C().run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "an attribute that pins the codec is as safe as a name that does",
        ),
        (
            'import json\nclass C:\n    def __init__(self):\n'
            '        self.load = json.loads\n'
            'C().load("{}", capture_output=True, text=True)',
            "an attribute holding an unrelated callable is ordinary Python",
        ),
        (
            'import subprocess\ndef go(runner=subprocess.run):\n'
            '    runner(["x"], capture_output=True, text=True, encoding="utf-8")',
            "a default argument that pins the codec needs no second look",
        ),
        (
            'import subprocess\nfrom mylib import render\n'
            'runner, drawer = subprocess.run, render\n'
            'drawer("x", capture_output=True, text=True)',
            "unpacking pairs by position, so the neighbour keeps its own identity",
        ),
        (
            'import subprocess\nrunners = [subprocess.run, subprocess.Popen]\n'
            'runners[0](["x"], capture_output=True, text=True, encoding="utf-8")',
            "a container call that pins the codec is as safe as a direct one",
        ),
        (
            'from functools import partial as p\n'
            'x = p(open, "f")\nx()',
            "a partial over an unrelated callable is not a subprocess call",
        ),
        (
            'from functools import partial as p\n'
            'q = p\nq(open, "f")()',
            "the alias itself is functools.partial, not a subprocess entry point",
        ),
        (
            'from functools import partial as p\n'
            'def fetch(cmd, text=False):\n    return cmd\n'
            'go = p(fetch, text=True)\ngo(["x"])',
            "a partial over a local function that takes text is not subprocess",
        ),
        (
            'import shutil\n_run = shutil.run\n'
            '_run(["x"], capture_output=True, text=True)',
            "an alias of a same-named function on another module is not ours",
        ),
        (
            'from mypackage import run, getoutput\n'
            'run(["x"], capture_output=True, text=True)\ngetoutput("x")',
            "a from-import of a same-named function elsewhere is not ours",
        ),
        (
            'import subprocess\n'
            'getattr(subprocess, "PIPE")\n'
            'getattr(shutil, "run")(["x"], capture_output=True, text=True)',
            "getattr only counts when it names our module and our function",
        ),
        (
            'import subprocess\nname = "run"\n'
            'getattr(subprocess, name)(["x"], capture_output=True, encoding="utf-8")',
            "a dynamic lookup that still pins the codec decodes correctly",
        ),
        (
            'import subprocess\nname = "run"\nf = getattr(subprocess, name)',
            "fetching an attribute decodes nothing until something calls it",
        ),
        (
            'import subprocess\nH = {"run": subprocess.run, "build": local}\n'
            'H["build"](["x"], capture_output=True, text=True)',
            "a literal key selects one handler, and this one is not an entry point",
        ),
        (
            'import subprocess\nR = [local, subprocess.run]\n'
            'R[0](["x"], capture_output=True, text=True)',
            "a literal index selects one element, and this one is not an entry point",
        ),
        (
            'import subprocess\nR = [subprocess.run, local]\n'
            'R[-1](["x"], capture_output=True, text=True)',
            "a negative index counts from the end of the literal",
        ),
        (
            'import subprocess\nH = {"a": local, "b": subprocess.run}\n'
            '(f := H["a"])(["x"], capture_output=True, text=True)',
            "a walrus over an indexed table still selects the one element",
        ),
        (
            'import subprocess\nH: object = [subprocess.check_call, subprocess.run]\n'
            'H: object\n'
            'H[0](["x"], capture_output=True, text=True)',
            "a bare annotation declares a type and binds nothing",
        ),
        (
            "import subprocess\nH = [[subprocess.check_call]]\ndel H[0][1]\n"
            'H[0](["x"], capture_output=True, text=True)',
            "a delete may reach through a subscript the scan cannot name",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n    case _:\n'
            '        _(["x"], capture_output=True, text=True)',
            "a wildcard pattern matches everything and captures nothing",
        ),
        (
            'import subprocess\nmatch subprocess.check_call:\n    case runner:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "a capture is only as loud as the subject it reads",
        ),
        (
            'import subprocess\n'
            'for label, runner in [(subprocess.check_call, subprocess.run)]:\n'
            '    label(["x"], capture_output=True, text=True)',
            "a loop target takes one column of the pairs, not both",
        ),
        (
            'import subprocess\n'
            'for label, runner in ((subprocess.check_call, 1), (subprocess.run, 2)):\n'
            '    runner(["x"], capture_output=True, text=True)',
            "the second column of every pair is what the second name reads",
        ),
        (
            'import subprocess\n'
            'for label, runner in {(subprocess.check_call, subprocess.run)}:\n'
            '    label(["x"], capture_output=True, text=True)',
            "a set literal of pairs still has columns",
        ),
        (
            'import subprocess\n'
            'runner = other = subprocess.check_output\n'
            'runner = subprocess.run\n'
            'runner(["x"], text=True)',
            "the first binding of a name wins over a later group it shares",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["ls"], capture_output=True, text=True, encoding=f"utf-8")',
            "an f-string with no placeholder reaches the runtime as the same codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, '
            'encoding="utf" + "-8")',
            "a concatenation of literals reaches the runtime as the same codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["ls"], capture_output=0, text=True)',
            "subprocess tests capture_output for truth, and zero is false",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], stdout=subprocess.DEVNULL, text=True)',
            "DEVNULL throws the stream away, so nothing is decoded",
        ),
        (
            'import subprocess\n'
            'from subprocess import DEVNULL\n'
            'subprocess.run(["x"], stderr=DEVNULL, text=True)',
            "an imported DEVNULL is the same null sink under a shorter name",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="UTF-8")',
            "codec names are case folded before they reach a codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf8")',
            "utf8 resolves to the same codec as utf-8",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="UTF_8")',
            "an underscore spelling resolves to the same codec",
        ),
        (
            'import subprocess\n'
            'r = subprocess.run.__get__\n'
            'r(["x"], capture_output=True, text=True)',
            "__get__ returns a binding rather than the callable it was read from",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], stdout=None, text=True)',
            "an explicit stdout of None inherits the handle and decodes nothing",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], stderr=None, text=True)',
            "an explicit stderr of None inherits the handle and decodes nothing",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=None, text=True)',
            "subprocess tests capture_output for truth, and None is false",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], check=True)',
            "one positional argument is the command, and nothing here decodes",
        ),
        (
            'import subprocess\n'
            'runner = {}.get("run", subprocess.run)\n'
            'runner(["x"], -1)',
            "a lookup that merely fetches a reference is not a spawn point",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    def make(self):\n'
            '        return (runner := subprocess.run)\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus inside a method binds a local, never a class attribute",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    make = lambda self: (runner := subprocess.run)\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus inside a lambda binds there, not in the class body",
        ),
        (
            'import subprocess\n'
            'import mymod\n'
            'subprocess.run(["x"], -1, None, None, mymod.PIPE)',
            "a pipe sentinel belongs to subprocess, not to any module spelling it",
        ),
        (
            'import subprocess\n'
            'subprocess.run(subprocess.PIPE)',
            "the command slot holds what to run, so a sentinel there captures nothing",
        ),
        (
            'def go(runner):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go(print)',
            "a parameter that never receives a runner starts no process",
        ),
        (
            'import subprocess\n'
            'def go(runner):\n'
            '    runner(["x"], capture_output=True, text=True, encoding="utf-8")\n'
            'go(subprocess.run)',
            "a runner handed in is still pinned by the call site that uses it",
        ),
    ],
)
def test_detector_stays_quiet(source: str, why: str) -> None:
    """The guard must not fire on calls that decode nothing."""
    assert unpinned_lines(source) == [], f"false positive on {why}"


def test_detector_reports_every_offender_in_one_file() -> None:
    """A file with several bad calls must surface all of them, not just the first."""
    source = (
        "import subprocess\n"
        "subprocess.run(['a'], capture_output=True, text=True)\n"
        'subprocess.run(["b"], capture_output=True, text=True, encoding="utf-8")\n'
        "subprocess.run(['c'], capture_output=True, text=True)\n"
    )
    assert unpinned_lines(source) == [2, 4]


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding=None)',
            "encoding=None is an explicit request for the locale codec",
        ),
        (
            'from subprocess import run\nrun(["x"], capture_output=True, text=True)',
            "a direct import evades an owner-name check",
        ),
        (
            'import subprocess as sp\nsp.run(["x"], capture_output=True, text=True)',
            "a module alias evades an owner-name check",
        ),
        (
            'from subprocess import check_output as co\nco(["x"], text=True, stdout=1)',
            "a renamed import evades a function-name check",
        ),
        (
            'import subprocess\nsubprocess.getoutput("x")',
            "getoutput always decodes and defaults to encoding=None",
        ),
        (
            'import subprocess\nsubprocess.getstatusoutput("x")',
            "getstatusoutput has the same default",
        ),
        (
            'import os\nos.popen("x")',
            "os.popen decodes with no way to pin a codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf-8-sig")',
            "utf-8-sig silently strips a BOM, so it is not the pinned codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding=CODEC)',
            "a non-literal encoding cannot be proven to be utf-8",
        ),
        (
            'import subprocess\ncapture = True\n'
            'subprocess.run(["x"], capture_output=capture, text=True)',
            "a variable capture flag still captures",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, text=1)',
            "a truthy non-True literal still selects text mode",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, text=True, **kw)',
            "splatted keywords cannot prove the codec is pinned",
        ),
        (
            'import subprocess\nkw = {"text": True}\n'
            'subprocess.run(["x"], capture_output=True, **kw)',
            "a splat can supply text= with no literal keyword to read",
        ),
        (
            'import subprocess\nkw = {"text": True, "capture_output": True}\n'
            'subprocess.run(["x"], **kw)',
            "a splat can supply every decoding keyword at once",
        ),
        (
            'import subprocess\nkw = {"text": True}\n'
            'subprocess.check_output(["x"], **kw)',
            "the splat hole is not specific to run",
        ),
        (
            'import subprocess\n_run = subprocess.run\n'
            '_run(["x"], capture_output=True, text=True)',
            "a plain assignment rebinds run without any import to read",
        ),
        (
            'import subprocess\na = subprocess.run\nb = a\n'
            'b(["x"], capture_output=True, text=True)',
            "an alias of an alias still reaches run",
        ),
        (
            'from subprocess import run\n_r = run\n'
            '_r(["x"], capture_output=True, text=True)',
            "a directly imported name can be rebound too",
        ),
        (
            'import subprocess\nfrom typing import Any\n'
            '_run: Any = subprocess.run\n'
            '_run(["x"], capture_output=True, text=True)',
            "an annotated assignment binds exactly like a plain one",
        ),
        (
            'import subprocess\ndef f():\n    r = subprocess.run\n'
            '    return r(["x"], capture_output=True, text=True)',
            "a binding inside a function body is just as reachable",
        ),
        (
            'import functools, subprocess\n'
            '_run = functools.partial(subprocess.run, text=True)\n'
            '_run(["x"], capture_output=True)',
            "partial pins text mode at the partial, not at the call",
        ),
        (
            'import subprocess\n'
            'getattr(subprocess, "run")(["x"], capture_output=True, text=True)',
            "getattr with a literal name is still a static reference",
        ),
        (
            'import os\np = os.popen\np("x").read()',
            "os.popen can be rebound as readily as run",
        ),
        (
            'import subprocess\nname = "run"\n'
            'getattr(subprocess, name)(["x"], capture_output=True, text=True)',
            "a computed attribute name still reaches a subprocess entry point",
        ),
        (
            'import subprocess\nname = "getoutput"\n'
            'getattr(subprocess, name)("ls")',
            "a computed name can land on getoutput, which decodes with no flag",
        ),
        (
            'import subprocess\nname = "getoutput"\n'
            'f = getattr(subprocess, name)\nf("ls")',
            "binding a computed lookup defers the decode, it does not avoid it",
        ),
        (
            'import subprocess\nif True:\n    a = subprocess.run\n'
            'b = a\nb(["x"], capture_output=True, text=True)',
            "a nested binding is walked after the top-level one that uses it",
        ),
        (
            'import subprocess\n'
            '(r := subprocess.run)(["x"], capture_output=True, text=True)',
            "a walrus binds and calls in one expression",
        ),
        (
            'import subprocess\nif (r := subprocess.run):\n    pass\n'
            'r(["x"], capture_output=True, text=True)',
            "a name bound by a walrus is still bound at the later call",
        ),
        (
            'import subprocess\nRUNNERS = [subprocess.run]\n'
            'RUNNERS[0](["x"], capture_output=True, text=True)',
            "a list can hold the entry point as readily as a bare name",
        ),
        (
            'import subprocess\nR = {"go": subprocess.run}\n'
            'R["go"](["x"], capture_output=True, text=True)',
            "a dict value is reached by subscript, not by attribute",
        ),
        (
            'import subprocess\nH = {"go": subprocess.run}\nk = "go"\n'
            'H[k](["x"], capture_output=True, text=True)',
            "a computed key names no element the scan can read, so all of them count",
        ),
        (
            'import subprocess\nH = {"go": subprocess.run}\n'
            'H["absent"](["x"], capture_output=True, text=True)',
            "a key that is not in the literal says nothing about what is",
        ),
        (
            'import subprocess\nH = {1: local, "go": subprocess.run}\n'
            'H[True](["x"], capture_output=True, text=True)',
            "True equals 1 in Python but names no key a dict was written with",
        ),
        (
            'import subprocess\nbase = {"safe": subprocess.run}\n'
            'H = {**base, "safe": local}\n'
            'H["safe"](["x"], capture_output=True, text=True)',
            "a mapping splat can carry an entry point under any key",
        ),
        (
            'import subprocess\nR = [*others, subprocess.run]\n'
            'R[0](["x"], capture_output=True, text=True)',
            "a starred element shifts every index after it",
        ),
        (
            'import subprocess\nR = [local, subprocess.run]\n'
            'R[7](["x"], capture_output=True, text=True)',
            "an index past the end of the literal reads nothing from it",
        ),
        (
            'import subprocess\nR = [local, subprocess.run]\n'
            'R[0:1][0](["x"], capture_output=True, text=True)',
            "a slice yields a container the scan did not build",
        ),
        (
            'import subprocess\nH = {"safe": subprocess.run}\n'
            'H = {"safe": local}\n'
            'H["safe"](["x"], capture_output=True, text=True)',
            "a name bound twice names no one literal the scan can index",
        ),
        (
            'import subprocess\nR = (subprocess.getoutput,)\n'
            'R[0]("ls")',
            "a tuple element that always decodes needs no text keyword",
        ),
        (
            'import subprocess\nR = [subprocess.Popen, subprocess.getoutput]\n'
            'R[1]("ls")',
            "a mixed container may yield the member that decodes regardless",
        ),
        (
            'import subprocess\nfrom functools import partial as p\n'
            'f = p(subprocess.run, text=True)\nf(["x"], capture_output=True)',
            "an aliased partial import is not spelled partial at the call",
        ),
        (
            'import subprocess\na, b = subprocess.run, None\n'
            'a(["x"], capture_output=True, text=True)',
            "tuple unpacking binds a name without an ast.Name target",
        ),
        (
            'import subprocess\n(a, (b, c)) = (None, (subprocess.run, None))\n'
            'b(["x"], capture_output=True, text=True)',
            "a nested unpacking target is still a binding",
        ),
        (
            'import subprocess\n*runners, tail = subprocess.run, None\n'
            'runners[0](["x"], capture_output=True, text=True)',
            "a starred target collects the reference into a container",
        ),
        (
            'import subprocess\nrunners = [subprocess.run, subprocess.run]\n'
            'a, b = runners\na(["x"], capture_output=True, text=True)',
            "unpacking a name of unknown shape may hand it to either side",
        ),
        (
            'import subprocess\nrunners = [subprocess.run, subprocess.run]\n'
            'a, b = runners\nb(["x"], capture_output=True, text=True)',
            "every name on the left of an unknown shape carries the same answer",
        ),
        (
            'import subprocess\nclass C:\n    def __init__(self):\n'
            '        self.run = subprocess.run\n'
            'C().run(["x"], capture_output=True, text=True)',
            "an entry point parked on an attribute is reached through the object",
        ),
        (
            'import subprocess\nclass C:\n    run = subprocess.run\n'
            'C.run(["x"], capture_output=True, text=True)',
            "a class body binds an attribute without ever naming self",
        ),
        (
            'import subprocess\nfor runner in (subprocess.run,):\n'
            '    runner(["x"], capture_output=True, text=True)',
            "a loop target is a binding with no assignment statement",
        ),
        (
            'import subprocess\ndef go(runner=subprocess.run):\n'
            '    runner(["x"], capture_output=True, text=True)',
            "a default argument binds the name once, at definition time",
        ),
        (
            'import subprocess\ndef go(cmd, runner=subprocess.run):\n'
            '    runner(cmd, capture_output=True, text=True)',
            "defaults fill the tail of the parameter list, not the head",
        ),
        (
            'import subprocess\ndef go(*, runner=subprocess.run):\n'
            '    runner(["x"], capture_output=True, text=True)',
            "a keyword-only parameter carries its default in a separate list",
        ),
        (
            'import subprocess\ndef go():\n'
            '    return [r(["x"], capture_output=True, text=True) '
            'for r in (subprocess.run,)]',
            "a comprehension target binds inside its own scope",
        ),
        (
            'import subprocess\nrunners = [subprocess.run, subprocess.Popen]\n'
            'runners[0](["x"], capture_output=True, text=True)',
            "members that share a keyword contract still honour that contract",
        ),
        (
            'import subprocess, os\nrunners = [subprocess.check_output, os.popen]\n'
            'runners[1]("ls")',
            "a container holding os.popen may yield the one that cannot pin",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\n"
            "H[0] = subprocess.run\nH[0](['x'], capture_output=True, text=True)",
            "a list written through a subscript no longer matches its literal",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\n"
            "H.append(subprocess.run)\nH[0](['x'], capture_output=True, text=True)",
            "a list appended to no longer matches its literal",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\n"
            "H += [subprocess.run]\nH[0](['x'], capture_output=True, text=True)",
            "augmented assignment rebinds a name with no assignment in sight",
        ),
        (
            "import subprocess\nH = {'a': subprocess.check_call}\n"
            "H['b'] = subprocess.run\nH['a'](['x'], capture_output=True, text=True)",
            "a mapping written through a key no longer matches its literal",
        ),
        (
            "import subprocess\nH = {'a': subprocess.check_call}\n"
            "H.update(b=subprocess.run)\nH['a'](['x'], capture_output=True, text=True)",
            "a mapping updated by keyword no longer matches its literal",
        ),
        (
            "import subprocess\nH = [subprocess.check_call, subprocess.run]\n"
            "del H[0]\nH[0](['x'], capture_output=True, text=True)",
            "deleting an element shifts every index after it",
        ),
        (
            "import subprocess\nH = [subprocess.check_call, subprocess.run]\n"
            "H.reverse()\nH[0](['x'], capture_output=True, text=True)",
            "a method that takes no arguments can still reorder the container",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\n"
            "H[0], y = subprocess.run, 1\nH[0](['x'], capture_output=True, text=True)",
            "a subscript inside a tuple target writes just the same",
        ),
        (
            "import subprocess\nb = c = a\na = subprocess.run\n"
            "b = subprocess.check_output\n"
            'c(["x"], capture_output=True, text=True)',
            "one name of a shared binding resolving does not answer for the rest",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n    case runner:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "a bare match case captures the subject under a new name",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n'
            '    case object() as runner:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "an as-pattern captures under a name too",
        ),
        (
            'import subprocess\nmatch [subprocess.run]:\n    case [*rest]:\n'
            '        rest[0](["x"], capture_output=True, text=True)',
            "a star pattern collects the subject into a new container",
        ),
        (
            'import subprocess\nmatch {"k": subprocess.run}:\n'
            '    case {**rest}:\n'
            '        rest["k"](["x"], capture_output=True, text=True)',
            "a mapping rest pattern captures what the other keys left",
        ),
        (
            'import subprocess\nmatch [subprocess.run]:\n    case [runner]:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "a sequence pattern captures an element by position",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n'
            '    case runner if runner:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "a guarded case still captures before the guard runs",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n'
            '    case object(__doc__=held):\n'
            '        held(["x"], capture_output=True, text=True)',
            "a class pattern captures through a keyword",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n    case [] | runner:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "an or-pattern captures in whichever alternative matches",
        ),
        (
            'import subprocess\nmatch subprocess.run:\n    case []:\n'
            '        pass\n    case runner:\n'
            '        runner(["x"], capture_output=True, text=True)',
            "a later case captures just as much as the first",
        ),
        (
            'import subprocess\nheld = [subprocess.run]\n'
            'for runner in held:\n'
            '    runner(["x"], capture_output=True, text=True)',
            "an opaque iterable still resolves through its own binding",
        ),
        (
            'import subprocess\n'
            'for runner in [subprocess.check_call, subprocess.run]:\n'
            '    runner(["x"], capture_output=True, text=True)',
            "every item of the iterable is a value the name can take",
        ),
        (
            'import subprocess\n'
            'def go(runner=subprocess.run, /):\n'
            '    runner(["x"], capture_output=True, text=True)',
            "a positional-only parameter takes a default like any other",
        ),
        (
            'import functools, subprocess\n'
            'run_cmd = functools.partial(subprocess.run, capture_output=True)\n'
            'run_cmd(["ls"], text=True)',
            "a partial fixes capture where it is built and text where it is called",
        ),
        (
            'from functools import partial\n'
            'import subprocess\n'
            'capturing = partial(subprocess.run, capture_output=True)\n'
            'alias = capturing\n'
            'alias(["x"], text=True)',
            "an alias inherits the capture its partial already fixed",
        ),
        (
            'import subprocess\n'
            '(*[subprocess.run],)[0](["ls"], capture_output=True, text=True)',
            "a starred element spreads into the container it is read from",
        ),
        (
            'import subprocess\n'
            'f = lambda r=subprocess.run: r(["ls"], capture_output=True, text=True)',
            "a lambda takes a default like any other callable",
        ),
        (
            'import subprocess\n'
            'sp = subprocess\n'
            'sp.run(["x"], capture_output=True, text=True)',
            "a module rebound by assignment leaves no import to read",
        ),
        (
            'from subprocess import *\n'
            'run(["x"], capture_output=True, text=True)',
            "a star import binds every entry point and names none of them",
        ),
        (
            'import subprocess\n'
            'runner = {"run": subprocess.run}.get("run")\n'
            'runner(["x"], capture_output=True, text=True)',
            "get selects an element exactly as a subscript does",
        ),
        (
            'import subprocess\n'
            'runners = {}\n'
            'runners.setdefault("run", subprocess.run)(["x"], capture_output=True, text=True)',
            "the fallback of setdefault is a path to a value the receiver lacks",
        ),
        (
            'import subprocess\n'
            '{}.get("run", subprocess.run)(["x"], capture_output=True, text=True)',
            "the fallback of get is a path to a value the receiver lacks",
        ),
        (
            'import subprocess\n'
            'runner = min([subprocess.run])\n'
            'runner(["x"], capture_output=True, text=True)',
            "a builtin that selects from a container yields what it held",
        ),
        (
            'import subprocess\n'
            '([subprocess.run] + [print])[0](["x"], capture_output=True, text=True)',
            "concatenation builds a container holding what either side held",
        ),
        (
            'import subprocess\n'
            '([subprocess.run] * 2)[0](["x"], capture_output=True, text=True)',
            "repetition builds a container holding what the left side held",
        ),
        (
            'import subprocess\n'
            'from contextlib import nullcontext\n'
            'with nullcontext(subprocess.run) as runner:\n'
            '    runner(["x"], capture_output=True, text=True)',
            "a with target binds a name with no assignment statement in sight",
        ),
        (
            'import subprocess\n'
            'from contextlib import nullcontext, ExitStack\n'
            'with ExitStack() as stack:\n'
            '    runner = stack.enter_context(nullcontext(subprocess.run))\n'
            '    runner(["x"], capture_output=True, text=True)',
            "enter_context hands back the object it was given",
        ),
        (
            'import subprocess\n'
            'class Holder: pass\n'
            'holder = Holder()\n'
            'setattr(holder, "runner", subprocess.run)\n'
            'holder.runner(["x"], capture_output=True, text=True)',
            "setattr is an attribute assignment spelled as a call",
        ),
        (
            'import subprocess\n'
            'globals()["runner"] = subprocess.run\n'
            'runner(["x"], capture_output=True, text=True)',
            "a globals write binds a name absent from the left of the assignment",
        ),
        (
            'import subprocess\n'
            'runner = staticmethod(subprocess.run)\n'
            'runner(["x"], capture_output=True, text=True)',
            "staticmethod hands the reference straight back out",
        ),
        (
            'from os import popen\n'
            'popen("x").read()',
            "os.popen has no encoding parameter under any spelling",
        ),
        (
            'from os import popen as p\n'
            'p("x").read()',
            "an aliased popen import is the same unpinnable call",
        ),
        (
            'import os as myos\n'
            'myos.popen("x").read()',
            "an aliased os module still owns popen",
        ),
        (
            'import os\n'
            'getattr(os, "popen")("x").read()',
            "getattr reaches popen as directly as an attribute does",
        ),
        (
            'import os\n'
            'name = "popen"\n'
            'getattr(os, name)("x").read()',
            "a computed attribute on a tracked module may name popen",
        ),
        (
            'import subprocess\n'
            'flag = 1\n'
            'r = subprocess.run if flag else None\n'
            'r(["x"], capture_output=True, text=True)',
            "a conditional expression makes both branches values the name takes",
        ),
        (
            'import subprocess\n'
            'cached = None\n'
            'r = cached or subprocess.run\n'
            'r(["x"], capture_output=True, text=True)',
            "a boolean fallback makes either operand a value the name takes",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, '
            'encoding="not-a-codec")',
            "a codec name Python cannot resolve pins nothing",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, '
            'encoding="utf-8-sig")',
            "utf-8-sig normalises to itself and strips a byte order mark",
        ),
        (
            'import subprocess\n'
            'subprocess.run.__call__(["x"], capture_output=True, text=True)',
            "__call__ hands back the callable it is read from",
        ),
        (
            'import subprocess as sp\n'
            'sp.run.__call__(["x"], capture_output=True, text=True)',
            "a forwarding attribute survives a module alias",
        ),
        (
            'import subprocess\n'
            'r = subprocess.run\n'
            'r.__call__(["x"], capture_output=True, text=True)',
            "a forwarding attribute survives a bound name",
        ),
        (
            'import os\n'
            'os.popen.__call__("x").read()',
            "a forwarding attribute reaches popen too",
        ),
        (
            'from os import popen\n'
            'popen.__call__("x").read()',
            "a forwarding attribute reaches an imported popen",
        ),
        (
            'import subprocess\n'
            'subprocess.run.__func__(["x"], capture_output=True, text=True)',
            "__func__ hands back the same callable",
        ),
        (
            'import subprocess\n'
            'subprocess.run.__wrapped__(["x"], capture_output=True, text=True)',
            "__wrapped__ hands back the same callable",
        ),
        (
            'import subprocess\n'
            'getattr(subprocess.run, "__call__")(["x"], capture_output=True, text=True)',
            "getattr composed with a forwarding attribute reaches the callable",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], -1, None, None, subprocess.PIPE, text=True)',
            "capture selected by position leaves no keyword to read",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], -1, None, None, subprocess.PIPE, None, None, '
            'True, False, None, None, True)',
            "text mode selected by position leaves no keyword to read",
        ),
        (
            'import subprocess\n'
            'next(r for r in [subprocess.run])(["x"], capture_output=True, text=True)',
            "a generator yields whatever its element expression evaluates to",
        ),
        (
            'import subprocess\n'
            '[r for r in [subprocess.run]][0](["x"], capture_output=True, text=True)',
            "a list comprehension yields its element expression",
        ),
        (
            'import subprocess\n'
            '{r for r in [subprocess.run]}.pop()(["x"], capture_output=True, text=True)',
            "a set comprehension yields its element expression",
        ),
        (
            'import subprocess\n'
            '{k: subprocess.run for k in "a"}["a"](["x"], capture_output=True, text=True)',
            "a dict comprehension yields its value expression",
        ),
        (
            'import subprocess\n'
            'list(r for r in [subprocess.run])[0](["x"], capture_output=True, text=True)',
            "list rebuilds a container holding the same elements",
        ),
        (
            'import subprocess\n'
            'runner = None or subprocess.run\n'
            'runner(["x"], capture_output=True, text=True)',
            "a boolean fallback resolves through its own binding",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    if (runner := subprocess.run):\n'
            '        pass\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a class-body walrus binds an attribute from a test position",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    print(runner := subprocess.run)\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a class-body walrus binds an attribute from an argument position",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    assert (runner := subprocess.run)\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a class-body walrus binds an attribute from an assert",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    ok = True and (runner := subprocess.run)\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a class-body walrus binds beside the assignment it sits inside",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    t = ((runner := subprocess.run), 1)\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a class-body walrus binds from inside a container literal",
        ),
        (
            'import subprocess\n'
            'class C:\n'
            '    assert (outer := (runner := subprocess.run))\n'
            'C.runner(["x"], capture_output=True, text=True)',
            "a nested class-body walrus binds every name it writes",
        ),
        (
            'import subprocess\n'
            'import mymod\n'
            'subprocess.run(["x"], stdout=mymod.DEVNULL, text=True)',
            "only subprocess owns the null sink, so a lookalike is a real stream",
        ),
        (
            'import subprocess\n'
            'def go(runner):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go(subprocess.run)',
            "a runner handed in positionally decodes inside the body it reaches",
        ),
        (
            'import subprocess\n'
            'def go(runner=None):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go(runner=subprocess.run)',
            "a runner handed in by keyword lands in the parameter of that name",
        ),
        (
            'import subprocess\n'
            'def go(runner=subprocess.run):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go()',
            "a default is the value the parameter takes when a call site omits it",
        ),
        (
            'import subprocess\n'
            'def go(*, runner):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go(runner=subprocess.run)',
            "a keyword-only parameter receives a runner like any other",
        ),
        (
            'import subprocess\n'
            'args = (None, subprocess.run)\n'
            'def go(first, runner):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go(*args)',
            "a splat fills an unknown run of slots, so every one of them reads it",
        ),
        (
            'import subprocess\n'
            'kw = {"runner": subprocess.run}\n'
            'def go(runner):\n'
            '    runner(["x"], capture_output=True, text=True)\n'
            'go(**kw)',
            "a keyword splat may name any parameter, so every one of them reads it",
        ),
        (
            'import subprocess\n'
            'def inner(r):\n'
            '    r(["x"], capture_output=True, text=True)\n'
            'def outer(runner):\n'
            '    inner(runner)\n'
            'outer(subprocess.run)',
            "a runner forwarded through a second definition still arrives",
        ),
    ],
)
def test_detector_closes_the_evasions(source: str, why: str) -> None:
    """Holes found by adversarial review. Each one decodes under the locale codec."""
    assert unpinned_lines(source) != [], f"missed {why}"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess, sys\n'
            'subprocess.run(["x"], stdout=sys.stdout, text=True)',
            "a redirect that is not a pipe leaves the parent nothing to decode",
        ),
        (
            'import subprocess\na = subprocess.run\n'
            'a = lambda *args, **kwargs: None\n'
            'a(["x"], capture_output=True, text=True)',
            "the later binding wins at runtime, but not in a flow-blind scan",
        ),
        (
            'import subprocess\nkwargs = {}\n'
            'subprocess.run(["x"], **kwargs)',
            "an empty splat carries no text keyword and returns bytes",
        ),
        (
            'import subprocess\nclass C:\n    def __init__(self):\n'
            '        self.run = subprocess.run\n'
            'def go(parser):\n'
            '    parser.run(["x"], capture_output=True, text=True)',
            "an unrelated object with a same-named method reads as the one bound",
        ),
        (
            'import subprocess\n'
            'held = [subprocess.run, subprocess.check_call]\n'
            'held[True](["x"], capture_output=True, text=True)',
            "a bool index is a valid int index, and reading it as one is a guess",
        ),
        (
            'import subprocess\n'
            'def read():\n'
            '    held = [subprocess.check_call]\n'
            '    held[0](["x"], capture_output=True, text=True)\n'
            'def write():\n'
            '    held = [subprocess.run]\n'
            '    held[0](["x"], capture_output=True, text=True)',
            "one name bound in two scopes reads as one name bound twice",
        ),
    ],
)
def test_detector_over_approximates_deliberately(source: str, why: str) -> None:
    """Known false positives, kept on purpose and recorded here as decisions.

    Each costs a redundant ``encoding="utf-8"`` on a call that decodes nothing.
    Each precise alternative costs a missed decode, which is the failure this
    file exists to prevent:

    Reading the redirect would mean resolving the keyword's value, and an alias
    or a computed mode defeats that, so ``stdout=PIPE`` would slip through.
    Letting the last binding win would mean ordering the bindings, which
    ``ast.walk`` does not give, so a rebinding nested in a branch would decide
    the answer for code that never runs it. Reading an absent keyword inside a
    splat as proof of bytes mode is the exact hole an adversarial review walked
    through. Deciding which object an attribute hangs off would mean tracking
    types, and a wrapper that stores an entry point on ``self`` is the very
    shape a review executed against this scan, so the attribute name alone has
    to carry the binding. Reading ``held[True]`` as ``held[1]`` would mean
    trusting that a bool index was meant as the int it equals, and a dispatch
    table keyed on flags would then answer for the wrong branch. Telling two
    ``held`` bindings apart would mean tracking scopes, and a name that a
    nested function closes over belongs to neither scope alone, so one binding
    per name across the file is what the scan can honestly claim.

    No file in this repository trips any of these, which is what makes the
    trade cheap: the repo-wide scan above is green.
    """
    assert unpinned_lines(source) != [], f"expected over-approximation: {why}"


def test_name_resolution_stays_linear_on_a_deep_reverse_chain() -> None:
    """A long chain resolved in the worst order must not cost quadratic work.

    Every binding here reads the name defined on the following line, so a
    repeated sweep learns exactly one name per pass and does N passes over N
    bindings. The queue learns the whole chain in one pass over the dependency
    edges instead.

    The bound is deliberately loose. Measured on this machine the queue takes
    0.36 seconds and a repeated sweep takes about 40, so anything under the
    ceiling is the linear implementation and anything over it is a regression
    to the sweep, not a slow CI runner.
    """
    depth = 20000
    source = "\n".join(
        ["import subprocess"]
        + [f"v{index} = v{index + 1}" for index in range(depth)]
        + [f"v{depth} = subprocess.run", 'v0(["x"], capture_output=True, text=True)']
    )
    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged, "a chain of any depth still reaches a subprocess entry point"
    assert elapsed < 10.0, f"name resolution took {elapsed:.1f}s for {depth} bindings"


def test_unpacking_a_wide_container_stays_linear() -> None:
    """One value shared by many names must be read once, not once per name.

    A left side that does not line up with the right side pairs every name
    with the whole of it, so ``width`` bindings share a single value node.
    Reading that node once per binding walks the same subtree ``width`` times,
    which is quadratic and measurably so: 4000 names took 17.76 seconds.

    Grouping the bindings that share a value node bounds the work at one read
    per node. Nothing here resolves, which is the point: the cost has to stay
    bounded even when no answer is ever found.
    """
    width = 4000
    names = ", ".join(f"a{index}" for index in range(width))
    values = ", ".join(f"b{index}" for index in range(width))
    source = f"import subprocess\n{names} = {{{values}}}\n"

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [], "no call is made, so nothing can decode"
    assert elapsed < 3.0, f"unpacking took {elapsed:.1f}s for {width} names"


def test_a_value_reading_many_names_stays_linear() -> None:
    """A binding that reads many names must be read once, not once per name.

    The mirror of the case above. There one value was shared by many names;
    here one value reads many names, and each of them resolving queues the
    group that reads it. Reading that group again walks the whole node, so a
    container of ``width`` names is walked ``width`` times: 4000 names took
    3.28 seconds, growing fourfold for every doubling.

    A group whose names are all resolved has nothing left to learn, so it can
    be dropped without reading it. Every later queue entry for it is then
    free, and the node is walked at most twice.
    """
    width = 4000
    bindings = "\n".join(f"held{index} = subprocess.run" for index in range(width))
    elements = ", ".join(f"held{index}" for index in range(width))
    source = f"import subprocess\n{bindings}\nkept = [{elements}]\n"

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [], "no call is made, so nothing can decode"
    assert elapsed < 1.5, f"resolution took {elapsed:.1f}s for {width} names"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess\nv1 = v2\nv2 = subprocess.run\n'
            'v1(["x"], capture_output=True, text=True)',
            "a binding that reads a name defined below it still resolves",
        ),
    ],
)
def test_detector_resolves_out_of_order_chains(source: str, why: str) -> None:
    """Source order does not decide resolution order, so neither can evade."""
    assert unpinned_lines(source) != [], f"missed {why}"


def test_name_resolution_survives_a_deep_subscript_chain() -> None:
    """A long subscript chain must not exhaust the interpreter stack.

    ``a[0][0][0]...`` is left recursive rather than nested, so the parser
    imposes no bracket-depth limit and hands back an arbitrarily deep tree.
    Unwinding it with recursion crashes; unwinding it in a loop does not.
    """
    source = "import subprocess\na = subprocess.run" + "[0]" * 2000 + "\na()"

    assert unpinned_lines(source) == [], "a bare call with no keywords decodes nothing"
