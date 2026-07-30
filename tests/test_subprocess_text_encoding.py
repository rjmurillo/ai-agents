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
# Popen selects the mode with ``encoding or errors or text or
# universal_newlines``, so all four are equal doors into str. Reading only the
# last two lets ``errors="ignore"`` through, which is exactly what an author
# writes to silence a UnicodeDecodeError while keeping the locale codec.
_TEXT_SELECTORS = ("text", "universal_newlines", "encoding", "errors")
_OS_POPEN = "os.popen"
# Stands for a subprocess entry point selected at runtime, which no static
# scan can name. Because it may be getoutput, which decodes with no flag to
# read, invoking one counts as decoding text whatever keywords are present.
_DYNAMIC = "subprocess.<dynamic>"

# Marks a name that reaches functools.partial. Held in the same map as the
# subprocess names for want of a second one to thread, and filtered out of
# every path that answers "is this a subprocess entry point".
_ATTRIBUTE = "."

#: The subprocess sentinels that leave a stream with nothing to read. The
#: null device throws the bytes away, and ``STDOUT`` merges one stream into
#: the other rather than opening a pipe of its own: with no pipe on the
#: receiving side both attributes stay ``None`` and no decoder runs.
_DEVNULL = "DEVNULL"
_STDOUT = "STDOUT"
_DISCARDING_SENTINELS = frozenset({_DEVNULL, _STDOUT})
_VIA_PARTIAL = "*"
#: Marks a partial that fixed the codec where it was built. Kept apart from
#: :data:`_VIA_PARTIAL` because the two answer different questions: one says a
#: call site cannot see the capture keywords, the other says it need not.
_PINNED_PARTIAL = "*utf8*"
_UNKNOWN = object()
_PARTIAL = "functools.partial"

# The nodes that open a namespace of their own. A binding inside one belongs
# to that scope, so any walk looking for names of the enclosing scope stops
# here rather than reading a local as an attribute of the block around it.
_OWN_SCOPE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)

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
    "os": {"popen": _OS_POPEN},
}
# Modules whose attributes name an entry point. An alias is recorded against
# the module it stands for, so ``import os as system`` still reaches popen.
_ENTRY_MODULES = ("subprocess", "os")

# Attribute names that hand back the same callable they are read from, so
# ``subprocess.run.__call__`` is ``subprocess.run``. ``__get__`` is left out
# on purpose: it returns a binding rather than the callable, so calling it
# starts no process. Verified at runtime: ``subprocess.run.__call__`` with
# ``text=True`` returns ``str``, exactly as the plain form does.
_CALLABLE_ALIASES = frozenset({"__call__", "__func__", "__wrapped__"})

#: Methods that hand back an element of the object they are called on. A
#: container holding a runner yields that runner through any of them, so the
#: owner is resolved and its element answers for the call. Unlike
#: :data:`_CALLABLE_ALIASES` these do not name the same callable, they return
#: one, but both reach a runner from an expression that never spells its name.
_ELEMENT_METHODS = frozenset({"pop", "popleft", "popitem", "get", "setdefault"})

#: Element methods whose second argument is handed straight back when the key
#: is missing. ``{}.get("run", subprocess.run)`` never touches the mapping, so
#: resolving the owner alone reaches nothing and the default is the runner.
_DEFAULTING_METHODS = frozenset({"get", "setdefault"})

#: Dict methods that only read. A call to one of these on a partial's
#: ``keywords`` changes nothing, so it must not be read as a rewrite that
#: drops the pin the construction recorded.
_READING_METHODS = frozenset(
    {"get", "keys", "values", "items", "copy", "__contains__", "__len__", "__getitem__"}
)

#: Binary operators whose result is a container built out of its operands, so
#: an element of either side may be the value a later lookup hands back. Add
#: and multiply cover sequences, the bitwise three cover mappings and sets.
#: Every other operator builds something that is not a container of the
#: operands: ``"%s" % (subprocess.run,)`` yields a string of characters.
_CONTAINER_OPERATORS = (ast.Add, ast.Mult, ast.Sub, ast.BitOr, ast.BitAnd, ast.BitXor)

#: Builtins that pass an element of their argument straight back out.
#: ``next(iter([subprocess.run]))`` reaches the runner with no comprehension
#: and no attribute, so resolving the first argument is what closes it.
#: ``operator.getitem`` is here because it is a subscript spelled as a call.
_ELEMENT_BUILTINS = frozenset(
    {
        "next",
        "iter",
        "list",
        "tuple",
        "set",
        "frozenset",
        "sorted",
        "reversed",
        "min",
        "max",
        "getitem",
    }
)

#: Callables that hand back an element of their *second* argument. The first
#: is a predicate or a count, so resolving argument zero reaches the wrong
#: expression entirely: ``filter(None, [subprocess.run])`` keeps the runner in
#: the sequence and holds only ``None`` in the slot the element family reads.
_SECOND_ARG_ELEMENTS = frozenset(
    {"filter", "filterfalse", "takewhile", "dropwhile", "nlargest", "nsmallest"}
)

#: Callables that hand back an element of *any* argument, because every one of
#: them is a sequence: ``chain([], [subprocess.run])`` yields the runner from
#: the second, and nothing in the spelling says which one holds it.
_ANY_ARG_ELEMENTS = frozenset({"chain"})

#: Calls that hand their first argument straight back out, so the caller ends
#: up holding whatever was passed in. ``staticmethod`` unwraps on attribute
#: access, ``nullcontext`` unwraps on ``__enter__``, and ``enter_context``
#: returns whatever ``__enter__`` returned. ``classmethod`` is deliberately
#: absent: it binds the class as the first positional argument, so
#: ``Runner().runner(cmd, ...)`` passes the command as ``bufsize`` and raises
#: ``TypeError`` before anything decodes. Verified at runtime.
_TRANSPARENT_CALLS = frozenset({"staticmethod", "nullcontext", "enter_context"})

#: Calls whose first argument is what the caller ends up with, either because
#: an element of it is handed back or because it is handed back whole. Both
#: readings resolve the same expression, so they share one arm.
_YIELDING_CALLS = _ELEMENT_BUILTINS | _TRANSPARENT_CALLS

#: Callables from :mod:`operator` that reach an attribute without spelling it
#: as one. Both are built with the attribute name as their first argument and
#: then called with the owner, so ``attrgetter("run")(subprocess)`` and
#: ``methodcaller("run", cmd)(subprocess)`` both reach ``subprocess.run``.
_OPERATOR_GETTERS = frozenset({"attrgetter", "methodcaller"})

#: The :mod:`operator` factory that reaches an *element* rather than an
#: attribute. ``itemgetter(0)([subprocess.run])`` is a subscript with the two
#: halves swapped: the index is bound to the factory and the container is the
#: argument, so what it returns is whatever the container holds.
_OPERATOR_SELECTOR = "itemgetter"

#: Marks a local spelling of an :mod:`operator` factory. ``from operator
#: import itemgetter as pick`` renames the factory without changing what it
#: builds, so matching on the written name alone left ``pick(0)(HOLDER)``
#: unresolved. Kept behind a prefix rather than written into ``functions``
#: under the bare name, because these are not subprocess entry points and a
#: resolver reading one as such would answer for a call that starts nothing.
_OPERATOR_ALIAS = "*op*"

#: Every :mod:`operator` factory this scan reads, under its canonical name.
_OPERATOR_FACTORIES = _OPERATOR_GETTERS | frozenset({_OPERATOR_SELECTOR})

#: Marks the place in a merged mapping that could not be read. It sits where
#: the unreadable segment sat, so position still decides: a codec spelled
#: after it survives no matter what the merge holds, while one spelled before
#: it may be overwritten. Recording unreadability as a verdict instead of a
#: position read ``{**opaque, "encoding": "utf-8"}`` as unpinned, which it
#: never is. No keyword can collide with this, because ``*`` cannot appear in
#: a Python identifier.
_OPAQUE_KEY = "*opaque*"

#: Marks the capture keywords a partial pre-bound, by name. A call site that
#: repeats one of them overrides it, so the name is what says which.
_CAPTURING_PARTIAL = "*cap*"

#: Separates a pre-bound capture keyword from the state it was given. The state
#: travels with the name so that a construction read as off is distinguishable
#: from one that supplied nothing, which otherwise read as capturing.
_CAPTURE_STATE = ":"

#: The state a pre-bound capture keyword carries when it opens a pipe.
_CAPTURE_ON = "on"

#: The state a pre-bound capture keyword carries when it opens no pipe.
_CAPTURE_OFF = "off"

#: How far a mapping splat may nest before it stops being read. A real call
#: site does not merge deeper than this, and the bound is what ends recursion.
_MAPPING_DEPTH = 6

#: Calls that return the namespace a module's globals live in, so writing
#: through one binds an ordinary global rather than filling a container.
#: ``vars()`` is included because at module scope it is ``globals()`` under a
#: second name. Inside a function ``vars()`` is a snapshot and the write never
#: reaches a name, so reading it here is an over-approximation by one shape.
_NAMESPACE_CALLS = frozenset({"globals", "vars"})


def _comprehension_element(node: ast.expr) -> ast.expr | None:
    """Return the expression a comprehension yields, or ``None``.

    A comprehension is a container literal wearing a loop, so whatever it
    yields is reachable the same way a literal element is.
    """
    if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return node.elt
    if isinstance(node, ast.DictComp):
        return node.value
    return None


def _unstarred(elements: list[ast.expr]) -> list[ast.expr]:
    """Return *elements* with every star spread into the members it supplies.

    ``[*RUNNERS]`` holds whatever ``RUNNERS`` holds, so a star has to be read
    through rather than handed on. Nothing else resolves a star, and one left
    in place makes the member unreadable, which is a runner slipping past.
    A star over something with no readable members keeps that operand, so a
    name bound to a container is still resolved by the caller.
    """
    found: list[ast.expr] = []
    for element in elements:
        if not isinstance(element, ast.Starred):
            found.append(element)
            continue
        inner = _element_expressions(element.value)
        found.extend([element.value] if inner is None else inner)
    return found


def _element_expressions(node: ast.expr) -> list[ast.expr] | None:
    """Return the expressions *node* may evaluate to, or ``None``.

    One reading covers every shape that holds candidates rather than being
    one: a literal container, a comprehension that builds one, a conditional
    that picks an arm, and a boolean fallback that picks an operand. Each
    hands back a list because any member may be the one that runs, and a
    runner anywhere in the list has to answer for the call.

    A dict answers with its values in both spellings. Keys are hashed, not
    called, so a runner used as a key is not reachable through a lookup.
    """
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return _unstarred(node.elts)
    if isinstance(node, ast.Dict):
        return [value for value in node.values if value is not None]
    if isinstance(node, ast.IfExp):
        # ``subprocess.run if capture else other`` picks a runner at runtime,
        # so either arm may be the one that decodes.
        return [node.body, node.orelse]
    if isinstance(node, ast.BoolOp):
        # ``runner or subprocess.run`` is the same choice spelled shorter.
        return list(node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _CONTAINER_OPERATORS):
        # ``[] + [subprocess.run]`` builds one container out of two, ``[run] * 2``
        # builds one out of a container and a count, ``{"r": run} | {}`` merges
        # two mappings, and set algebra keeps some subset of both operands. Each
        # spelling yields the elements of whichever side has any, so both sides
        # are read and a non-container side contributes nothing. Operators that
        # build something other than a container are excluded: ``"%s" % (run,)``
        # produces a string, whose members are characters rather than the runner.
        # Verified at runtime: an element read back out of any included form
        # decodes under the locale codec, and the excluded form does not.
        left = _element_expressions(node.left) or []
        right = _element_expressions(node.right) or []
        return (left + right) or None
    element = _comprehension_element(node)
    return None if element is None else [element]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for keyword *name*, or ``None`` when absent."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _is_literal_falsy(node: ast.expr | None) -> bool:
    """Report whether *node* is a literal that subprocess reads as off.

    ``capture_output`` is tested for truth, not compared to ``False``, so
    ``0`` and ``""`` turn capture off exactly as ``False`` does and none of
    them opens a pipe. A stream keyword is a different question and does not
    use this: ``stdout=0`` names file descriptor zero, which is a redirect.
    """
    return isinstance(node, ast.Constant) and not node.value


def _is_literal_none(node: ast.expr | None) -> bool:
    """Report whether *node* is the literal ``None``.

    An explicit ``None`` is how a caller says *leave this stream alone*.
    ``stdout=None`` inherits the parent's stream and leaves ``.stdout`` empty,
    so no bytes reach a decoder and there is nothing for a codec to get wrong.
    """
    return isinstance(node, ast.Constant) and node.value is None


def _is_capturing_stream(node: ast.expr | None, modules: dict[str, str]) -> bool:
    """Report whether a ``stdout`` or ``stderr`` value opens a pipe to read.

    Each stream is read on its own, so a call that quiets one and pipes the
    other still decodes. A literal ``None`` and ``subprocess.DEVNULL`` are the
    two spellings that read as no capture. ``DEVNULL`` resolves the same way
    an entry point does, through the tracked module alias, so it is not the
    guess a file object would be: ``open(path)`` names something whose mode
    this scan cannot see, and it still counts.
    """
    if node is None or _is_literal_none(node):
        return False
    return not _is_discarded_stream(node, modules)


def _is_discarded_stream(node: ast.expr, modules: dict[str, str]) -> bool:
    """Report whether *node* names a sentinel that leaves the stream unread.

    Read through the module map rather than on the bare attribute name, so a
    ``DEVNULL`` attribute on some unrelated object is not mistaken for this
    one. ``subprocess.DEVNULL`` leaves the attribute at ``None``, which is the
    same observable state as never capturing at all. ``subprocess.STDOUT``
    opens no pipe either: it points one stream at wherever the other already
    goes, so it only decodes when that other stream is itself piped, and that
    pipe is read on its own keyword. Verified at runtime:
    ``run(cmd, stderr=STDOUT, text=True)`` returns ``None`` for both
    attributes, while adding ``stdout=PIPE`` decodes under the locale codec.
    """
    if not isinstance(node, ast.Attribute) or node.attr not in _DISCARDING_SENTINELS:
        return False
    return isinstance(node.value, ast.Name) and modules.get(node.value.id) == "subprocess"


def _selects_text(node: ast.expr | None) -> bool:
    """Report whether *node* supplies a value that turns text mode on.

    ``Popen`` decides the mode with ``encoding or errors or text or
    universal_newlines``, so all four keywords are equal doors into ``str``
    and a keyword only opens one when its value is truthy. An absent keyword
    and a literal falsy one both leave the pipes in bytes mode.

    Anything the scan cannot evaluate counts as text mode. ``text=flag``
    decodes whenever ``flag`` is true at runtime, and reading an unresolved
    value as bytes mode is the direction that hides the bug.
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


def _reaches_partial(label: str, functions: dict[str, str]) -> bool:
    """Report whether *label* names a partial, the maker or one it made.

    Two different questions share a spelling at the call site.
    ``partial(subprocess.run, text=True)`` names the maker, and
    ``run_cmd(...)`` names the object it made. Only the first is a reference
    to ``functools.partial`` itself, which is why resolving a callee asks
    :func:`_is_partial` and reading the mode asks this. Both matter to the
    mode, because either site can be the one holding the missing half.
    """
    return _is_partial(label, functions) or _VIA_PARTIAL + label in functions


def _carry_partial(
    name: str,
    value: ast.expr,
    functions: dict[str, str],
    resolved: str,
    containers: dict[str, _Container] | None = None,
) -> None:
    """Record what a call site cannot see about the partial behind *name*.

    Two facts travel with a partial and neither is legible where it is called.
    The keywords it pre-bound may be the ones that open the capture, and the
    codec it pre-bound may be the one that makes the capture safe. Both are
    kept beside the target rather than folded into it, because a later binding
    that is not a partial must not inherit either.

    An alias copies both. ``alias = runner`` is the same object under a second
    name, so reading the markers off the source name is what keeps the alias
    from looking like a bare callable with no keywords at all. A container
    holds the object just as an alias does, so ``holders[0]`` copies the same
    markers from whichever name the element was built under. Reading only the
    bare-name spelling left a partial taken out of a list looking like a
    callable that pre-bound nothing.
    """
    for source in _alias_sources(value, containers or {}):
        for marker in (_VIA_PARTIAL, _PINNED_PARTIAL, _CAPTURING_PARTIAL):
            if marker + source in functions:
                functions[marker + name] = functions[marker + source]
        return
    if not isinstance(value, ast.Call) or not _is_partial(_call_label(value), functions):
        return
    functions[_VIA_PARTIAL + name] = resolved
    if _pins_utf8(value):
        functions[_PINNED_PARTIAL + name] = resolved
    supplied = _capture_keywords(value)
    if supplied:
        functions[_CAPTURING_PARTIAL + name] = ",".join(supplied)


def _alias_sources(value: ast.expr, containers: dict[str, _Container]) -> list[str]:
    """Return the names *value* is the same object as, bare or through a container."""
    if isinstance(value, ast.Name):
        return [value.id]
    return _module_source(value, containers) if isinstance(value, ast.Subscript) else []


def _capture_keywords(call: ast.Call) -> list[str]:
    """Return the capture keywords *call* supplies, each tagged on or off.

    Recorded by name rather than as a verdict, because a call site can shadow
    one of these and only the name says which. The state travels with the name
    so that a construction which was read and said off is not confused with one
    that said nothing: ``partial(run, capture_output=False)`` captures nothing,
    and dropping the record left it indistinguishable from a silent partial and
    so reported as capturing.

    ``stdout`` counts as on wherever it appears: a stream that opens no pipe is
    recorded here and then read as capturing, which keeps this no quieter than
    treating the whole partial as opaque already does.
    """
    supplied = []
    capture = _keyword(call, "capture_output")
    if capture is not None:
        state = _CAPTURE_OFF if _is_literal_falsy(capture) else _CAPTURE_ON
        supplied.append("capture_output" + _CAPTURE_STATE + state)
    supplied.extend(
        name + _CAPTURE_STATE + _CAPTURE_ON
        for name in ("stdout", "stderr")
        if _keyword(call, name) is not None
    )
    return supplied


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
    if label in _YIELDING_CALLS and call.args:
        # ``next(...)`` and friends hand back an element of their argument, and
        # ``staticmethod(...)`` and friends hand the argument back whole, so
        # whatever that argument resolves to is what the caller ends up with.
        return _resolve_callable(call.args[0], modules, functions)
    if label in _SECOND_ARG_ELEMENTS and len(call.args) >= 2:
        # The sequence is the second argument here, so reading the first
        # resolves a predicate or a count and misses the runner entirely.
        return _resolve_callable(call.args[1], modules, functions)
    if label in _ANY_ARG_ELEMENTS and call.args:
        # Every argument is a sequence, and the runner may be in any of them.
        return _resolve_elements(call.args, modules, functions)
    getter = _resolve_operator_getter(call, modules, functions)
    if getter is not None:
        return getter
    if isinstance(call.func, ast.Attribute) and call.func.attr in _ELEMENT_METHODS:
        return _resolve_element_method(call, call.func, modules, functions)
    if label == "getattr" and len(call.args) >= 2:
        return _resolve_getattr(call, modules, functions)
    return None


def _resolve_element_method(
    call: ast.Call,
    method: ast.Attribute,
    modules: dict[str, str],
    functions: dict[str, str],
) -> str | None:
    """Resolve a call to a method that hands back an element of its receiver.

    ``holder.pop()`` yields an element of the holder. The method itself is not
    the runner, which is why this is read on the call and not in
    :func:`_attribute` where the attribute alone is resolved.
    """
    owned = _resolve_callable(method.value, modules, functions)
    if owned is not None:
        return owned
    if method.attr in _DEFAULTING_METHODS and len(call.args) >= 2:
        # A missing key hands the default straight back, so the second
        # argument is the other place the runner can be hiding. A literal
        # receiver that already holds the key never reaches the default, and
        # reading it anyway flagged a lookup that resolves to something else
        # entirely.
        if _mapping_holds(method.value, call.args[0]):
            return None
        return _resolve_callable(call.args[1], modules, functions)
    return None


def _mapping_holds(receiver: ast.expr, key: ast.expr) -> bool:
    """Report whether *receiver* is a literal mapping proven to carry *key*."""
    wanted = _literal_string(key)
    if wanted is None or not isinstance(receiver, ast.Dict):
        return False
    return any(_literal_string(spelled) == wanted for spelled in receiver.keys)


def _resolve_getattr(
    call: ast.Call, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Resolve ``getattr(subprocess, "run")`` and the shapes that wear it."""
    owner, attr = call.args[0], call.args[1]
    if isinstance(attr, ast.Constant) and attr.value in _CALLABLE_ALIASES:
        # ``getattr(subprocess.run, "__call__")`` is ``subprocess.run``, and
        # the owner here can be any expression, not just a module.
        return _resolve_callable(owner, modules, functions)
    origin = modules.get(owner.id) if isinstance(owner, ast.Name) else None
    if origin is None:
        return None
    if not isinstance(attr, ast.Constant):
        # ``getattr(subprocess, name)`` hides which entry point it reaches.
        # Nothing in this repository needs that, so the safe reading is that
        # it reaches one of them.
        return _DYNAMIC
    return _entry_point(origin, attr.value)


def _resolve_operator_getter(
    call: ast.Call, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Resolve ``attrgetter("run")(subprocess)`` and the shapes that wear it.

    Every one of these spells the thing it reaches as an argument handed to a
    factory and the thing it reads from as the argument of the object that
    factory returns, so both halves are in the source with no dot between
    them. The outer call's ``func`` is itself a call, which is what separates
    this shape from every other one resolved here.

    ``itemgetter`` selects an element rather than an attribute, so the owner
    is a container and resolving it is the whole job. The two attribute
    factories need the owner to be a module, and a computed attribute on one
    reaches some entry point of it: the owner proves a subprocess module is in
    play exactly as it does for ``getattr``, so refusing the pair outright
    left ``attrgetter(name)(subprocess)`` unflagged while the ``getattr``
    spelling of the same thing was caught.
    """
    factory = call.func
    if not isinstance(factory, ast.Call) or not call.args:
        return None
    owner = call.args[0]
    label = _operator_label(factory, functions)
    if label == _OPERATOR_SELECTOR:
        return _resolve_callable(owner, modules, functions)
    if label not in _OPERATOR_GETTERS or not factory.args:
        return None
    origin = modules.get(owner.id) if isinstance(owner, ast.Name) else None
    if origin is None:
        return None
    attr = factory.args[0]
    if not isinstance(attr, ast.Constant):
        return _DYNAMIC
    return _entry_point(origin, attr.value)


def _operator_label(factory: ast.Call, functions: dict[str, str]) -> str:
    """Return the canonical :mod:`operator` factory *factory* builds with.

    An import alias renames the factory and nothing else, so the local
    spelling has to be translated back before any table can be consulted.
    A name that was never imported from :mod:`operator` answers with itself,
    which leaves ``operator.itemgetter(0)`` and every unrelated call reading
    exactly as they did.
    """
    label = _call_label(factory)
    return functions.get(_OPERATOR_ALIAS + label, label)


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
        for resolved in (_resolve_callable(value, modules, functions) for value in values)
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


def _entry_point(origin: str | None, attr: object) -> str | None:
    """Return the entry point that ``origin.attr`` names, or ``None``.

    One table serving the two syntaxes that reach a module attribute: the
    plain ``os.popen`` form and the ``getattr(os, "popen")`` form. Holding the
    mapping in a single place is what stops those two from drifting apart,
    which is exactly how ``getattr`` kept reaching ``os.popen`` unguarded
    while the attribute form was closed.
    """
    if origin == "subprocess" and attr in _SUBPROCESS_ATTRS:
        return str(attr)
    if origin == "os" and attr == "popen":
        return _OS_POPEN
    return None


def _attribute(
    node: ast.Attribute, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Return the entry point ``owner.attr`` names, or ``None``.

    An attribute owner answers with its own attribute name, because a module
    parked on a class attribute is reached that way: ``Holder.sp.run`` is
    ``subprocess.run`` whenever ``sp`` is bound to the module. Reading only a
    bare owner left that spelling unresolved, and the same reasoning already
    governs :func:`_keywords_owner`.
    """
    if node.attr in _CALLABLE_ALIASES:
        return _resolve_callable(node.value, modules, functions)
    spelling = _owner_spelling(node.value)
    if spelling is not None:
        found = _entry_point(modules.get(spelling), node.attr)
        if found is not None:
            return found
    # No partial filter here, unlike the bare-name branch in the caller. The
    # sentinel is only ever written for an imported name, and every attribute
    # binding is resolved through that branch, which drops it.
    return functions.get(_ATTRIBUTE + node.attr)


def _owner_spelling(node: ast.expr) -> str | None:
    """Return the name an owner expression is spelled with, or ``None``."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


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
        return None if resolved == _PARTIAL else resolved
    if isinstance(node, ast.Attribute):
        return _attribute(node, modules, functions)
    if isinstance(node, ast.Call):
        return _resolve_indirect(node, modules, functions)
    if isinstance(node, ast.NamedExpr):
        # ``(r := subprocess.run)(...)`` binds and calls in one expression.
        return _resolve_callable(node.value, modules, functions, containers)
    elements = _element_expressions(node)
    if elements is not None:
        return _resolve_elements(elements, modules, functions)
    return None


def _namespace_key(target: ast.expr) -> str | None:
    """Return the global name a write through ``globals()`` or ``vars()`` binds.

    ``globals()["runner"] = subprocess.run`` is a plain module-level binding
    wearing a subscript, because the mapping those calls return is the module
    namespace rather than a container living inside it. Reading it as a
    container write would taint a name that does not exist.

    Only a constant key is read. A computed one names something this scan
    cannot spell, so there is no key to bind it under.
    """
    if not isinstance(target, ast.Subscript) or not isinstance(target.value, ast.Call):
        return None
    if _call_label(target.value) not in _NAMESPACE_CALLS or target.value.args:
        return None
    key = target.slice
    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
        return None
    return key.value


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
    namespaced = _namespace_key(target)
    if namespaced is not None:
        # ``globals()["runner"] = subprocess.run`` writes into the module
        # namespace itself, so it creates an ordinary global rather than
        # filling a container. The key is the name the rest of the file calls.
        return [(namespaced, value)]
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

    Two items of the same shape bind the same names to the same values, so
    reading the second teaches the scan nothing. Skipping it bounds the work
    at one read per distinct item rather than one per item, which matters
    because a target of ``width`` names against ``width`` items would
    otherwise emit ``width`` squared bindings for the resolution queue.

    Items that differ still cost one read each, so a wide target over a wide
    literal of distinct items stays quadratic. That is left alone rather than
    capped, because a cap would drop real bindings to buy speed in a shape
    that does not occur: across the 319 files this guard scans there are 1246
    loops, 241 with a tuple target and 52 over a literal, and the largest
    names by items product in any of them is nine.
    """
    if not isinstance(iterable, (ast.List, ast.Tuple, ast.Set)):
        return _unpack(target, iterable)
    found: list[tuple[str, ast.expr]] = []
    seen: set[str] = set()
    for item in iterable.elts:
        shape = ast.dump(item)
        if shape in seen:
            continue
        seen.add(shape)
        found.extend(_unpack(target, item))
    return found


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
        return _setattr_binding(call)
    if not isinstance(call.func.value, ast.Name):
        return []
    name = call.func.value.id
    handed = [*call.args, *(keyword.value for keyword in call.keywords)]
    return [(name, value) for value in handed]


def _setattr_binding(call: ast.Call) -> list[tuple[str, ast.expr]]:
    """Pair the attribute ``setattr`` writes with the value it writes there.

    ``setattr(holder, "runner", subprocess.run)`` binds an attribute exactly as
    ``holder.runner = subprocess.run`` does, and the second spelling is already
    read. Which object holds it is not modelled either way, so both land under
    the same attribute key.

    A computed attribute name is refused. There is no key to bind it under, and
    guessing one would answer for an attribute the source never writes.
    """
    if _call_label(call) != "setattr" or len(call.args) != 3:
        return []
    name = call.args[1]
    if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
        return []
    return [(_ATTRIBUTE + name.value, call.args[2])]


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
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
            )
    return found


def _class_scope(body: list[ast.stmt]) -> list[ast.stmt]:
    """Return every statement of *body* that runs in the same class namespace.

    A class body is executed like any other block, so a binding inside an
    ``if`` or a ``try`` lands in the class namespace exactly as one at the top
    level does. A nested function or class opens its own namespace, and both
    already have their own handling, so the walk stops at them rather than
    reading a method local as a class attribute.
    """
    found: list[ast.stmt] = []
    for statement in body:
        if isinstance(statement, _OWN_SCOPE):
            continue
        found.append(statement)
        for field in ("body", "orelse", "finalbody"):
            found.extend(_class_scope(getattr(statement, field, [])))
        for block in list(getattr(statement, "handlers", ())) + list(
            getattr(statement, "cases", ())
        ):
            found.extend(_class_scope(block.body))
    return found


def _nested_walrus(statement: ast.stmt) -> list[ast.NamedExpr]:
    """Return every walrus in *statement* that binds in the enclosing scope.

    A walrus binds wherever it appears, not only as a statement of its own, so
    an ``if`` test, a call argument and an operand of a boolean expression all
    leave a name behind. The walk stops at a nested function, class or lambda,
    because a walrus inside one of those binds in that scope instead and
    reading it here would report a local as a class attribute.
    """
    found: list[ast.NamedExpr] = []
    stack: list[ast.AST] = [statement]
    while stack:
        for child in ast.iter_child_nodes(stack.pop()):
            if isinstance(child, _OWN_SCOPE):
                continue
            if isinstance(child, ast.NamedExpr):
                found.append(child)
            stack.append(child)
    return found


def _class_bindings(node: ast.ClassDef) -> list[tuple[str, ast.expr]]:
    """Pair every attribute a class body binds with the value it receives.

    A class body binds attributes without ever naming ``self``, so the names
    are recorded under the attribute prefix and read back the same way. Every
    binding shape counts, not just the plain assignment: an annotation, a
    walrus, an in-place extension, a loop variable and a match capture all
    outlive their statement and leave a class attribute behind.
    """
    found: list[tuple[str, ast.expr]] = []
    for statement in _class_scope(node.body):
        for named in _nested_walrus(statement):
            found.extend((_ATTRIBUTE + name, bound) for name, bound in _assigned(named))
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            pairs = _assigned(statement)
        elif isinstance(statement, (ast.For, ast.AsyncFor)):
            pairs = _iterated(statement.target, statement.iter)
        elif isinstance(statement, ast.Match):
            pairs = _captured(statement)
        else:
            continue
        found.extend((_ATTRIBUTE + name, bound) for name, bound in pairs)
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
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            # ``with nullcontext(subprocess.run) as runner`` binds a name the
            # same way an assignment would. What ``__enter__`` returns is not
            # knowable in general, so the target takes the context expression
            # and the transparent wrappers are what make it resolve.
            found.extend(
                pair
                for item in node.items
                if item.optional_vars is not None
                for pair in _unpack(item.optional_vars, item.context_expr)
            )
        elif isinstance(node, ast.ClassDef):
            found.extend(_class_bindings(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # A lambda takes defaults exactly as a def does, and the parameter
            # is in scope for the body that calls it.
            found.extend(_defaults(node.args))
    return found


def _containers(tree: ast.AST, bindings: list[tuple[str, ast.expr]]) -> dict[str, _Container]:
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
    """Collect the module aliases and imported names that reach an entry point.

    ``import subprocess as sp`` and ``from subprocess import run`` are both
    ordinary Python, and an owner-name check that only knows the literal word
    ``subprocess`` misses each of them. ``os`` is tracked the same way, because
    ``os.popen`` decodes with the locale codec and offers no parameter to pin
    it, so an aliased import of it is the worst case this scan has.
    """
    modules = {name: name for name in _ENTRY_MODULES}
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _ENTRY_MODULES:
                    modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            wanted = _IMPORTED_NAMES.get(node.module or "", {})
            for alias in node.names:
                if alias.name == "*":
                    # ``from subprocess import *`` binds every public name
                    # under its own spelling, and no alias is possible.
                    functions.update(wanted)
                elif alias.name in wanted:
                    functions[alias.asname or alias.name] = wanted[alias.name]
                elif node.module == "operator" and alias.name in _OPERATOR_FACTORIES:
                    functions[_OPERATOR_ALIAS + (alias.asname or alias.name)] = alias.name
    return modules, functions


def _dependents(groups: dict[int, tuple[ast.expr, list[str]]]) -> dict[str, list[int]]:
    """Map each name a binding group reads to the groups that read it."""
    found: dict[str, list[int]] = {}
    for key, (value, _) in groups.items():
        for free in {node.id for node in ast.walk(value) if isinstance(node, ast.Name)}:
            found.setdefault(free, []).append(key)
    return found


def _module_source(node: ast.expr, containers: dict[str, _Container]) -> list[str]:
    """Return every name *node* may evaluate to, opening any container on the way.

    ``sp = subprocess`` names the module outright, but ``[subprocess][0]`` and
    ``HOLDER[0]`` reach the same module object through a container, and an
    attribute read off the result is an ordinary entry-point call. Reading only
    a bare name left both unflagged.

    A subscript chain is unwound in a loop for the same reason it is in
    :func:`_resolve_callable`: the parser caps no depth, so recursion crashes.
    """
    while isinstance(node, ast.Subscript):
        selected = _element(node, containers)
        node = node.value if selected is None else selected
    if isinstance(node, ast.Name):
        return [node.id]
    elements = _element_expressions(node)
    if elements is None:
        return []
    return [item.id for item in elements if isinstance(item, ast.Name)]


def _module_aliases(
    bindings: list[tuple[str, ast.expr]], modules: dict[str, str], containers: dict[str, _Container]
) -> None:
    """Extend *modules* with the names bound to a module already in it.

    ``import subprocess`` and ``sp = subprocess`` reach the same entry points,
    and only the first is an import statement, so the binding pass has to carry
    the second. A chain is resolved by repeating until nothing new is learned,
    which terminates because every pass that changes anything adds a name and
    the supply of names is finite.

    What each binding may name is read once, before the repeats begin. The
    source of a binding cannot change between passes, only what is known about
    it, so reading it inside the loop pays the walk once per pass for an answer
    that never moves: a file of several thousand bindings took minutes that
    way against seconds this way.

    The first binding of a name wins, matching how callables are recorded. A
    name rebound away from a module keeps reading as that module, which costs
    a redundant ``encoding="utf-8"`` rather than a missed decode.
    """
    sources = [(name, _module_source(value, containers)) for name, value in bindings]
    learned = True
    while learned:
        learned = False
        for name, candidates in sources:
            if name in modules:
                continue
            module = _first_module(candidates, modules)
            if module is None:
                continue
            modules[name] = module
            learned = True


def _first_module(sources: list[str], modules: dict[str, str]) -> str | None:
    """Return the first of *sources* that already names a subprocess module."""
    for source in sources:
        module = modules.get(source)
        if module is not None:
            return module
    return None


def _subprocess_names(
    tree: ast.Module,
) -> tuple[dict[str, str], dict[str, str], dict[str, _Container], frozenset[int]]:
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
    _module_aliases(bindings, modules, containers)
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
            _carry_partial(name, value, functions, resolved, containers)
            queue.extend(dependents.get(name, ()))
    rewritten = _aliased_writes(_keyword_writes(tree), bindings, containers)
    for name in rewritten:
        # A pin recorded at construction only answers for the partial while
        # the keywords it recorded are still the ones the partial holds.
        functions.pop(_PINNED_PARTIAL + name, None)
    repinned = frozenset(id(value) for name, value in bindings if name in rewritten)
    return modules, functions, containers, repinned


def _aliased_writes(
    written: set[str], bindings: list[tuple[str, ast.expr]], containers: dict[str, _Container]
) -> set[str]:
    """Extend *written* with every other name for the same object.

    ``alias = runner`` binds one partial under two names, and
    ``alias.keywords["encoding"] = None`` rewrites the object, not the
    spelling. Invalidating only the name the write was spelled with left the
    pin recorded under the other name intact, so a call through the original
    still read as pinned while the codec had already been replaced.

    The relation is symmetric and transitive: the write may be spelled with
    either name, so both directions are linked and the closure is taken.
    """
    linked: dict[str, set[str]] = {}
    for name, value in bindings:
        for source in _alias_sources(value, containers):
            linked.setdefault(name, set()).add(source)
            linked.setdefault(source, set()).add(name)
    found = set(written)
    queue = list(found)
    while queue:
        for peer in linked.get(queue.pop(), ()):
            if peer not in found:
                found.add(peer)
                queue.append(peer)
    return found


def _keyword_writes(tree: ast.AST) -> set[str]:
    """Return every partial whose pre-bound keywords the file may rewrite.

    ``functools.partial`` keeps its keywords in an ordinary mutable dict and
    publishes it, so ``runner.keywords["encoding"] = None`` undoes a pin that
    the construction call recorded. Reading the construction alone would trust
    a codec the file went on to replace.

    Only writes count. A file that reads ``runner.keywords`` to log it has
    changed nothing, and dropping the pin there would ask for an encoding the
    partial already supplies.
    """
    mutated: set[str] = set()
    for node in ast.walk(tree):
        for target in _write_targets(node):
            owner = _keywords_owner(target)
            if owner is not None:
                mutated.add(owner)
    return mutated


def _write_targets(node: ast.AST) -> list[ast.expr]:
    """Return the expressions *node* writes through, ignoring what it reads.

    Three statement shapes reach a partial's keyword dict: an assignment or a
    delete lands on the dict or a key inside it, and a method call mutates it
    through the receiver. Each keeps its targets somewhere different, so they
    are collected here rather than at every use.
    """
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        # ``runner.keywords["encoding"] = None`` writes a key, while
        # ``runner.keywords = {}`` replaces the dict outright. The first hides
        # the attribute under a subscript, so both spellings are unwrapped.
        return [t.value if isinstance(t, ast.Subscript) else t for t in targets]
    if isinstance(node, ast.Delete):
        return [t.value if isinstance(t, ast.Subscript) else t for t in node.targets]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        # ``runner.keywords.update(...)`` and its siblings mutate through the
        # receiver. The read-only half of the dict interface does not, and
        # treating a lookup as a rewrite dropped a pin the file never touched,
        # which asked a correct call to spell the codec twice.
        return [] if node.func.attr in _READING_METHODS else [node.func.value]
    return []


def _keywords_owner(target: ast.expr) -> str | None:
    """Return the name whose ``keywords`` attribute *target* refers to.

    An attribute receiver answers with its own attribute name, because that is
    the name the construction was bound to: ``holder.runner.keywords["enc"]``
    rewrites whatever ``holder.runner`` holds, and the construction that filled
    it is spelled ``runner = ...`` or ``runner: ... = ...`` wherever it lives.
    Reading only a bare receiver left the attribute spelling of the same
    rewrite unflagged, so the pin it undid still counted.
    """
    if not isinstance(target, ast.Attribute) or target.attr != "keywords":
        return None
    owner = target.value
    if isinstance(owner, ast.Name):
        return owner.id
    return owner.attr if isinstance(owner, ast.Attribute) else None


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
    if _call_label(call) == "getattr":
        # ``getattr(os, "popen")`` only fetches. It decodes nothing until
        # something calls the result, and that call is the node this scan
        # flags instead. ``functools.partial`` is the opposite case above: it
        # fixes the codec where it is built, so it stays.
        return None
    return fallback


def _supplies_capture(call: ast.Call, modules: dict[str, str]) -> bool:
    """Report whether *call* asks for output to be captured.

    ``capture_output`` is read for truth, so any value the scan cannot rule
    out counts. A stream keyword counts on its own, because ``stdout=PIPE``
    captures with no ``capture_output`` anywhere in sight.
    """
    capture = _keyword(call, "capture_output")
    if capture is not None and not _is_literal_falsy(capture):
        return True
    return any(_is_capturing_stream(_keyword(call, name), modules) for name in ("stdout", "stderr"))


def _captures_text(
    call: ast.Call,
    functions: dict[str, str],
    target: str,
    modules: dict[str, str],
    containers: dict[str, _Container] | None = None,
) -> bool:
    """Report whether *call* may decode captured output into ``str``.

    Deliberately conservative. Anything other than a literal falsy value
    counts, because ``text=1`` and ``capture_output=flag`` both decode at
    runtime while reading as compliant to a check that only recognises
    ``True``.

    A ``functools.partial`` is read at both sites. Selecting text mode counts
    with no capture keyword, because the capture can be supplied at either
    end, and the same holds where the partial is called: the name bound to a
    partial carries whatever the definition pre-bound, so a call site adding
    ``text=True`` is reached even though the capture is nowhere in sight.
    Neither site alone can see the other's half. An entry point
    in :data:`_ALWAYS_CAPTURING_ATTRS` captures without being asked, so
    *target* has to be known here rather than inferred from the spelling at
    the call site.

    A ``**kwargs`` splat is treated as text mode outright when it cannot be
    read. The keywords it carries are not visible here, so ``text`` may be
    among them, and reading the absence of a literal keyword as proof of bytes
    mode is the hole an adversarial review walked through. One this scan can
    open answers for itself instead: ``**{"cwd": "."}`` spells a directory and
    nothing else, so flagging it asked a call that decodes nothing to pin a
    codec. Its readable keywords are folded in beside the written ones, which
    is what lets ``**{"text": True}`` still count.
    """
    call = _with_readable_splats(call, containers or {})
    if _splat_items(call, containers or {}):
        return True
    if len(call.args) > 1:
        # Only the command is ever passed positionally in this repository:
        # every one of the 1079 entry-point calls under scan passes exactly
        # one. A second positional lands in a parameter this scan does not
        # track by index, and ``stdout`` and ``universal_newlines`` are both
        # reachable that way, so the mode is unreadable and has to count.
        # Reading position by index instead would pin this scan to one
        # release's parameter order, which is the reason that was rejected.
        return True
    partial = _reaches_partial(_call_label(call), functions)
    if not any(_selects_text(_keyword(call, name)) for name in _TEXT_SELECTORS):
        return False
    if partial or target in _ALWAYS_CAPTURING_ATTRS:
        return _inherits_capture(call, functions, modules) if partial else True
    return _supplies_capture(call, modules)


def _inherits_capture(call: ast.Call, functions: dict[str, str], modules: dict[str, str]) -> bool:
    """Report whether a partial's pre-bound capture survives to reach *call*.

    A call site overrides the keyword it repeats, so
    ``partial(run, capture_output=True)`` called with ``capture_output=False``
    opens no pipe and decodes nothing. Verified at runtime, where that pairing
    left ``stdout`` as ``None`` rather than a captured string.

    Only the keywords the construction was seen to supply can be shadowed.
    Where none were recorded the construction was either silent or unreadable,
    and those are not distinguishable here, so the capture is assumed. That
    keeps ``partial(run, stdout=PIPE)`` called with ``capture_output=False``
    flagged, because turning off a keyword the partial never set changes
    nothing about the pipe it did.

    A keyword the call site does not repeat keeps the state the construction
    gave it, so ``partial(run, capture_output=False)`` stays quiet whether or
    not the call site repeats the off value. Spelled directly that call was
    already quiet, and routing it through a partial should not change the
    answer.
    """
    inherited = functions.get(_CAPTURING_PARTIAL + _call_label(call))
    if inherited is None:
        return True
    return any(_capture_survives(call, item, modules) for item in inherited.split(","))


def _capture_survives(call: ast.Call, item: str, modules: dict[str, str]) -> bool:
    """Report whether one pre-bound capture keyword still captures at *call*.

    A call site overrides the keyword it repeats, so where one is supplied the
    supplied value is the whole answer. A keyword the call site leaves alone
    keeps the state the construction gave it.
    """
    name, _, state = item.partition(_CAPTURE_STATE)
    supplied = _keyword(call, name)
    if supplied is None:
        return state == _CAPTURE_ON
    if name == "capture_output":
        return not _is_literal_falsy(supplied)
    return _is_capturing_stream(supplied, modules)


def _literal_string(node: ast.expr | None) -> str | None:
    """Return the string *node* is known to be, or ``None``.

    An f-string with no placeholder is a string literal wearing a prefix, and
    the parser keeps it as a joined string rather than folding it. Reading only
    ``ast.Constant`` therefore rejects a codec name that is spelled correctly,
    which costs a false alarm on a call that is already right. A placeholder
    anywhere makes the value unknowable here, so the whole string is refused.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        # ``"utf" + "-8"`` is one constant folded by hand. Both sides have to
        # be readable, so a name on either side refuses the whole value.
        left, right = _literal_string(node.left), _literal_string(node.right)
        return None if left is None or right is None else left + right
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for piece in node.values:
        if not isinstance(piece, ast.Constant) or not isinstance(piece.value, str):
            return None
        parts.append(piece.value)
    return "".join(parts)


def _names_utf8(node: ast.expr | None) -> bool:
    """Report whether *node* is a literal naming the UTF-8 codec.

    The string is compared the way the interpreter compares it, through
    :func:`codecs.lookup`, because ``UTF-8``, ``utf8`` and ``UTF_8`` all select
    the same codec and flagging them is a false positive on a correct call.
    Normalising does not widen the check: ``utf-8-sig`` resolves to its own
    name, so it stays out, and it quietly strips a byte order mark.
    """
    name = _literal_string(node)
    if name is None:
        return False
    try:
        return codecs.lookup(name).name == _PINNED_CODEC
    except LookupError:
        # An unknown codec name raises at runtime before anything decodes, so
        # nothing is pinned and nothing is read.
        return False


def _mapping_items(
    node: ast.expr, containers: dict[str, _Container], depth: int = 0
) -> list[tuple[str, ast.expr]]:
    """Return the keywords a mapping expression carries, marking what it hides.

    Unreadability is recorded as an :data:`_OPAQUE_KEY` entry at the position
    the unreadable segment sat, not as a verdict over the whole mapping. That
    distinction is what runtime merge order demands: ``{**opaque, "encoding":
    "utf-8"}`` decodes as UTF-8 whatever ``opaque`` holds, while ``{"encoding":
    "utf-8", **opaque}`` may not. Discarding the position read the first one as
    unpinned, which it never is.

    An empty list still means readable and empty, and is not the same as an
    opaque entry: a mapping this scan opened and found nothing in carries
    nothing, while one it could not open may carry any codec at all.

    Three spellings are read. A literal, a ``dict(...)`` call, and a name bound
    once to a literal that nothing writes to, which is the same guarantee
    subscripting a container already relies on.
    """
    if depth > _MAPPING_DEPTH:
        # A mapping nested deeper than this is not something a real call site
        # writes, and refusing it is what bounds the recursion.
        return [(_OPAQUE_KEY, node)]
    if isinstance(node, ast.Name):
        literal = containers.get(node.id)
        if literal is None:
            return [(_OPAQUE_KEY, node)]
        return _mapping_items(literal, containers, depth + 1)
    if isinstance(node, ast.Dict):
        return _dict_items(node, containers, depth)
    if isinstance(node, ast.Call) and _call_label(node) == "dict" and not node.args:
        return _keyword_items(node.keywords, containers, depth)
    return [(_OPAQUE_KEY, node)]


def _dict_items(
    node: ast.Dict, containers: dict[str, _Container], depth: int
) -> list[tuple[str, ast.expr]]:
    """Return the keywords a dict literal carries, following any merge in it.

    A ``None`` key is how the parser spells ``{**inner}``, so the merged
    mapping is opened in turn. A key that is not a literal string names a
    keyword this scan cannot spell, so it is recorded as opaque where it sits:
    it may be the encoding, and anything spelled after it still wins.
    """
    items: list[tuple[str, ast.expr]] = []
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            items.extend(_mapping_items(value, containers, depth + 1))
            continue
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            items.append((_OPAQUE_KEY, value))
            continue
        items.append((key.value, value))
    return items


def _keyword_items(
    keywords: list[ast.keyword], containers: dict[str, _Container], depth: int
) -> list[tuple[str, ast.expr]]:
    """Return the keywords a ``dict(...)`` call carries, following any splat."""
    items: list[tuple[str, ast.expr]] = []
    for keyword in keywords:
        if keyword.arg is None:
            items.extend(_mapping_items(keyword.value, containers, depth + 1))
            continue
        items.append((keyword.arg, keyword.value))
    return items


def _with_readable_splats(call: ast.Call, containers: dict[str, _Container]) -> ast.Call:
    """Return *call* with every fully readable mapping splat written out.

    A splat this scan can open is not an unknown. Rewriting it into ordinary
    keywords lets every reader below work on one shape instead of asking each
    of them to open the mapping again, and it keeps an unreadable splat in
    place so the callers that refuse one still see it.
    """
    if not any(keyword.arg is None for keyword in call.keywords):
        return call
    keywords: list[ast.keyword] = []
    for keyword in call.keywords:
        if keyword.arg is not None:
            keywords.append(keyword)
            continue
        items = _mapping_items(keyword.value, containers)
        if any(name == _OPAQUE_KEY for name, _ in items):
            keywords.append(keyword)
            continue
        keywords.extend(ast.keyword(arg=name, value=value) for name, value in items)
    opened = ast.Call(func=call.func, args=call.args, keywords=keywords)
    return ast.copy_location(opened, call)


def _splat_groups(
    call: ast.Call, containers: dict[str, _Container]
) -> list[list[tuple[str, ast.expr]]]:
    """Return each mapping splat on *call* separately, in the order written.

    Kept apart rather than flattened, because the two levels merge under
    different rules. Inside one mapping display the later key wins silently,
    which is why :func:`_mapping_items` records position. Across two splats on
    the same call a repeated key raises ``TypeError`` before anything runs, so
    a later splat can never be the one that overwrote an earlier key in a
    program that executes at all.
    """
    return [
        _mapping_items(keyword.value, containers)
        for keyword in call.keywords
        if keyword.arg is None
    ]


def _splat_value(
    groups: list[list[tuple[str, ast.expr]]], key: str
) -> tuple[ast.expr | None, bool]:
    """Return the value *key* survives with across *groups*, and whether it is hidden.

    A readable spelling wins over an unreadable splat written after it. The
    interpreter would raise on the duplicate, so the only program that runs is
    the one where the unreadable splat does not carry *key* at all.
    """
    found: ast.expr | None = None
    hidden = False
    for group in groups:
        value = _last_value(group, key)
        if value is not None:
            found = value
        elif _shadows(group, key):
            hidden = True
    return found, (hidden and found is None)


def _splat_items(call: ast.Call, containers: dict[str, _Container]) -> list[tuple[str, ast.expr]]:
    """Return the keywords every mapping splat on *call* carries, in order.

    An empty list means the call has no splat, or none that carried anything.
    A splat that could not be read contributes an :data:`_OPAQUE_KEY` entry
    where it sat, which is what keeps an opaque ``**kwargs`` blocking while
    letting a codec spelled after it survive.
    """
    items: list[tuple[str, ast.expr]] = []
    for keyword in call.keywords:
        if keyword.arg is None:
            items.extend(_mapping_items(keyword.value, containers))
    return items


def _last_value(items: list[tuple[str, ast.expr]], key: str) -> ast.expr | None:
    """Return the value *key* ends up with once the mappings are merged.

    A later mapping overwrites an earlier one, which is how ``{**base, **more}``
    behaves at runtime, so the last occurrence is the one that survives. An
    opaque entry may carry *key* itself, so it clears whatever came before it.
    """
    found: ast.expr | None = None
    for name, value in items:
        if name == key:
            found = value
        elif name == _OPAQUE_KEY:
            found = None
    return found


def _shadows(items: list[tuple[str, ast.expr]], key: str) -> bool:
    """Report whether an unreadable segment sits at or after the last *key*.

    :func:`_last_value` returning ``None`` cannot tell absent from hidden, and
    the two answers differ: nothing carried leaves the call site's own keyword
    to decide, while something hidden means the codec is unknowable.
    """
    blocked = False
    for name, _ in items:
        if name == key:
            blocked = False
        elif name == _OPAQUE_KEY:
            blocked = True
    return blocked


def _pins_utf8(call: ast.Call) -> bool:
    """Report whether *call* proves its codec is UTF-8 at the call site.

    ``encoding=None`` is an explicit request for the locale codec and a name or
    attribute cannot be resolved statically, so only a literal string counts.
    """
    return _names_utf8(_keyword(call, "encoding"))


def _codec_is_pinned(
    call: ast.Call,
    functions: dict[str, str],
    repinned: frozenset[int] = frozenset(),
    containers: dict[str, _Container] | None = None,
) -> bool:
    """Report whether *call* decodes as UTF-8, counting a pin it inherited.

    A partial fixes the codec where it is built, and the site that calls it
    carries no ``encoding`` keyword to read. The inherited pin only survives
    while the call site stays silent, because a keyword there overrides the
    pre-bound one: ``partial(run, encoding="utf-8")`` called with
    ``encoding="latin-1"`` decodes as latin-1. Verified at runtime, where the
    inherited form returned ``str`` under an ASCII parent locale.

    A construction listed in *repinned* keeps no pin at all. Its keywords are
    rewritten somewhere below it, so the codec spelled here is not the one the
    partial carries by the time anything calls it.

    A splat is opened rather than refused outright. ``**{"encoding": "utf-8"}``
    reaches the interpreter as the keyword it spells, so reading it as proof
    of nothing asks a compliant call to repeat itself. One that cannot be
    opened blocks only what it can still overwrite, and at a call site that is
    nothing spelled in another splat: ``f(**a, **b)`` sharing a key raises
    ``TypeError`` before ``f`` is entered, so any program that runs at all has
    a readable codec no later splat overrode. Inside one display the ordinary
    left-to-right merge still applies, which is why the splats are read apart.
    """
    if id(call) in repinned:
        return False
    if _pins_utf8(call):
        return True
    splatted, hidden = _splat_value(_splat_groups(call, containers or {}), "encoding")
    if hidden:
        return False
    if splatted is not None:
        return _names_utf8(splatted)
    if _keyword(call, "encoding") is not None:
        return False
    return _PINNED_PARTIAL + _call_label(call) in functions


def _arguments_reaching(call: ast.Call, functions: dict[str, str]) -> ast.Call:
    """Return the call whose arguments reach the entry point *call* runs.

    ``methodcaller("run", cmd, text=True)(subprocess)`` stores its arguments on
    the factory and takes only the owner at the site that runs them, so the
    keywords deciding the mode sit one call inward. Reading the outer call
    finds a lone positional and concludes nothing decodes.

    Its ``attrgetter`` twin needs none of this: that one only fetches, so the
    call that runs the attribute is written out in full and carries its own
    arguments. Every other shape likewise answers for itself.
    """
    factory = call.func
    if not isinstance(factory, ast.Call) or _operator_label(factory, functions) != "methodcaller":
        return call
    reaching = ast.Call(func=factory.func, args=factory.args[1:], keywords=factory.keywords)
    return ast.copy_location(reaching, call)


def unpinned_lines(source: str) -> list[int]:
    """Return the line numbers of text-capturing calls that do not pin UTF-8."""
    tree = ast.parse(source)
    modules, functions, containers, repinned = _subprocess_names(tree)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _target(node, modules, functions, containers)
        if target is None:
            continue
        if target == _OS_POPEN:
            # os.popen has no encoding parameter at all, so the only compliant
            # move is to not use it.
            offenders.append(node.lineno)
            continue
        reading = _arguments_reaching(node, functions)
        if target not in _DECODES_UNCONDITIONALLY and not _captures_text(
            reading, functions, target, modules, containers
        ):
            continue
        if not _codec_is_pinned(reading, functions, repinned, containers):
            offenders.append(node.lineno)
    return sorted(offenders)


def _python_sources() -> list[Path]:
    """Return every Python file under ``scripts/``, skipping caches."""
    return [path for path in sorted(_SCRIPTS_DIR.rglob("*.py")) if "__pycache__" not in path.parts]


def test_every_capturing_call_under_scripts_pins_utf8() -> None:
    """No text-capturing subprocess call may inherit the locale's codec."""
    offenders: list[str] = []
    for path in _python_sources():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        offenders.extend(f"{rel}:{line}" for line in unpinned_lines(path.read_text("utf-8")))
    assert offenders == [], (
        'text-capturing subprocess calls must pass encoding="utf-8": ' + ", ".join(offenders)
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
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, errors='ignore')",
            "errors alone selects text mode and leaves the codec to the locale",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, encoding='latin-1')",
            "encoding alone selects text mode and names a codec that is not UTF-8",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=flag)",
            "a text value the scan cannot evaluate may well be true at runtime",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, encoding=CODEC)",
            "a codec named indirectly is not proof that the codec is UTF-8",
        ),
        (
            "import subprocess\n"
            "subprocess.run(['x'], stdout=None, stderr=subprocess.PIPE, text=True)",
            "each stream keyword is read on its own, so a quiet stdout hides nothing",
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
            "import subprocess\n"
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
            "import subprocess\nH = [subprocess.check_call, subprocess.run]\n"
            'H[0](["x"], capture_output=True, text=True)',
            "a table nobody writes to still reads one element",
        ),
        (
            "import subprocess\nH = [subprocess.check_call, subprocess.run]\n"
            "G = [subprocess.run]\nG[0] = subprocess.run\n"
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
            "import subprocess\n_run = subprocess.run\n"
            '_run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "an alias that pins the codec is exactly as safe as the original",
        ),
        (
            "import functools, subprocess\n"
            '_run = functools.partial(subprocess.run, text=True, encoding="utf-8")',
            "a partial that pins the codec has nothing left to decide",
        ),
        (
            "import functools, subprocess\n"
            "_popen = functools.partial(subprocess.Popen, stdout=subprocess.PIPE)",
            "a partial that never selects text mode returns bytes",
        ),
        (
            'import json\n_loads = json.loads\n_loads("{}")',
            "binding an unrelated callable is ordinary Python",
        ),
        (
            "import subprocess\nrunners = [subprocess.run, subprocess.Popen]\n"
            'runners[0](["echo", "hi"])',
            "two entry points that both need keywords decode nothing without one",
        ),
        (
            "import subprocess\nclass C:\n    def __init__(self):\n"
            "        self.run = subprocess.run\n"
            'C().run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "an attribute that pins the codec is as safe as a name that does",
        ),
        (
            "import json\nclass C:\n    def __init__(self):\n"
            "        self.load = json.loads\n"
            'C().load("{}", capture_output=True, text=True)',
            "an attribute holding an unrelated callable is ordinary Python",
        ),
        (
            "import subprocess\ndef go(runner=subprocess.run):\n"
            '    runner(["x"], capture_output=True, text=True, encoding="utf-8")',
            "a default argument that pins the codec needs no second look",
        ),
        (
            "import subprocess\nfrom mylib import render\n"
            "runner, drawer = subprocess.run, render\n"
            'drawer("x", capture_output=True, text=True)',
            "unpacking pairs by position, so the neighbour keeps its own identity",
        ),
        (
            "import subprocess\nrunners = [subprocess.run, subprocess.Popen]\n"
            'runners[0](["x"], capture_output=True, text=True, encoding="utf-8")',
            "a container call that pins the codec is as safe as a direct one",
        ),
        (
            'from functools import partial as p\nx = p(open, "f")\nx()',
            "a partial over an unrelated callable is not a subprocess call",
        ),
        (
            'from functools import partial as p\nq = p\nq(open, "f")()',
            "the alias itself is functools.partial, not a subprocess entry point",
        ),
        (
            "from functools import partial as p\n"
            "def fetch(cmd, text=False):\n    return cmd\n"
            'go = p(fetch, text=True)\ngo(["x"])',
            "a partial over a local function that takes text is not subprocess",
        ),
        (
            'import shutil\n_run = shutil.run\n_run(["x"], capture_output=True, text=True)',
            "an alias of a same-named function on another module is not ours",
        ),
        (
            "from mypackage import run, getoutput\n"
            'run(["x"], capture_output=True, text=True)\ngetoutput("x")',
            "a from-import of a same-named function elsewhere is not ours",
        ),
        (
            "import subprocess\n"
            'getattr(subprocess, "PIPE")\n'
            'getattr(shutil, "run")(["x"], capture_output=True, text=True)',
            "getattr only counts when it names our module and our function",
        ),
        (
            'import os\ngetattr(os, "run")(["x"], capture_output=True, text=True)',
            "a subprocess attribute name on the os module is not our entry point",
        ),
        (
            'import os\nf = getattr(os, "popen")',
            "fetching os.popen through getattr decodes nothing until it is called",
        ),
        (
            'import subprocess\nsubprocess.run.__call__(["x"], '
            'capture_output=True, encoding="utf-8")',
            "forwarding through __call__ does not lose a pinned codec",
        ),
        (
            'local.__call__(["x"], capture_output=True, text=True)',
            "__call__ on an unrelated object reaches no entry point",
        ),
        (
            'getattr(local, "__call__")(["x"], capture_output=True, text=True)',
            "a dunder forward off an unrelated object is still unrelated",
        ),
        (
            "import subprocess\nf = subprocess.run.__get__\n"
            'f(["x"], capture_output=True, text=True)',
            "__get__ hands back a binding, not the callable, so it runs nothing",
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
            "import subprocess\nR = [local, subprocess.run]\n"
            'R[0](["x"], capture_output=True, text=True)',
            "a literal index selects one element, and this one is not an entry point",
        ),
        (
            "import subprocess\nR = [subprocess.run, local]\n"
            'R[-1](["x"], capture_output=True, text=True)',
            "a negative index counts from the end of the literal",
        ),
        (
            'import subprocess\nH = {"a": local, "b": subprocess.run}\n'
            '(f := H["a"])(["x"], capture_output=True, text=True)',
            "a walrus over an indexed table still selects the one element",
        ),
        (
            "import subprocess\nH: object = [subprocess.check_call, subprocess.run]\n"
            "H: object\n"
            'H[0](["x"], capture_output=True, text=True)',
            "a bare annotation declares a type and binds nothing",
        ),
        (
            "import subprocess\nH = [[subprocess.check_call]]\ndel H[0][1]\n"
            'H[0](["x"], capture_output=True, text=True)',
            "a delete may reach through a subscript the scan cannot name",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n    case _:\n"
            '        _(["x"], capture_output=True, text=True)',
            "a wildcard pattern matches everything and captures nothing",
        ),
        (
            "import subprocess\nmatch subprocess.check_call:\n    case runner:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "a capture is only as loud as the subject it reads",
        ),
        (
            "import subprocess\n"
            "for label, runner in [(subprocess.check_call, subprocess.run)]:\n"
            '    label(["x"], capture_output=True, text=True)',
            "a loop target takes one column of the pairs, not both",
        ),
        (
            "import subprocess\n"
            "for label, runner in ((subprocess.check_call, 1), (subprocess.run, 2)):\n"
            '    runner(["x"], capture_output=True, text=True)',
            "the second column of every pair is what the second name reads",
        ),
        (
            "import subprocess\n"
            "for label, runner in {(subprocess.check_call, subprocess.run)}:\n"
            '    label(["x"], capture_output=True, text=True)',
            "a set literal of pairs still has columns",
        ),
        (
            "import subprocess\n"
            "runner = other = subprocess.check_output\n"
            "runner = subprocess.run\n"
            'runner(["x"], text=True)',
            "the first binding of a name wins over a later group it shares",
        ),
        (
            "import subprocess\n"
            "class C:\n"
            "    def m(self):\n        runner = subprocess.run\n"
            'def go(c):\n    c.runner(["x"], capture_output=True, text=True)',
            "a method local is not a class attribute",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, errors=None)",
            "errors=None asks for bytes, exactly as omitting it does",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, encoding=None)",
            "encoding=None asks for bytes, exactly as omitting it does",
        ),
        (
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, errors='ignore', encoding='utf-8')",
            "errors with a pinned codec decodes under UTF-8",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], errors='ignore')",
            "text mode with nothing captured decodes nothing",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=None)",
            "text=None is falsy and leaves the pipes in bytes mode",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=0)",
            "text=0 is falsy and leaves the pipes in bytes mode",
        ),
        (
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, universal_newlines=None)",
            "the legacy spelling is falsy under None just as the new one is",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, encoding="UTF-8")',
            "codec lookup folds case, so UTF-8 is the pinned codec",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, encoding="utf8")',
            "codec lookup ignores the hyphen, so utf8 is the pinned codec",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, encoding="UTF_8")',
            "codec lookup folds the underscore too, so UTF_8 is the pinned codec",
        ),
        (
            "import subprocess\n"
            "class C:\n    async def m(self):\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a name bound in an async method is a local, not a class attribute",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], stdout=None, text=True)',
            "stdout=None inherits the parent's stream, so nothing is captured to decode",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], stderr=None, text=True)',
            "stderr=None inherits the parent's stream, so nothing is captured to decode",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=None, text=True)',
            "capture_output=None is falsy, so subprocess never opens the pipes",
        ),
        (
            "import subprocess\n"
            "class C:\n    def g(self):\n        if (runner := subprocess.run):\n"
            "            pass\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus inside a method binds a method local, not a class attribute",
        ),
        (
            "import subprocess\n"
            "class C:\n    f = lambda: (runner := subprocess.run)\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a lambda opens a scope of its own, so a walrus in one stays inside it",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding=f"utf-8")',
            "an f-string with no placeholder is a string literal and pins the codec",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=0, text=True)',
            "capture_output=0 is falsy, so subprocess opens no pipes to decode",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], stdout=subprocess.DEVNULL, text=True)',
            "DEVNULL discards the stream, so the attribute is None and nothing decodes",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf" + "-8")',
            "a codec name built from two literals is still a literal",
        ),
        (
            "import subprocess\n"
            "def local(*args, **kwargs):\n    return None\n"
            "H = (local, subprocess.run)\n"
            'H[0](["x"], capture_output=True, text=True)',
            "a literal index into a tuple names one element, not the whole tuple",
        ),
        (
            "from subprocess import run\n"
            "def check_output(*args, **kwargs):\n    return None\n"
            'check_output(["x"], capture_output=True, text=True)',
            "importing one name binds that name only, so a local definition wins",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, "
            'encoding="utf-8")\n'
            'runner(["x"], text=True)',
            "a partial that pins the codec keeps it at every site that calls it",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, "
            'encoding="utf-8")\n'
            "alias = runner\n"
            'alias(["x"], text=True)',
            "an alias of a pinned partial keeps the codec the partial pinned",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], stderr=subprocess.STDOUT, text=True)',
            "merging stderr into an inherited stdout captures neither stream",
        ),
        (
            "import subprocess\n"
            '("%s" % (subprocess.run,))[0](["x"], capture_output=True, text=True)',
            "formatting builds a string, so its characters are not the runner",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, '
            '**{"encoding": "utf-8"})',
            "a literal mapping splat pins the codec as plainly as a keyword does",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, '
            '**dict(encoding="utf-8"))',
            "dict() builds the same mapping the literal spelling does",
        ),
        (
            "import subprocess\n"
            'base = {"encoding": "utf-8"}\n'
            'subprocess.run(["x"], capture_output=True, text=True, **{**base})',
            "merging a literal mapping into another keeps the codec it carried",
        ),
        (
            "import subprocess\n"
            'options = {"encoding": "utf-8"}\n'
            'subprocess.run(["x"], capture_output=True, text=True, **options)',
            "a splat of a name bound to a literal mapping pins the codec",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True)\n"
            'runner(["x"], capture_output=False, text=True)',
            "a call site that turns capture off opens no pipe to decode",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True)\n"
            'runner(["x"], capture_output=0, text=True)',
            "any falsey constant turns capture off, not just the keyword False",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, stdout=subprocess.PIPE)\n"
            'runner(["x"], stdout=None, text=True)',
            "a call site that drops the pipe inherits nothing to decode",
        ),
        (
            "import subprocess\n"
            "class Runner:\n"
            "    runner = classmethod(subprocess.run)\n"
            'Runner().runner(["x"], capture_output=True, text=True)',
            "classmethod passes the class first, so the call raises before decoding",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], **{})',
            "a splat proven empty supplies no keyword, so nothing captures",
        ),
        (
            "import subprocess\nEMPTY = {}\nsubprocess.run(['x'], **EMPTY)",
            "a name bound to an empty literal is as readable as the literal",
        ),
        (
            'import subprocess\nkwargs = {}\nsubprocess.run(["x"], **kwargs)',
            "an empty splat carries no text keyword and returns bytes",
        ),
        (
            "import subprocess\n"
            "def go(**opts):\n"
            "    subprocess.run(['x'], capture_output=True, text=True, "
            '**{**opts, "encoding": "utf-8"})',
            "a codec spelled after an unreadable merge wins at runtime",
        ),
        (
            "import subprocess\n"
            "def go(**opts):\n"
            "    subprocess.run(['x'], capture_output=True, text=True, "
            '**dict(**opts, encoding="utf-8"))',
            "the dict-call spelling of a trailing codec wins the same way",
        ),
        (
            "import subprocess\n"
            "def go(**opts):\n"
            "    subprocess.run(['x'], capture_output=True, text=True, **opts, "
            '**{"encoding": "utf-8"})',
            "a later splat overrides an earlier unreadable one",
        ),
        (
            "import subprocess\nfrom operator import attrgetter\n"
            "attrgetter()(subprocess)(['x'], capture_output=True, text=True)",
            "an argless factory raises before it reaches anything",
        ),
        (
            "import os\nfrom operator import attrgetter\n"
            "attrgetter('run')(os)(['x'], capture_output=True, text=True)",
            "the owner has to be a subprocess module for the attribute to matter",
        ),
        (
            "import subprocess\nfrom operator import methodcaller\n"
            "methodcaller('run', ['x'])(subprocess)",
            "the keywords a methodcaller stores are the ones that decide the mode",
        ),
        (
            "import subprocess\nfrom operator import methodcaller\n"
            "methodcaller('run', ['x'], capture_output=True, text=True, "
            "encoding='utf-8')(subprocess)",
            "a codec stored on the factory pins the call it reaches",
        ),
        (
            "import subprocess\nvars(object)['r'] = subprocess.run\n"
            "r(['x'], capture_output=True, text=True)",
            "vars of an argument is not the module namespace and binds no global",
        ),
        (
            "import subprocess\nclass H: pass\n"
            "setattr(H, 'r')\nH.r(['x'], capture_output=True, text=True)",
            "a setattr missing its value raises before it binds anything",
        ),
        (
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, text=True, "
            "**{1: 'x', 'encoding': 'utf-8'})",
            "a codec spelled after an unspellable key still wins",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True)\n"
            "runner(['x'], capture_output=False, text=True)",
            "shadowing the only capture keyword leaves no pipe to decode",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, encoding='utf-8')\n"
            "runner(['x'], capture_output=True, text=True)",
            "a pin nothing rewrites survives to the site that calls it",
        ),
        (
            'import subprocess\nsubprocess.run([1], **{"cwd": "."})',
            "a splat this scan opened and read carries neither capture nor mode",
        ),
        (
            "import subprocess\n"
            "def options():\n"
            "    return {}\n"
            "opts = options()\n"
            'subprocess.run([1], capture_output=True, text=True, **{"encoding": "utf-8"}, **opts)',
            "a later splat cannot overwrite a call keyword without raising first",
        ),
        (
            "import functools, subprocess\n"
            "base = functools.partial(subprocess.run, capture_output=True)\n"
            "alias = base\n"
            "alias([1], capture_output=False, text=True)",
            "an alias carries the capture keywords its source pre-bound",
        ),
        (
            "import subprocess\n"
            'subprocess.run([1], capture_output=True, text=True, **dict(**{"encoding": "utf-8"}))',
            "a dict call is opened through the splat it merges",
        ),
        (
            "import subprocess\n"
            'subprocess.run([1], capture_output=True, text=True, **{"encoding": "utf-8"}, **KW)',
            "an unbound later splat cannot overwrite the codec either",
        ),
        (
            "import subprocess\n"
            "def safe(*args, **kwargs):\n"
            "    return None\n"
            'runner = {"run": safe}.get("run", subprocess.run)\n'
            "runner([1], capture_output=True, text=True)",
            "a literal mapping that holds the key never reaches the default",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, encoding='utf-8')\n"
            "assert runner.keywords.get('encoding') == 'utf-8'\n"
            "runner([1], text=True)",
            "reading a partial's keywords leaves the codec it pinned in place",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=False)\n"
            'runner(["x"], text=True)',
            "a partial that pre-bound capture off opens no pipe to decode",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=False)\n"
            'runner(["x"], capture_output=False, text=True)',
            "repeating the off value the partial already pre-bound changes nothing",
        ),
        (
            "import operator, subprocess\n"
            'name = "run"\n'
            "holder = object()\n"
            "operator.attrgetter(name)(holder)([1], capture_output=True, text=True)",
            "a getter reading an object that is not a known module reaches nothing",
        ),
        (
            "import subprocess\n"
            "class H:\n"
            "    pass\n"
            'register(H, "runner", subprocess.run)\n'
            "H.runner([1], capture_output=True, text=True)",
            "only setattr writes an attribute, so a lookalike call binds nothing",
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
            "import subprocess\n"
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
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf-8-sig")',
            "utf-8-sig silently strips a BOM, so it is not the pinned codec",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding=CODEC)',
            "a non-literal encoding cannot be proven to be utf-8",
        ),
        (
            "import subprocess\ncapture = True\n"
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
            'import subprocess\nkw = {"text": True}\nsubprocess.check_output(["x"], **kw)',
            "the splat hole is not specific to run",
        ),
        (
            'import subprocess\n_run = subprocess.run\n_run(["x"], capture_output=True, text=True)',
            "a plain assignment rebinds run without any import to read",
        ),
        (
            "import subprocess\na = subprocess.run\nb = a\n"
            'b(["x"], capture_output=True, text=True)',
            "an alias of an alias still reaches run",
        ),
        (
            'from subprocess import run\n_r = run\n_r(["x"], capture_output=True, text=True)',
            "a directly imported name can be rebound too",
        ),
        (
            "import subprocess\nfrom typing import Any\n"
            "_run: Any = subprocess.run\n"
            '_run(["x"], capture_output=True, text=True)',
            "an annotated assignment binds exactly like a plain one",
        ),
        (
            "import subprocess\ndef f():\n    r = subprocess.run\n"
            '    return r(["x"], capture_output=True, text=True)',
            "a binding inside a function body is just as reachable",
        ),
        (
            "import functools, subprocess\n"
            "_run = functools.partial(subprocess.run, text=True)\n"
            '_run(["x"], capture_output=True)',
            "partial pins text mode at the partial, not at the call",
        ),
        (
            'import subprocess\ngetattr(subprocess, "run")(["x"], capture_output=True, text=True)',
            "getattr with a literal name is still a static reference",
        ),
        (
            'import os\np = os.popen\np("x").read()',
            "os.popen can be rebound as readily as run",
        ),
        (
            'import os\ngetattr(os, "popen")("x").read()',
            "getattr reaches os.popen just as it reaches subprocess.run",
        ),
        (
            'import subprocess\nsubprocess.run.__call__(["x"], capture_output=True, text=True)',
            "__call__ on an entry point is the entry point",
        ),
        (
            'import subprocess as sp\nsp.run.__call__(["x"], capture_output=True, text=True)',
            "a module alias does not hide a dunder forward",
        ),
        (
            "import subprocess\nr = subprocess.run\n"
            'r.__call__(["x"], capture_output=True, text=True)',
            "a bound name forwards through __call__ like the attribute does",
        ),
        (
            'import os\nos.popen.__call__("x").read()',
            "os.popen forwards through __call__ and still cannot be pinned",
        ),
        (
            'import subprocess\ngetattr(subprocess.run, "__call__")'
            '(["x"], capture_output=True, text=True)',
            "getattr composed with a dunder forward reaches the entry point",
        ),
        (
            'import os\nname = "popen"\ngetattr(os, name)("x").read()',
            "a computed name on os can land on popen, which cannot be pinned",
        ),
        (
            "import subprocess\nr = None if flag else subprocess.run\n"
            'r(["x"], capture_output=True, text=True)',
            "a conditional hides the runner in either arm, not just the first",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, '
            'text=True, encoding="not-a-codec")',
            "an unknown codec name pins nothing, it raises before decoding",
        ),
        (
            'import subprocess\nname = "run"\n'
            'getattr(subprocess, name)(["x"], capture_output=True, text=True)',
            "a computed attribute name still reaches a subprocess entry point",
        ),
        (
            'import subprocess\nname = "getoutput"\ngetattr(subprocess, name)("ls")',
            "a computed name can land on getoutput, which decodes with no flag",
        ),
        (
            'import subprocess\nname = "getoutput"\nf = getattr(subprocess, name)\nf("ls")',
            "binding a computed lookup defers the decode, it does not avoid it",
        ),
        (
            "import subprocess\nif True:\n    a = subprocess.run\n"
            'b = a\nb(["x"], capture_output=True, text=True)',
            "a nested binding is walked after the top-level one that uses it",
        ),
        (
            'import subprocess\n(r := subprocess.run)(["x"], capture_output=True, text=True)',
            "a walrus binds and calls in one expression",
        ),
        (
            "import subprocess\nif (r := subprocess.run):\n    pass\n"
            'r(["x"], capture_output=True, text=True)',
            "a name bound by a walrus is still bound at the later call",
        ),
        (
            "import subprocess\nRUNNERS = [subprocess.run]\n"
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
            "import subprocess\nR = [*others, subprocess.run]\n"
            'R[0](["x"], capture_output=True, text=True)',
            "a starred element shifts every index after it",
        ),
        (
            "import subprocess\nR = [local, subprocess.run]\n"
            'R[7](["x"], capture_output=True, text=True)',
            "an index past the end of the literal reads nothing from it",
        ),
        (
            "import subprocess\nR = [local, subprocess.run]\n"
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
            'import subprocess\nR = (subprocess.getoutput,)\nR[0]("ls")',
            "a tuple element that always decodes needs no text keyword",
        ),
        (
            'import subprocess\nR = [subprocess.Popen, subprocess.getoutput]\nR[1]("ls")',
            "a mixed container may yield the member that decodes regardless",
        ),
        (
            "import subprocess\nfrom functools import partial as p\n"
            'f = p(subprocess.run, text=True)\nf(["x"], capture_output=True)',
            "an aliased partial import is not spelled partial at the call",
        ),
        (
            "import subprocess\na, b = subprocess.run, None\n"
            'a(["x"], capture_output=True, text=True)',
            "tuple unpacking binds a name without an ast.Name target",
        ),
        (
            "import subprocess\n(a, (b, c)) = (None, (subprocess.run, None))\n"
            'b(["x"], capture_output=True, text=True)',
            "a nested unpacking target is still a binding",
        ),
        (
            "import subprocess\n*runners, tail = subprocess.run, None\n"
            'runners[0](["x"], capture_output=True, text=True)',
            "a starred target collects the reference into a container",
        ),
        (
            "import subprocess\nrunners = [subprocess.run, subprocess.run]\n"
            'a, b = runners\na(["x"], capture_output=True, text=True)',
            "unpacking a name of unknown shape may hand it to either side",
        ),
        (
            "import subprocess\nrunners = [subprocess.run, subprocess.run]\n"
            'a, b = runners\nb(["x"], capture_output=True, text=True)',
            "every name on the left of an unknown shape carries the same answer",
        ),
        (
            "import subprocess\nclass C:\n    def __init__(self):\n"
            "        self.run = subprocess.run\n"
            'C().run(["x"], capture_output=True, text=True)',
            "an entry point parked on an attribute is reached through the object",
        ),
        (
            "import subprocess\nclass C:\n    run = subprocess.run\n"
            'C.run(["x"], capture_output=True, text=True)',
            "a class body binds an attribute without ever naming self",
        ),
        (
            "import subprocess\nfor runner in (subprocess.run,):\n"
            '    runner(["x"], capture_output=True, text=True)',
            "a loop target is a binding with no assignment statement",
        ),
        (
            "import subprocess\ndef go(runner=subprocess.run):\n"
            '    runner(["x"], capture_output=True, text=True)',
            "a default argument binds the name once, at definition time",
        ),
        (
            "import subprocess\ndef go(cmd, runner=subprocess.run):\n"
            "    runner(cmd, capture_output=True, text=True)",
            "defaults fill the tail of the parameter list, not the head",
        ),
        (
            "import subprocess\ndef go(*, runner=subprocess.run):\n"
            '    runner(["x"], capture_output=True, text=True)',
            "a keyword-only parameter carries its default in a separate list",
        ),
        (
            "import subprocess\ndef go():\n"
            '    return [r(["x"], capture_output=True, text=True) '
            "for r in (subprocess.run,)]",
            "a comprehension target binds inside its own scope",
        ),
        (
            "import subprocess\nrunners = [subprocess.run, subprocess.Popen]\n"
            'runners[0](["x"], capture_output=True, text=True)',
            "members that share a keyword contract still honour that contract",
        ),
        (
            "import subprocess, os\nrunners = [subprocess.check_output, os.popen]\n"
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
            "import subprocess\nmatch subprocess.run:\n    case runner:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "a bare match case captures the subject under a new name",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n"
            "    case object() as runner:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "an as-pattern captures under a name too",
        ),
        (
            "import subprocess\nmatch [subprocess.run]:\n    case [*rest]:\n"
            '        rest[0](["x"], capture_output=True, text=True)',
            "a star pattern collects the subject into a new container",
        ),
        (
            'import subprocess\nmatch {"k": subprocess.run}:\n'
            "    case {**rest}:\n"
            '        rest["k"](["x"], capture_output=True, text=True)',
            "a mapping rest pattern captures what the other keys left",
        ),
        (
            "import subprocess\nmatch [subprocess.run]:\n    case [runner]:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "a sequence pattern captures an element by position",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n"
            "    case runner if runner:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "a guarded case still captures before the guard runs",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n"
            "    case object(__doc__=held):\n"
            '        held(["x"], capture_output=True, text=True)',
            "a class pattern captures through a keyword",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n    case [] | runner:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "an or-pattern captures in whichever alternative matches",
        ),
        (
            "import subprocess\nmatch subprocess.run:\n    case []:\n"
            "        pass\n    case runner:\n"
            '        runner(["x"], capture_output=True, text=True)',
            "a later case captures just as much as the first",
        ),
        (
            "import subprocess\nheld = [subprocess.run]\n"
            "for runner in held:\n"
            '    runner(["x"], capture_output=True, text=True)',
            "an opaque iterable still resolves through its own binding",
        ),
        (
            "import subprocess\n"
            "for runner in [subprocess.check_call, subprocess.run]:\n"
            '    runner(["x"], capture_output=True, text=True)',
            "every item of the iterable is a value the name can take",
        ),
        (
            "import subprocess\n"
            "def go(runner=subprocess.run, /):\n"
            '    runner(["x"], capture_output=True, text=True)',
            "a positional-only parameter takes a default like any other",
        ),
        (
            "import subprocess\nfrom typing import Any\n"
            "class C:\n    runner: Any = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "an annotated class attribute binds like a plain one",
        ),
        (
            "import subprocess\n"
            "class C:\n    (runner := subprocess.run)\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus in a class body binds a class attribute",
        ),
        (
            "import subprocess\n"
            "class C:\n    held = [print]\n    held += [subprocess.run]\n"
            'C.held[0](["x"], capture_output=True, text=True)',
            "a class attribute extended in place holds what was added",
        ),
        (
            "import subprocess\n"
            "class C:\n    if True:\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a class body binds inside a branch as well as outside one",
        ),
        (
            "import subprocess\n"
            "class C:\n    try:\n        runner = subprocess.run\n"
            "    except ImportError:\n        runner = None\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a guarded import shape still binds the name it guards",
        ),
        (
            "import subprocess\n"
            "class C:\n    for runner in [subprocess.run]:\n        pass\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a loop variable in a class body outlives the loop as an attribute",
        ),
        (
            "import subprocess\n"
            "class C:\n    match subprocess.run:\n        case runner:\n            pass\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a match capture in a class body outlives the match as an attribute",
        ),
        (
            "import subprocess\n"
            "class C:\n    try:\n        import fast\n"
            "    except ImportError:\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a fallback bound in an except body is still a class attribute",
        ),
        (
            "import subprocess\n"
            "class C:\n    if False:\n        pass\n"
            "    else:\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a class body binds in an else branch as well as an if",
        ),
        (
            "import subprocess\n"
            "class C:\n    try:\n        pass\n    except ImportError:\n        pass\n"
            "    else:\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a try else block binds in the class namespace too",
        ),
        (
            "import subprocess\n"
            "class C:\n    try:\n        pass\n"
            "    finally:\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a finally block binds in the class namespace too",
        ),
        (
            "import subprocess\n"
            "class C:\n    match 1:\n        case 1:\n            runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a case body binds in the class namespace too",
        ),
        (
            "import subprocess, contextlib\n"
            "class C:\n"
            "    with contextlib.suppress(Exception):\n        runner = subprocess.run\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a with body binds in the class namespace too",
        ),
        (
            "import subprocess\n"
            "for runner, unused in [(subprocess.run, 1), (subprocess.run, 1)]:\n    pass\n"
            'runner(["x"], capture_output=True, text=True)',
            "skipping a repeated item must not drop the binding it already read",
        ),
        (
            'from os import popen\nout = popen("x").read()',
            "os.popen always decodes and has no codec knob, so an import of it is the worst case",
        ),
        (
            'from os import popen as spawn\nout = spawn("x").read()',
            "renaming os.popen on import does not stop it decoding",
        ),
        (
            'import os as system\nout = system.popen("x").read()',
            "renaming the os module on import does not stop popen decoding",
        ),
        (
            "import subprocess\n"
            "runner = subprocess.run if True else None\n"
            'runner(["x"], capture_output=True, text=True)',
            "a conditional expression picks a runner and the scan must read both arms",
        ),
        (
            "import subprocess\n"
            "runner = subprocess.run or None\n"
            'runner(["x"], capture_output=True, text=True)',
            "a boolean fallback picks a runner and the scan must read every operand",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], -1, None, None, subprocess.PIPE, text=True)',
            "stdout passed positionally captures, and the mode keyword still decodes",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], -1, None, None, subprocess.PIPE, None, None, True,'
            " False, None, None, True)",
            "universal_newlines passed positionally selects text mode with no keyword",
        ),
        (
            "import subprocess\n"
            'next(r for r in [subprocess.run])(["x"], capture_output=True, text=True)',
            "a generator expression yields the runner without naming it at the call",
        ),
        (
            "import subprocess\n"
            '[r for r in [subprocess.run]][0](["x"], capture_output=True, text=True)',
            "a list comprehension is the same reference wearing a loop",
        ),
        (
            "import subprocess\n"
            '{r for r in [subprocess.run]}.pop()(["x"], capture_output=True, text=True)',
            "popping a set comprehension hands back the runner it was built from",
        ),
        (
            "import subprocess\n"
            '{k: subprocess.run for k in "a"}["a"](["x"], capture_output=True, text=True)',
            "a dict comprehension holds the runner in its values",
        ),
        (
            "import subprocess\n"
            'list(r for r in [subprocess.run])[0](["x"], capture_output=True, text=True)',
            "list() of a generator is still the element the generator yields",
        ),
        (
            "import subprocess\n"
            'next(iter([subprocess.run]))(["x"], capture_output=True, text=True)',
            "iter() and next() reach the element with no comprehension at all",
        ),
        (
            "import subprocess\n"
            "runner = None or subprocess.run\n"
            'runner(["x"], capture_output=True, text=True)',
            "a boolean fallback can hold the runner in any operand, not just the first",
        ),
        (
            'import subprocess\n(subprocess.run,)[0](["x"], capture_output=True, text=True)',
            "an inline tuple holds a runner the same way an inline list does",
        ),
        (
            'import subprocess\n{subprocess.run}.pop()(["x"], capture_output=True, text=True)',
            "an inline set holds a runner and pop hands it straight back",
        ),
        (
            "import subprocess\n"
            "class C:\n    if (runner := subprocess.run):\n        pass\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus in an if test binds a class attribute like any other walrus",
        ),
        (
            "import subprocess\n"
            "class C:\n    print(runner := subprocess.run)\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus inside a call argument still outlives the statement",
        ),
        (
            "import subprocess\n"
            "class C:\n    ok = True and (runner := subprocess.run)\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus nested in an assigned expression binds two names, not one",
        ),
        (
            "import subprocess\n"
            "class C:\n    assert (outer := (runner := subprocess.run))\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "a walrus inside another walrus binds both names, so the walk descends",
        ),
        (
            "import subprocess\n"
            "class C:\n    assert (first := 1) and (runner := subprocess.run)\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "one statement can hold several walruses and every one of them binds",
        ),
        (
            "import functools, subprocess\n"
            "run_cmd = functools.partial(subprocess.run, capture_output=True)\n"
            'run_cmd(["x"], text=True)',
            "a partial can hold the capture and take the text mode at its call site",
        ),
        (
            'import subprocess\n(*[subprocess.run],)[0](["x"], capture_output=True, text=True)',
            "a star unpacks a container into the one around it and the runner survives",
        ),
        (
            "import subprocess\n"
            '(lambda runner=subprocess.run: runner(["x"], capture_output=True, text=True))()',
            "a lambda takes default arguments exactly as a def does",
        ),
        (
            'import os, subprocess\nflag = True\n(subprocess.Popen if flag else os.popen)("ls")',
            "os.popen always decodes, so an arm that reaches it answers for the call",
        ),
        (
            "import subprocess\n"
            "X = (*[subprocess.Popen, subprocess.run], subprocess.check_output)\n"
            "X[2]([1], capture_output=True, text=True)",
            "a star shifts every index after it, so reading one needs it spread first",
        ),
        (
            "import subprocess\n"
            "R = [subprocess.run]\n"
            "X = [*R]\n"
            "X[0]([1], capture_output=True, text=True)",
            "a star over a name has no readable members, so the name itself is the member",
        ),
        (
            "import subprocess\n"
            'suffix = "8"\n'
            'subprocess.run([1], capture_output=True, text=True, encoding=f"utf-{suffix}")',
            "a placeholder makes the codec unknowable, so the pin is not proven",
        ),
        (
            "import subprocess, sys\nsp = subprocess\nsp.run([1], capture_output=True, text=True)",
            "a module bound to another name is the same module",
        ),
        (
            "from subprocess import *\nrun([1], capture_output=True, text=True)",
            "a star import binds every public name the module exports",
        ),
        (
            "import subprocess\n"
            'runner = {"run": subprocess.run}.get("run")\n'
            "runner([1], capture_output=True, text=True)",
            "get reads an element out of a mapping exactly as pop does",
        ),
        (
            "import subprocess\n"
            "runner = min([subprocess.run])\n"
            "runner([1], capture_output=True, text=True)",
            "min hands back one of the elements it was given",
        ),
        (
            "import subprocess\n"
            "def bind():\n    global sp\n    sp = subprocess\n"
            "sp2 = sp\n"
            "sp2.run([1], capture_output=True, text=True)",
            "a module alias bound through a second alias is still the module",
        ),
        (
            "import subprocess\n"
            "runner = max([subprocess.run])\n"
            "runner([1], capture_output=True, text=True)",
            "max hands back one of the elements it was given, exactly as min does",
        ),
        (
            "import subprocess\nsorted([subprocess.run])[0]([1], capture_output=True, text=True)",
            "sorted hands back the same elements in another order",
        ),
        (
            "import collections, subprocess\n"
            "q = collections.deque()\n"
            "q.append(subprocess.run)\n"
            "q.popleft()([1], capture_output=True, text=True)",
            "popleft takes an element off the other end and is still an element",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True)\n"
            "alias = runner\n"
            "alias([1], text=True)",
            "an alias of a partial carries the keywords the partial pre-bound",
        ),
        (
            "import subprocess\n"
            'runner = {}.setdefault("run", subprocess.run)\n'
            "runner([1], capture_output=True, text=True)",
            "setdefault hands back its second argument when the key is absent",
        ),
        (
            "import subprocess\n"
            'runner = {}.get("run", subprocess.run)\n'
            "runner([1], capture_output=True, text=True)",
            "get hands back its second argument when the key is absent",
        ),
        (
            "import subprocess\n"
            "runners = [] + [subprocess.run]\n"
            "runners[0]([1], capture_output=True, text=True)",
            "adding two lists makes a list holding the elements of both",
        ),
        (
            "import subprocess\n"
            "runners = (subprocess.run,) + ()\n"
            "runners[0]([1], capture_output=True, text=True)",
            "tuple concatenation hides a runner the same way list addition does",
        ),
        (
            "import subprocess\n"
            "runners = [subprocess.run] * 2\n"
            "runners[0]([1], capture_output=True, text=True)",
            "repeating a container repeats the runner it holds",
        ),
        (
            "import subprocess\n"
            "runners = 2 * [subprocess.run]\n"
            "runners[0]([1], capture_output=True, text=True)",
            "the count may be written on either side of the repetition",
        ),
        (
            "import subprocess\nsubprocess.run.__wrapped__([1], capture_output=True, text=True)",
            "__wrapped__ hands back the callable it was read from",
        ),
        (
            "import subprocess\n"
            "next(iter(frozenset([subprocess.run])))([1], capture_output=True, text=True)",
            "frozenset holds the elements it was built from",
        ),
        (
            "import subprocess\n"
            "subprocess.run([1], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)",
            "merging stderr into a piped stdout still decodes the pipe",
        ),
        (
            "import subprocess\nsubprocess.check_output([1], stderr=subprocess.STDOUT, text=True)",
            "check_output captures on its own, so merging stderr into it still decodes",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, "
            'encoding="utf-8")\n'
            'runner([1], text=True, encoding="latin-1")',
            "a keyword at the call site overrides the one the partial pre-bound",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, "
            'encoding="utf-8")\n'
            "runner([1], text=True, **overrides)",
            "a splat at the call site may carry an encoding that overrides the pin",
        ),
        (
            "import subprocess\n"
            "def call(**kwargs):\n"
            "    subprocess.run([1], capture_output=True, text=True, **kwargs)",
            "a splat this file cannot read may carry no codec at all",
        ),
        (
            "import subprocess\n"
            '({"r": subprocess.run} | {})["r"]([1], capture_output=True, text=True)',
            "merging two dicts keeps the values of both",
        ),
        (
            "import subprocess\n"
            "list({subprocess.run} - set())[0]([1], capture_output=True, text=True)",
            "a set difference keeps whichever members survive",
        ),
        (
            "import subprocess\n"
            "list({subprocess.run} & {subprocess.run})[0]([1], capture_output=True, "
            "text=True)",
            "a set intersection keeps whichever members are in both",
        ),
        (
            "import subprocess\n"
            "list({subprocess.run} ^ set())[0]([1], capture_output=True, text=True)",
            "a symmetric difference keeps whichever members appear once",
        ),
        (
            "import subprocess\n"
            'globals()["runner"] = subprocess.run\n'
            "runner([1], capture_output=True, text=True)",
            "writing through globals() creates an ordinary module-level name",
        ),
        (
            "import subprocess\n"
            'vars()["runner"] = subprocess.run\n'
            "runner([1], capture_output=True, text=True)",
            "vars() at module scope is the same mapping globals() returns",
        ),
        (
            "import contextlib, subprocess\n"
            "with contextlib.nullcontext(subprocess.run) as runner:\n"
            "    runner([1], capture_output=True, text=True)",
            "nullcontext hands its argument straight back out of __enter__",
        ),
        (
            "import contextlib, subprocess\n"
            "with contextlib.nullcontext((subprocess.run,)) as pair:\n"
            "    pair[0]([1], capture_output=True, text=True)",
            "nullcontext is transparent to a container as much as to a name",
        ),
        (
            "import contextlib, subprocess\n"
            "with contextlib.ExitStack() as stack:\n"
            "    runner = stack.enter_context(contextlib.nullcontext(subprocess.run))\n"
            "    runner([1], capture_output=True, text=True)",
            "enter_context returns whatever __enter__ returned",
        ),
        (
            "import subprocess\n"
            "class Runner:\n"
            "    runner = staticmethod(subprocess.run)\n"
            "Runner().runner([1], capture_output=True, text=True)",
            "staticmethod hands the wrapped function back with no instance bound",
        ),
        (
            "import subprocess\n"
            "class Runner:\n"
            "    runner = staticmethod(subprocess.run)\n"
            "Runner.runner([1], capture_output=True, text=True)",
            "a staticmethod reached on the class is the same wrapped function",
        ),
        (
            "import operator, subprocess\n"
            'operator.methodcaller("run", [1], capture_output=True, text=True)(subprocess)',
            "methodcaller calls the named attribute with the arguments it stored",
        ),
        (
            "import operator, subprocess\n"
            'operator.attrgetter("run")(subprocess)([1], capture_output=True, text=True)',
            "attrgetter reaches the attribute without spelling it as one",
        ),
        (
            "import subprocess\n"
            'setattr(holder, "runner", subprocess.run)\n'
            "holder.runner([1], capture_output=True, text=True)",
            "setattr binds an attribute the same way an assignment would",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, "
            'text=True, encoding="utf-8")\n'
            'runner.keywords["encoding"] = None\n'
            "runner([1])",
            "a partial's keywords are mutable, so an inherited pin can be undone",
        ),
        (
            "import subprocess\nfrom operator import itemgetter\n"
            "itemgetter(0)([subprocess.run])([1], capture_output=True, text=True)",
            "itemgetter hands back the element it selects, runner and all",
        ),
        (
            "import subprocess\nfrom operator import itemgetter\n"
            "HOLDER = [subprocess.run]\n"
            "itemgetter(0)(HOLDER)([1], capture_output=True, text=True)",
            "the container itemgetter reads can be a name bound to a literal",
        ),
        (
            "import subprocess\nfrom operator import getitem\n"
            "getitem([subprocess.run], 0)([1], capture_output=True, text=True)",
            "operator.getitem selects an element the same way a subscript does",
        ),
        (
            "import subprocess\n"
            "next(filter(None, [subprocess.run]))([1], capture_output=True, text=True)",
            "filter holds its sequence in the second argument, not the first",
        ),
        (
            "import subprocess\nfrom itertools import filterfalse\n"
            "next(filterfalse(None, [subprocess.run]))([1], capture_output=True, text=True)",
            "filterfalse forwards an element of its second argument",
        ),
        (
            "import subprocess\nfrom itertools import takewhile\n"
            "next(takewhile(None, [subprocess.run]))([1], capture_output=True, text=True)",
            "takewhile forwards an element of its second argument",
        ),
        (
            "import subprocess\nfrom itertools import dropwhile\n"
            "next(dropwhile(None, [subprocess.run]))([1], capture_output=True, text=True)",
            "dropwhile forwards an element of its second argument",
        ),
        (
            "import subprocess\nfrom heapq import nlargest\n"
            "nlargest(1, [subprocess.run])[0]([1], capture_output=True, text=True)",
            "nlargest forwards elements of its second argument",
        ),
        (
            "import subprocess\nfrom heapq import nsmallest\n"
            "nsmallest(1, [subprocess.run])[0]([1], capture_output=True, text=True)",
            "nsmallest forwards elements of its second argument",
        ),
        (
            "import subprocess\nfrom itertools import chain\n"
            "next(chain([], [subprocess.run]))([1], capture_output=True, text=True)",
            "chain forwards an element of any argument, not just the first",
        ),
        (
            "import subprocess\nmodule = [subprocess][0]\n"
            "module.run([1], capture_output=True, text=True)",
            "a container can hold the module itself, not only the runner",
        ),
        (
            "import subprocess\nHOLDER = (subprocess,)\nmodule = HOLDER[0]\n"
            "module.run([1], capture_output=True, text=True)",
            "the container a module alias reads can be a name bound to a literal",
        ),
        (
            "import subprocess\nfrom operator import attrgetter\nname = 'run'\n"
            "attrgetter(name)(subprocess)([1], capture_output=True, text=True)",
            "a computed attribute on a known module reaches some entry point",
        ),
        (
            "import subprocess\n"
            "def options():\n"
            "    return {}\n"
            "subprocess.run([1], capture_output=True, text=True, "
            '**{"encoding": "utf-8", **options()})',
            "a merge this scan cannot open still hides what follows the codec",
        ),
        (
            "import subprocess\nk = 'text'\nsubprocess.run([1], capture_output=True, **{k: True})",
            "a computed key may be the one that selects text mode",
        ),
        (
            "import subprocess\n"
            'subprocess.run([1], capture_output=True, text=True, **{"encoding": "utf-8", '
            '"encoding": None})',
            "a key repeated in one display keeps the value written last",
        ),
        (
            "import subprocess\n"
            "def go(**opts):\n"
            "    subprocess.run([1], capture_output=True, text=True, "
            '**{"encoding": "utf-8", **opts})',
            "a merge spelled after the codec overrides it at runtime",
        ),
        (
            "import subprocess\nfrom contextlib import nullcontext\n"
            "async def go():\n"
            "    async with nullcontext(subprocess.run) as r:\n"
            "        r([1], capture_output=True, text=True)",
            "an async with binds its target exactly as a plain with does",
        ),
        (
            "import subprocess\nclass H: pass\n"
            'setattr(H, "r", subprocess.run)\nH.r([1], capture_output=True, text=True)',
            "setattr binds an attribute without an assignment statement",
        ),
        (
            "import functools, subprocess\nclass A:\n"
            "    b = functools.partial(subprocess.run, capture_output=True, "
            'text=True, encoding="utf-8")\n'
            "a = A()\n"
            'a.b.keywords["encoding"] = None\n'
            "a.b([1])",
            "an attribute receiver rewrites the same keywords a bare name does",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, "
            "stdout=subprocess.PIPE)\n"
            "runner([1], capture_output=False, text=True)",
            "shadowing one capture keyword leaves the other pipe open",
        ),
        (
            "import subprocess\n"
            'subprocess.run([1], capture_output=True, text=True, **{"encoding": "latin-1"})',
            "a splatted codec is read as the codec it names, not waved through",
        ),
        (
            "import functools, subprocess\n"
            "base = functools.partial(subprocess.run, capture_output=True)\n"
            "alias = base\nalias([1], text=True)",
            "an alias of a partial carries the capture the original pre-bound",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True)\n"
            "runner([1], capture_output=True, text=True)",
            "repeating a capture keyword with the same value changes nothing",
        ),
        (
            "import subprocess\n"
            "class Holder:\n"
            "    sp = subprocess\n"
            "Holder.sp.run([1], capture_output=True, text=True)",
            "a module parked on a class attribute still names the module",
        ),
        (
            "import functools, subprocess\n"
            "base = functools.partial(subprocess.run, capture_output=True)\n"
            "holders = [base]\n"
            "runner = holders[0]\n"
            "runner([1], text=True)",
            "a partial taken out of a container keeps the capture it pre-bound",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, capture_output=True, encoding='utf-8')\n"
            "alias = runner\n"
            "alias.keywords['encoding'] = None\n"
            "runner([1], text=True)",
            "rewriting a partial through one alias undoes the pin under every name",
        ),
        (
            "import subprocess\n"
            "from operator import itemgetter as pick\n"
            "runner = pick(0)([subprocess.run])\n"
            "runner([1], capture_output=True, text=True)",
            "an operator selector imported under an alias is still that selector",
        ),
        (
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, stdout=subprocess.PIPE)\n"
            "runner([1], stdout=subprocess.PIPE, text=True)",
            "repeating a capturing stream leaves the pipe the partial opened",
        ),
        (
            "import subprocess\n"
            'pairs = [("text", True)]\n'
            "subprocess.run([1], capture_output=True, **dict(pairs))",
            "a dict built from a positional mapping may still select text mode",
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
            "import subprocess\na, b = [subprocess.run]\na([1], capture_output=True, text=True)",
            "an unpack whose sides do not line up",
        ),
        (
            "import subprocess\nsubprocess.run([1], capture_output=True, text=True, encoding=8)",
            "a codec keyword that is not a string",
        ),
        (
            "import subprocess\n"
            "def g():\n"
            "    subprocess.run([1], capture_output=(yield), text=True)",
            "a capture keyword whose value is not a literal at all",
        ),
    ],
)
def test_detector_survives_malformed_source(source: str, why: str) -> None:
    """Shapes that are legal Python but nonsense. The scan reports, never raises.

    A crash here takes the whole gate down and every call in the repository
    goes unchecked, which is strictly worse than a false alarm. Both shapes
    reach code that would raise if it trusted its input: a strict zip over
    two lists of different lengths, and :func:`codecs.lookup` on an integer.
    """
    assert unpinned_lines(source) != [], f"missed {why}"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess, sys\nsubprocess.run(["x"], stdout=sys.stdout, text=True)',
            "a redirect that is not a pipe leaves the parent nothing to decode",
        ),
        (
            "import subprocess\na = subprocess.run\n"
            "a = lambda *args, **kwargs: None\n"
            'a(["x"], capture_output=True, text=True)',
            "the later binding wins at runtime, but not in a flow-blind scan",
        ),
        (
            'import subprocess\nkwargs = {}\nkwargs["text"] = True\n'
            'subprocess.run(["x"], **kwargs)',
            "a name written to after binding is no longer readable as empty",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, '
            "**dict([('encoding', 'utf-8')]))",
            "a dict built from positional pairs is not read, so its codec is hidden",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, **'
            + "{**" * 9
            + "{'encoding': 'utf-8'}"
            + "}" * 9
            + ")",
            "a mapping nested past the depth bound stops being read",
        ),
        (
            "import subprocess\nclass C:\n    def __init__(self):\n"
            "        self.run = subprocess.run\n"
            "def go(parser):\n"
            '    parser.run(["x"], capture_output=True, text=True)',
            "an unrelated object with a same-named method reads as the one bound",
        ),
        (
            "import subprocess\n"
            "held = [subprocess.run, subprocess.check_call]\n"
            'held[True](["x"], capture_output=True, text=True)',
            "a bool index is a valid int index, and reading it as one is a guess",
        ),
        (
            "import subprocess\n"
            "def read():\n"
            "    held = [subprocess.check_call]\n"
            '    held[0](["x"], capture_output=True, text=True)\n'
            "def write():\n"
            "    held = [subprocess.run]\n"
            '    held[0](["x"], capture_output=True, text=True)',
            "one name bound in two scopes reads as one name bound twice",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], -1)',
            "a second positional argument lands in a parameter this scan cannot name",
        ),
        (
            "import subprocess\n"
            "class C:\n    class D:\n        assert (runner := subprocess.run)\n"
            'C.runner(["x"], capture_output=True, text=True)',
            "an attribute is keyed by its name alone, so the owning class is not read",
        ),
        (
            "import subprocess\n"
            "import vendored\n"
            'subprocess.run(["x"], stdout=vendored.DEVNULL, text=True)',
            "a DEVNULL attribute on an untracked module may be anything, so it counts",
        ),
        (
            'import subprocess, os\nsubprocess.run(["x"], stdout=os.DEVNULL, text=True)',
            "os.DEVNULL is a path string, not the subprocess sentinel, so it counts",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf" % "-8")',
            "only concatenation folds two string literals, so any other operator counts",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding=PREFIX + "utf-8")',
            "a name on the left of a concatenation hides the whole codec name",
        ),
        (
            "import subprocess\n"
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf-8" + SUFFIX)',
            "a name on the right of a concatenation hides the whole codec name",
        ),
        (
            "import subprocess\n"
            'H = {"run": subprocess.run}\n'
            "H.popitem()([1], capture_output=True, text=True)",
            "popitem hands back a key and value pair, which raises before it decodes",
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


def test_a_wide_loop_over_a_repeated_item_stays_linear() -> None:
    """A loop target must cost one read per distinct item, not one per item.

    ``_iterated`` pairs the target with each item in turn, which is what makes
    a loop read down its columns instead of across its rows. The cost is that
    a target of ``width`` names against ``width`` items emits ``width``
    squared bindings, and the resolution queue then walks every one: 4000 by
    4000 took 10.34 seconds, growing fourfold for every doubling.

    Binding the same name to the same value twice teaches the scan nothing, so
    an item whose shape has already been read can be skipped. Every item here
    is the same name, so the work collapses to one read.
    """
    width = 4000
    names = ", ".join(f"a{index}" for index in range(width))
    items = ", ".join("x" for _ in range(width))
    source = f"import subprocess\nfor {names} in [{items}]:\n    pass\n"

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [], "no call is made, so nothing can decode"
    assert elapsed < 2.0, f"the loop took {elapsed:.1f}s for {width} names"


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
            "import subprocess\nv1 = v2\nv2 = subprocess.run\n"
            'v1(["x"], capture_output=True, text=True)',
            "a binding that reads a name defined below it still resolves",
        ),
    ],
)
def test_detector_resolves_out_of_order_chains(source: str, why: str) -> None:
    """Source order does not decide resolution order, so neither can evade."""
    assert unpinned_lines(source) != [], f"missed {why}"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            "import subprocess\nfrom operator import attrgetter\n"
            "def pick():\n"
            "    return subprocess\n"
            "attrgetter('run')(pick())(['x'], capture_output=True, text=True)",
            "a module returned by a call is not traced back to its import",
        ),
        (
            "import subprocess\nk = 'r'\nglobals()[k] = subprocess.run\n"
            "r(['x'], capture_output=True, text=True)",
            "a namespace key spelled as a name bound to a string is not read",
        ),
        (
            "import subprocess\nclass H: pass\nn = 'r'\n"
            "setattr(H, n, subprocess.run)\nH.r(['x'], capture_output=True, text=True)",
            "a setattr name spelled as a name bound to a string is not read",
        ),
    ],
)
def test_detector_stops_at_a_known_limit(source: str, why: str) -> None:
    """Shapes that decode at runtime and this scan does not reach. Recorded, not excused.

    Each one is a false negative, which is the direction this file exists to
    prevent, so each is pinned here rather than left to be rediscovered. The
    first needs a value to be followed out of a function and back, which is
    the same interprocedural step tracked separately. The other two need a
    name bound to a string constant to be read as that constant.

    A widening that closes any of these fails this test, which is the point:
    the limit moves by a deliberate edit, never by accident.
    """
    assert unpinned_lines(source) == [], f"limit moved, update the record: {why}"


def test_a_popped_pin_stops_answering_for_the_call_site() -> None:
    """A rewritten pin has to be dropped at both the construction and the call.

    Two mechanisms carry this, and each is the only one that answers in a
    different case. A construction that captures is scanned as an offender in
    its own right, and the id set is what unpins it there. A construction that
    captures nothing is never scanned, so only dropping the recorded pin
    reaches the site that calls it. Asserting both lines is what tells the two
    apart: dropping either mechanism alone still leaves the other line flagged.
    """
    source = (
        "import functools, subprocess\n"
        "runner = functools.partial(subprocess.run, encoding='utf-8')\n"
        "runner.keywords['encoding'] = None\n"
        "runner(['x'], capture_output=True, text=True)"
    )

    assert unpinned_lines(source) == [2, 4], "both the construction and the call lose the pin"


def test_a_deleted_keyword_undoes_an_inherited_pin() -> None:
    """Deleting a pre-bound codec is a rewrite, the same as assigning over it."""
    source = (
        "import functools, subprocess\n"
        "runner = functools.partial(subprocess.run, capture_output=True, "
        "text=True, encoding='utf-8')\n"
        "del runner.keywords['encoding']\n"
        "runner(['x'])"
    )

    assert unpinned_lines(source) == [2], "a delete rewrites the keywords it removes"


def test_name_resolution_survives_a_deep_subscript_chain() -> None:
    """A long subscript chain must not exhaust the interpreter stack.

    ``a[0][0][0]...`` is left recursive rather than nested, so the parser
    imposes no bracket-depth limit and hands back an arbitrarily deep tree.
    Unwinding it with recursion crashes; unwinding it in a loop does not.
    """
    source = "import subprocess\na = subprocess.run" + "[0]" * 2000 + "\na()"

    assert unpinned_lines(source) == [], "a bare call with no keywords decodes nothing"
