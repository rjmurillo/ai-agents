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

# check_output passes stdout=PIPE itself, so it captures whatever the call
# site says. Nothing in the source has to ask for capture, which means text
# mode on its own is enough to decode. run and Popen are not like this: with
# no capture keyword their output goes to the inherited handles and never
# becomes a str.
_ALWAYS_CAPTURING_ATTRS = frozenset({"check_output"})

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
_Assign = ast.Assign | ast.AnnAssign | ast.NamedExpr | ast.AugAssign

# Entry points that hand back str no matter what keywords a call passes.
_DECODES_UNCONDITIONALLY = _ALWAYS_TEXT_ATTRS | frozenset({_DYNAMIC})

# Per module, the names worth binding from a ``from ... import`` and what each
# one resolves to. A table rather than a branch per module, so a new source of
# subprocess entry points is one row.
_IMPORTED_NAMES: dict[str, dict[str, str]] = {
    "subprocess": {attr: attr for attr in _SUBPROCESS_ATTRS},
    "functools": {"partial": _PARTIAL},
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


def _is_literal_false(node: ast.expr | None) -> bool:
    """Report whether *node* is the literal ``False``."""
    return isinstance(node, ast.Constant) and node.value is False


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
    call: ast.Call, modules: set[str], functions: dict[str, str]
) -> str | None:
    """Resolve a wrapper call that yields a subprocess entry point.

    Covers ``functools.partial(subprocess.run, ...)`` and
    ``getattr(subprocess, "run")``. Both are static references wearing a
    disguise: the name is right there in the source.
    """
    label = _call_label(call)
    if _is_partial(label, functions) and call.args:
        return _resolve_callable(call.args[0], modules, functions)
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
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
        # ``H[0] = subprocess.run`` puts the value into H without rebinding
        # the name, so the base takes the binding. Which slot it lands in
        # does not matter: the write is what stops H being read from its
        # literal, so the whole container has to answer for it.
        return [(target.value.id, value)]
    if not isinstance(target, (ast.Tuple, ast.List)):
        return []
    if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
        return [
            pair
            for sub, item in zip(target.elts, value.elts, strict=True)
            for pair in _unpack(sub, item)
        ]
    return [pair for sub in target.elts for pair in _unpack(sub, value)]


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
        elif isinstance(node, ast.Match):
            found.extend(_captured(node))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            # ``for runner in (subprocess.run,)`` binds a name with no
            # assignment statement anywhere in sight.
            found.extend(_iterated(node.target, node.iter))
        elif isinstance(node, ast.ClassDef):
            found.extend(_class_bindings(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
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


def _captures_text(call: ast.Call, functions: dict[str, str], target: str) -> bool:
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
    text = _keyword(call, "text")
    legacy = _keyword(call, "universal_newlines")
    if (text is None or _is_literal_false(text)) and (
        legacy is None or _is_literal_false(legacy)
    ):
        return False
    if _is_partial(_call_label(call), functions):
        # A partial can select text mode here and be handed capture_output at
        # the eventual call site, which this scan has no way to reach.
        return True
    if target in _ALWAYS_CAPTURING_ATTRS:
        # The callee captures on its own behalf, so there is no capture
        # keyword for this scan to find and none is needed.
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
