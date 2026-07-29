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

_PINNED_CODEC = "utf-8"
_OS_POPEN = "os.popen"
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

# The literal container shapes an index can be read out of. Named so the
# non-mapping branch of _element is known to carry elts.
_Container = ast.Dict | ast.List | ast.Tuple

# Entry points that hand back str no matter what keywords a call passes.
_DECODES_UNCONDITIONALLY = _ALWAYS_TEXT_ATTRS | frozenset({_DYNAMIC})

# check_output passes stdout=PIPE itself, so it captures with no capture
# keyword in sight and text mode alone is enough to decode. run and Popen
# leave the child attached to this process unless a capture keyword says
# otherwise, so they are not on this list.
_ALWAYS_CAPTURES = frozenset({"check_output"})

# Keywords that select text mode. Popen computes text mode as
# ``encoding or errors or text or universal_newlines``, so every one of these
# decides the codec and all four have to be read.
_TEXT_MODE_KEYWORDS = ("text", "universal_newlines", "encoding", "errors")

# Builtins whose result carries the elements they were handed. Each one is a
# view or a copy, so a container holding an entry point still holds it after
# the round trip and the chain has to follow.
_PASS_THROUGH = frozenset(
    {"list", "tuple", "set", "frozenset", "sorted", "reversed", "iter", "zip",
     "enumerate"}
)

# Dict methods that yield a view, mapped to the halves of the literal the view
# reads. ``items`` yields both, so both taint what the loop target binds.
_DICT_VIEWS = {
    "items": ("keys", "values"),
    "keys": ("keys",),
    "values": ("values",),
}

# Suffix marking the pseudo-name that carries what a function returns. No
# identifier can spell it, so it cannot collide with a real binding.
_CALL_SUFFIX = "()"

# Popen's positional order, minus ``self``. run, call, check_call and
# check_output all forward ``*popenargs`` into Popen unchanged, so this order
# answers for every entry point. Only the slots this scan reads are listed;
# encoding, errors and text are keyword-only on Popen and have no slot.
_POSITIONAL_ORDER = {"stdout": 4, "stderr": 5, "universal_newlines": 11}

# Methods that write through a name to the container it holds. A container
# mutated after construction no longer matches the literal it was built from,
# so indexing that literal answers for the wrong object.
_MUTATING_METHODS = frozenset(
    {
        "append", "extend", "insert", "pop", "remove", "clear", "sort",
        "reverse", "update", "setdefault", "popitem", "add", "discard",
        "__setitem__", "__delitem__",
    }
)

# Per module, the names worth binding from a ``from ... import`` and what each
# one resolves to. A table rather than a branch per module, so a new source of
# subprocess entry points is one row.
_IMPORTED_NAMES: dict[str, dict[str, str]] = {
    "subprocess": {attr: attr for attr in _SUBPROCESS_ATTRS},
    "functools": {"partial": _PARTIAL},
}


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for keyword *name*, or ``None`` when absent.

    Falls back to the positional slot the name occupies. ``Popen`` takes most
    of its parameters positionally, and ``run``, ``call``, ``check_call`` and
    ``check_output`` all forward ``*popenargs`` into it unchanged, so one order
    answers for every entry point. A twelfth positional argument selects text
    mode exactly as ``universal_newlines=True`` does, and reading only
    ``call.keywords`` lets it through.

    ``encoding``, ``errors`` and ``text`` are keyword-only on ``Popen``, so
    they have no slot here and cannot be passed this way at all.
    """
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    index = _POSITIONAL_ORDER.get(name)
    if index is None or index >= len(call.args):
        return None
    argument = call.args[index]
    # A starred argument shifts every slot after it by an unknown amount, so
    # the name this slot holds is no longer knowable.
    if any(isinstance(node, ast.Starred) for node in call.args[: index + 1]):
        return None
    return argument


def _has_splat(call: ast.Call) -> bool:
    """Report whether *call* forwards ``**kwargs``.

    Live, and load bearing. This helper was dead once, and the reason it was
    dead was a hole in :func:`_captures_text`, not an excess of caution. See
    the splat cases in ``test_detector_closes_the_evasions``.
    """
    return any(keyword.arg is None for keyword in call.keywords)


def _is_literal_false(node: ast.expr | None) -> bool:
    """Report whether *node* is the literal ``False``."""
    return isinstance(node, ast.Constant) and node.value is False


def _selects_text_mode(node: ast.expr | None) -> bool:
    """Report whether a text-mode keyword value turns decoding on.

    Mirrors ``Popen``'s own ``encoding or errors or text or universal_newlines``:
    a missing keyword and a falsy literal leave bytes mode alone, and anything
    else selects text mode. A name or an attribute cannot be resolved here, so
    it counts as text mode and is then held to the UTF-8 pin.
    """
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return bool(node.value)
    return True


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


def _dict_view(call: ast.Call) -> list[ast.expr] | None:
    """Return the halves of a dict literal a view call reads, or ``None``.

    ``{"a": subprocess.run}.values()`` yields the entry point without ever
    binding a name to it, and ``.items()`` yields it inside a tuple that a
    loop target then unpacks.
    """
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    parts = _DICT_VIEWS.get(func.attr)
    if parts is None or not isinstance(func.value, ast.Dict):
        return None
    return [
        node
        for part in parts
        for node in getattr(func.value, part)
        if node is not None
    ]


def _return_bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, ast.expr]]:
    """Bind what a function returns to the pseudo-name for its call result.

    ``def get(): return subprocess.run`` puts an entry point behind ``get()``
    while binding no name to one, so ``get()(...)`` reads as opaque without
    this. A return inside a nested function is attributed to the outer one,
    which over-approximates in the direction the rest of this scan already
    takes: it can only add a finding, never hide one.
    """
    return [
        (f"{node.name}{_CALL_SUFFIX}", child.value)
        for child in ast.walk(node)
        if isinstance(child, ast.Return) and child.value is not None
    ]


def _resolve_indirect(
    call: ast.Call, modules: set[str], functions: dict[str, str]
) -> str | None:
    """Resolve a wrapper call that yields a subprocess entry point.

    Covers ``functools.partial(subprocess.run, ...)`` and
    ``getattr(subprocess, "run")``. Both are static references wearing a
    disguise: the name is right there in the source.

    Also covers a call that hands back what it was given: a pass-through
    builtin, a view on a dict literal, and a function whose ``return`` reaches
    an entry point. The scan resolves values, so without these a literal
    handed to ``list`` or ``zip`` becomes an opaque node and the chain stops
    one step short of the call it was meant to reach.
    """
    label = _call_label(call)
    if _is_partial(label, functions) and call.args:
        return _resolve_callable(call.args[0], modules, functions)
    if label in _PASS_THROUGH:
        return _resolve_elements(list(call.args), modules, functions)
    view = _dict_view(call)
    if view is not None:
        return _resolve_elements(view, modules, functions)
    returned = functions.get(f"{label}{_CALL_SUFFIX}")
    if returned is not None:
        return returned
    if label == "getattr" and len(call.args) >= 2:
        owner, attr = call.args[0], call.args[1]
        if not (isinstance(owner, ast.Name) and owner.id in modules):
            return None
        if not isinstance(attr, ast.Constant):
            # ``getattr(subprocess, name)`` hides which entry point it reaches.
            # Nothing in this repository needs that, so the safe reading is
            # that it reaches one of them.
            return _DYNAMIC
        if attr.value in _SUBPROCESS_ATTRS:
            return str(attr.value)
    return None


def _resolve_elements(
    values: list[ast.expr], modules: set[str], functions: dict[str, str]
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
        # keys on show are not the whole mapping.
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
    node: ast.Attribute, modules: set[str], functions: dict[str, str]
) -> str | None:
    """Return the subprocess entry point ``owner.attr`` names, or ``None``."""
    if isinstance(node.value, ast.Name):
        owner, attr = node.value.id, node.attr
        if owner in modules and attr in _SUBPROCESS_ATTRS:
            return attr
        if owner == "os" and attr == "popen":
            return _OS_POPEN
    # No partial filter here, unlike the bare-name branch in the caller. The
    # sentinel is only ever written for an imported name, and every attribute
    # binding is resolved through that branch, which drops it.
    return functions.get(_ATTRIBUTE + node.attr)


def _resolve_callable(
    node: ast.expr,
    modules: set[str],
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
        return None if resolved == _PARTIAL else resolved
    if isinstance(node, ast.Attribute):
        return _attribute(node, modules, functions)
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


def _subscript_binding(
    target: ast.Subscript, value: ast.expr
) -> list[tuple[str, ast.expr]]:
    """Bind the container a subscript target writes into.

    ``H[0] = subprocess.run`` writes into whatever ``H`` holds. Which slot it
    lands in is not modelled, so the binding is recorded against the container
    name and any read of it inherits the value. A subscript chain is left
    recursive, so unwinding it must not recurse.
    """
    base: ast.expr = target.value
    while isinstance(base, ast.Subscript):
        base = base.value
    if isinstance(base, ast.Name):
        return [(base.id, value)]
    if isinstance(base, ast.Attribute):
        return [(_ATTRIBUTE + base.attr, value)]
    return []


def _unpack(target: ast.expr, value: ast.expr) -> list[tuple[str, ast.expr]]:
    """Pair every name in an assignment *target* with the value it may receive.

    Shapes that line up are matched element by element. When they do not line
    up the right side is unknown, so every name on the left is paired with the
    whole of it rather than dropped. An attribute target binds under its own
    key, because the object holding it is out of reach of this scan. A
    subscript target binds the container name, because which slot receives the
    value is not modelled.
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
        return _subscript_binding(target, value)
    if not isinstance(target, (ast.Tuple, ast.List)):
        return []
    if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
        return [
            pair
            for sub, item in zip(target.elts, value.elts, strict=True)
            for pair in _unpack(sub, item)
        ]
    return [pair for sub in target.elts for pair in _unpack(sub, value)]


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


def _class_bindings(node: ast.ClassDef) -> list[tuple[str, ast.expr]]:
    """Pair every attribute a class body binds with the value it receives.

    A class body binds attributes without ever naming ``self``, so the names
    are recorded under the attribute prefix and read back the same way.
    """
    found: list[tuple[str, ast.expr]] = []
    for statement in node.body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            found.extend(
                (_ATTRIBUTE + name, bound)
                for name, bound in _unpack(target, statement.value)
            )
    return found


def _pattern_names(pattern: ast.pattern) -> list[str]:
    """Return every name a ``match`` case pattern captures.

    A capture binds without an assignment statement, the same way a loop
    target does. Sequence and mapping shapes are not lined up against the
    subject, so each captured name inherits the whole of it, which is the
    over-approximating direction this scan takes everywhere else.
    """
    found: list[str] = []
    for node in ast.walk(pattern):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
            found.append(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            found.append(node.rest)
    return found


def _iter_bindings(target: ast.expr, iterable: ast.expr) -> list[tuple[str, ast.expr]]:
    """Pair a loop target with what one turn of the loop hands it.

    ``for a, b in [(check_call, run)]`` gives ``a`` the first member of each
    element, not the whole list. Pairing against the list instead hands every
    name every callable in it, which reads ``a`` as ``run`` and flags a call
    that captures nothing.

    Only a literal sequence whose elements all line up with the target is
    unpacked. Anything else keeps the whole iterable, because the elements it
    yields are not on show.
    """
    if not isinstance(target, (ast.Tuple, ast.List)):
        return _unpack(target, iterable)
    if not isinstance(iterable, (ast.List, ast.Tuple, ast.Set)):
        return _unpack(target, iterable)
    width = len(target.elts)
    if any(isinstance(element, ast.Starred) for element in target.elts):
        # A starred target absorbs an unknown count, so no position lines up.
        return _unpack(target, iterable)
    grid: list[list[ast.expr]] = []
    for row in iterable.elts:
        if not isinstance(row, (ast.Tuple, ast.List)) or len(row.elts) != width:
            return _unpack(target, iterable)
        if any(isinstance(item, ast.Starred) for item in row.elts):
            return _unpack(target, iterable)
        grid.append(list(row.elts))
    if not grid:
        return _unpack(target, iterable)
    found: list[tuple[str, ast.expr]] = []
    for index, sub in enumerate(target.elts):
        # One synthetic tuple per position, so a name that several turns of
        # the loop bind keeps every value rather than only the first.
        column = ast.Tuple(elts=[row[index] for row in grid], ctx=ast.Load())
        found.extend(_unpack(sub, column))
    return found


def _assign_bindings(
    node: ast.Assign | ast.AnnAssign | ast.NamedExpr | ast.AugAssign,
) -> list[tuple[str, ast.expr]]:
    """Pair names with values for the four statement forms that assign.

    ``H += [subprocess.run]`` extends the object in place, so the literal ``H``
    was built from goes stale, which ``_mutated`` handles. What it puts into
    ``H`` still has to bind, or a container extended with an entry point and
    then indexed resolves to nothing at all.
    """
    if isinstance(node, ast.Assign):
        return [pair for target in node.targets for pair in _unpack(target, node.value)]
    if isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.value is not None:
            return [(node.target.id, node.value)]
        return []
    if isinstance(node, ast.AugAssign):
        if isinstance(node.target, ast.Name):
            return [(node.target.id, node.value)]
        return []
    return [(node.target.id, node.value)]


def _mutation_bindings(node: ast.Call) -> list[tuple[str, ast.expr]]:
    """Bind a container to what a mutating method call puts into it.

    ``H.append(subprocess.run)`` puts a callable into ``H`` without an
    assignment statement anywhere. Which slot it lands in is not modelled, so
    every argument binds the container name.

    Keyword arguments count for the same reason: ``H.update(b=subprocess.run)``
    stores through a keyword and reading only positional arguments misses it.
    """
    method = node.func
    if not isinstance(method, ast.Attribute) or method.attr not in _MUTATING_METHODS:
        return []
    if not isinstance(method.value, ast.Name):
        return []
    name = method.value.id
    return [
        (name, arg.value if isinstance(arg, ast.Starred) else arg) for arg in node.args
    ] + [(name, keyword.value) for keyword in node.keywords]


def _match_bindings(node: ast.Match) -> list[tuple[str, ast.expr]]:
    """Bind every name a ``match`` case captures to the subject it reads."""
    return [
        (name, node.subject)
        for case in node.cases
        for name in _pattern_names(case.pattern)
    ]


def _bindings(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    """Collect every ``name = value`` binding at any depth.

    Covers plain assignment, annotated assignment, the walrus, loop and
    comprehension targets, ``match`` captures, mutating method calls, class
    bodies, and default arguments, every one of which binds a name without an
    assignment statement to find. Assignment targets are unpacked, so a name
    bound by destructuring is as visible as one bound on its own.
    """
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
            found.extend(_assign_bindings(node))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            # ``for runner in (subprocess.run,)`` binds a name with no
            # assignment statement anywhere in sight.
            found.extend(_iter_bindings(node.target, node.iter))
        elif isinstance(node, ast.Call):
            found.extend(_mutation_bindings(node))
        elif isinstance(node, ast.Match):
            found.extend(_match_bindings(node))
        elif isinstance(node, ast.ClassDef):
            found.extend(_class_bindings(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(_defaults(node.args))
            found.extend(_return_bindings(node))
    return found


def _mutated(tree: ast.AST) -> set[str]:
    """Return every name written through after the object it holds is built.

    ``H[0] = subprocess.run`` and ``H.append(subprocess.run)`` both leave the
    literal ``H`` was built from unchanged. Reading the stale literal then
    answers for an object that no longer holds what the name points at. Such
    names are dropped, which falls back to tainting the container whole.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if isinstance(node.value, ast.Name):
                found.add(node.value.id)
        elif isinstance(node, ast.AugAssign):
            # ``H += [subprocess.run]`` extends in place for a list and does
            # not register as a second binding.
            if isinstance(node.target, ast.Name):
                found.add(node.target.id)
        elif isinstance(node, ast.Call):
            # ``H.pop()`` takes no argument and still mutates, so the method
            # name alone decides this, not what _mutation_bindings can bind.
            method = node.func
            if (
                isinstance(method, ast.Attribute)
                and method.attr in _MUTATING_METHODS
                and isinstance(method.value, ast.Name)
            ):
                found.add(method.value.id)
    return found


def _containers(
    tree: ast.AST, bindings: list[tuple[str, ast.expr]]
) -> dict[str, _Container]:
    """Map each name bound exactly once to a literal container, to that literal.

    Bound exactly once is the whole guarantee. A second binding anywhere,
    including a loop target or a parameter default, means the name may hold
    something the literal does not show, and indexing the literal would then
    answer for the wrong object. Such names are left out, so the caller falls
    back to tainting the container whole. A name written through after
    construction is dropped for the same reason; see ``_mutated``.
    """
    counts = Counter(name for name, _ in bindings)
    mutated = _mutated(tree)
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
            if (
                isinstance(target, ast.Name)
                and counts.get(target.id) == 1
                and target.id not in mutated
            ):
                found[target.id] = value
    return found


def _imports(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    """Collect the module aliases and imported names that reach subprocess.

    ``import subprocess as sp`` and ``from subprocess import run`` are both
    ordinary Python, and an owner-name check that only knows the literal word
    ``subprocess`` misses each of them.
    """
    modules = {"subprocess"}
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            wanted = _IMPORTED_NAMES.get(node.module or "", {})
            for alias in node.names:
                if alias.name in wanted:
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


def _subprocess_names(
    tree: ast.Module,
) -> tuple[set[str], dict[str, str], dict[str, _Container]]:
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
    bindings = _bindings(tree)
    containers = _containers(tree, bindings)
    groups: dict[int, tuple[ast.expr, list[str]]] = {}
    for name, value in bindings:
        groups.setdefault(id(value), (value, []))[1].append(name)

    dependents = _dependents(groups)
    queue = list(groups)
    while queue:
        value, names = groups[queue.pop()]
        if all(name in functions for name in names):
            # Every name this group binds is already settled, and the first
            # binding of a name wins, so resolving again cannot change an
            # answer. Skipping before the walk is what keeps a value node that
            # reads N names from being re-walked once per name: 4000 names
            # took 3.26 seconds that way.
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
            if name.endswith(_CALL_SUFFIX):
                # A group reading ``get()`` registers a dependency on the bare
                # name ``get``, because that is the only Name node in it.
                queue.extend(dependents.get(name[: -len(_CALL_SUFFIX)], ()))
    return modules, functions, containers


def _target(
    call: ast.Call,
    modules: set[str],
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


def _captures_text(call: ast.Call, functions: dict[str, str], target: str = "") -> bool:
    """Report whether *call* may decode captured output into ``str``.

    Deliberately conservative. Anything other than a literal ``False`` counts,
    because ``text=1`` and ``capture_output=flag`` both decode at runtime while
    reading as compliant to a check that only recognises ``True``.

    A ``functools.partial`` that selects text mode counts even with no capture
    keyword, because the capture can be supplied where the partial is called.

    An entry point that captures on its own, such as ``check_output``, needs
    no capture keyword: text mode alone decides its codec.

    A ``**kwargs`` splat is treated as text mode outright. The keywords it
    carries are not visible here, so ``text`` may be among them, and reading
    the absence of a literal keyword as proof of bytes mode is the hole an
    adversarial review walked through.

    Text mode is selected by ``encoding`` and ``errors`` as well as by ``text``
    and ``universal_newlines``. ``Popen`` computes it as
    ``encoding or errors or text or universal_newlines``, so reading only the
    latter two lets ``errors="ignore"`` decode under the locale codec, and lets
    ``encoding="latin-1"`` decode under a codec that is pinned but wrong.
    """
    if _has_splat(call):
        return True
    if not any(_selects_text_mode(_keyword(call, name)) for name in _TEXT_MODE_KEYWORDS):
        return False
    if _is_partial(_call_label(call), functions):
        # A partial can select text mode here and be handed capture_output at
        # the eventual call site, which this scan has no way to reach.
        return True
    if target in _ALWAYS_CAPTURES:
        # check_output supplies stdout=PIPE itself. Text mode is the whole
        # condition, so requiring a capture keyword as well misses the decode.
        return True
    capture = _keyword(call, "capture_output")
    if capture is not None and not _is_literal_false(capture):
        return True
    return _keyword(call, "stdout") is not None or _keyword(call, "stderr") is not None


def _pins_utf8(call: ast.Call) -> bool:
    """Report whether *call* proves its codec is UTF-8 at the call site.

    ``encoding=None`` is an explicit request for the locale codec, a name or
    attribute cannot be resolved statically, and ``utf-8-sig`` quietly strips a
    byte order mark, so only the literal string counts.
    """
    encoding = _keyword(call, "encoding")
    if encoding is None:
        return False
    return isinstance(encoding, ast.Constant) and encoding.value == _PINNED_CODEC


def unpinned_lines(source: str) -> list[int]:
    """Return the line numbers of text-capturing calls that do not pin UTF-8."""
    tree = ast.parse(source)
    modules, functions, containers = _subprocess_names(tree)
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
            node, functions, target
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
            "import subprocess\nfor a, b in [(subprocess.check_call, subprocess.run)]:\n"
            "    a(['x'], capture_output=True, text=True)",
            "a destructuring loop over a literal reads the column, not the whole list",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], text=True, "
            "encoding='utf-8')",
            "check_output that pins the codec is compliant",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'])",
            "check_output in bytes mode decodes nothing",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], text=True)",
            "run without a capture keyword leaves the child attached",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, "
            "encoding=None)",
            "encoding=None is the default and leaves the call in bytes mode",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, "
            "errors=None)",
            "errors=None leaves the call in bytes mode too",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], errors='ignore')",
            "errors= without a capture keyword still captures nothing",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, "
            "errors='ignore', encoding='utf-8')",
            "errors= alongside a pinned codec decodes as UTF-8",
        ),
        (
            "import subprocess\nfor fn in list([print]):\n"
            "    fn(['x'], capture_output=True, text=True)",
            "a pass-through of a container holding nothing relevant stays quiet",
        ),
        (
            "import subprocess\nfor v in {'a': print}.values():\n"
            "    v(['x'], capture_output=True, text=True)",
            "a dict view over unrelated values stays quiet",
        ),
        (
            "import subprocess\ndef get():\n    return print\n"
            "get()(['x'], capture_output=True, text=True)",
            "a function returning something else is not an entry point",
        ),
        (
            "import subprocess\nsubprocess.Popen(['e'], -1, None, None, "
            "subprocess.PIPE, subprocess.PIPE, None, True, False, None, None, False)",
            "a positional universal_newlines of False leaves bytes mode alone",
        ),
        (
            "import subprocess\nsubprocess.Popen(*a, -1, None, None, None, None, "
            "None, True, False, None, None, True)",
            "a starred argument shifts every slot after it by an unknown amount",
        ),
        (
            "import subprocess\nsubprocess.Popen(['e'], -1, None, None, "
            "subprocess.PIPE, subprocess.PIPE, None, True, False, None, None, "
            "True, encoding='utf-8')",
            "a positional universal_newlines alongside a pinned codec is compliant",
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
            "import subprocess\nsubprocess.check_output(['x'], text=True)",
            "check_output pipes stdout itself, so text mode alone decodes",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], universal_newlines=True)",
            "the legacy spelling of text mode decodes the same way",
        ),
        (
            "from subprocess import check_output\ncheck_output(['x'], text=True)",
            "an imported check_output captures without a keyword just the same",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\nH[0] = subprocess.run\n"
            "H[0](['x'], text=True, capture_output=True)",
            "a container written to after construction no longer matches its literal",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\nH.append(subprocess.run)\n"
            "H[0](['x'], text=True, capture_output=True)",
            "a container mutated by method call no longer matches its literal",
        ),
        (
            "import subprocess\nH = [local, subprocess.run]\nH.pop()\n"
            "H[0](['x'], text=True, capture_output=True)",
            "a zero-argument mutator still invalidates the literal",
        ),
        (
            "import subprocess\nH = [subprocess.check_call]\nH += [subprocess.run]\n"
            "H[0](['x'], text=True, capture_output=True)",
            "an augmented assignment binds what it extends the container with",
        ),
        (
            "import subprocess\nH = {'a': subprocess.check_call}\n"
            "H.update(b=subprocess.run)\nH['a'](['x'], text=True, capture_output=True)",
            "a mutating method stores through keywords as well as arguments",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n    case runner:\n"
            "        runner(['x'], text=True, capture_output=True)",
            "a match capture binds a name with no assignment statement",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n    case [*rest]:\n"
            "        rest(['x'], text=True, capture_output=True)",
            "a starred match capture binds a name too",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, "
            "errors='ignore')",
            "errors= alone selects text mode and decodes under the locale codec",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], errors='replace')",
            "errors= selects text mode on an entry point that captures on its own",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, "
            "encoding='latin-1')",
            "encoding= alone selects text mode, and this codec is pinned but wrong",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, "
            "encoding=chosen)",
            "a codec read from a name cannot be proven to be UTF-8",
        ),
        (
            "import subprocess\nfor k, v in {'a': subprocess.run}.items():\n"
            "    v(['x'], capture_output=True, text=True)",
            "a dict view yields the entry point without binding a name to it",
        ),
        (
            "import subprocess\nfor v in {'a': subprocess.run}.values():\n"
            "    v(['x'], capture_output=True, text=True)",
            "values() is the same view with one half of the literal",
        ),
        (
            "import subprocess\nfor a, b in zip([1], [subprocess.run]):\n"
            "    b(['x'], capture_output=True, text=True)",
            "zip hands back the elements it was given",
        ),
        (
            "import subprocess\nfor i, fn in enumerate([subprocess.run]):\n"
            "    fn(['x'], capture_output=True, text=True)",
            "enumerate hands back the elements it was given",
        ),
        (
            "import subprocess\nfor fn in reversed([subprocess.run]):\n"
            "    fn(['x'], capture_output=True, text=True)",
            "reversed hands back the elements it was given",
        ),
        (
            "import subprocess\nfor fn in sorted([subprocess.run]):\n"
            "    fn(['x'], capture_output=True, text=True)",
            "sorted hands back the elements it was given",
        ),
        (
            "import subprocess\nfor fn in list([subprocess.run]):\n"
            "    fn(['x'], capture_output=True, text=True)",
            "a copy of a literal still holds what the literal held",
        ),
        (
            "import subprocess\ndef get():\n    return subprocess.run\n"
            "get()(['x'], capture_output=True, text=True)",
            "a function return puts an entry point behind a call, not a name",
        ),
        (
            "import subprocess\ndef get():\n    return subprocess.run\n"
            "runner = get()\nrunner(['x'], capture_output=True, text=True)",
            "a name bound to a returned entry point resolves through the call",
        ),
        (
            "import subprocess\nsubprocess.Popen(['e'], -1, None, None, "
            "subprocess.PIPE, subprocess.PIPE, None, True, False, None, None, True)",
            "the twelfth positional is universal_newlines and selects text mode",
        ),
        (
            "import subprocess\nsubprocess.run(['e'], -1, None, None, "
            "subprocess.PIPE, subprocess.PIPE, None, True, False, None, None, True)",
            "run forwards popenargs into Popen, so the same slot decides",
        ),
        (
            "import subprocess\nsubprocess.Popen(['e'], -1, None, None, "
            "subprocess.PIPE, text=True)",
            "the fifth positional is stdout and supplies the capture",
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
    to carry the binding.

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


def test_one_value_reading_many_names_stays_linear() -> None:
    """A value node that reads N names must be walked once, not once per name.

    The mirror of the wide-unpack shape. One list literal reading ``width``
    names is re-queued every time one of them resolves, and each pop re-walks
    the whole node, which is quadratic: 4000 names took 3.26 seconds.

    A group whose names are all settled cannot change an answer, so skipping
    it before the walk bounds the work. Unlike the wide-unpack case every
    name here does resolve, which is what drives the re-queue.
    """
    width = 4000
    lines = ["import subprocess"]
    lines += [f"n{index} = subprocess.run" for index in range(width)]
    lines.append("WIDE = [" + ", ".join(f"n{index}" for index in range(width)) + "]")
    source = "\n".join(lines)

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [], "no call is made, so nothing can decode"
    assert elapsed < 1.0, f"resolution took {elapsed:.1f}s for {width} names"


def test_return_bindings_stay_linear_in_a_deeply_nested_file() -> None:
    """Collecting returns walks each function body once per enclosing function.

    ``_return_bindings`` calls ``ast.walk`` on the whole function, so a body
    nested ``depth`` deep is walked ``depth`` times. CPython refuses more than
    100 indentation levels, which bounds that multiplier at a constant the
    parser enforces rather than one this scan has to police, so the work stays
    linear in file size. The nesting here sits just under that ceiling.
    """
    depth, width = 90, 2000
    lines = [("  " * level) + f"def f{level}():" for level in range(depth)]
    lines += [("  " * depth) + f"x{index} = {index}" for index in range(width)]
    lines.append(("  " * depth) + "return 1")
    source = "\n".join(lines)

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [], "nothing here reaches subprocess"
    assert elapsed < 3.0, f"resolution took {elapsed:.1f}s at depth {depth}"


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
