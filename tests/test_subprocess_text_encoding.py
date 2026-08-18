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
from collections import Counter, deque
from pathlib import Path
from typing import NamedTuple

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
# The attribute a functools.partial keeps its bound keywords under.
_KEYWORDS = "keywords"
# The dict method that answers a question about the mapping while reaching
# only its keys. A partial's keys are always strings, so nothing it hands
# back can run code from the module under scan.
_KEY_READERS = frozenset({"keys"})
# The dict methods that hand a value back out. None of them changes the
# mapping, but the value they release carries its own ``__repr__`` and
# ``__eq__``, and those reach the mapping again. Spared only when every bound
# value is a literal. Every other way of reaching the mapping is a write.
_VALUE_READERS = frozenset({"copy", "get", "items", "values"})
# The nodes that hold the thing they walk under ``iter``. Walking a mapping
# yields its keys and leaves the mapping itself alone. All three also accept
# an assignment target, so the node has to be the ``iter`` to count as a read.
_WALKING_PARENTS = (ast.For, ast.AsyncFor, ast.comprehension)
# The nodes that only look at what they are given. A comparison runs ``__eq__``
# on the values it reaches; an interpolation renders them. Both are spared only
# when every bound value is a literal, which cannot run code.
_INSPECTING_PARENTS = (ast.Compare, ast.FormattedValue)
# The keyword the pin is bound under. A store or a delete that spells out some
# other key cannot reach it.
_ENCODING = "encoding"
# The builtin that fetches an attribute by name. It reaches a partial's
# keyword mapping exactly as the attribute does.
_GETATTR = "getattr"
# The dunders an attribute read delegates to. Spelling either one out by hand
# reaches the same value the sugar does, so a scan reading only the sugar is
# one rename away from missing the fetch. ``__getattr__`` is the fallback a
# partial subclass can define; ``__getattribute__`` runs for every read.
_ATTR_DUNDERS = frozenset({"__getattribute__", "__getattr__"})
# How a name that fetches an attribute asks for it. A named fetcher is told
# the attribute at the call site, the way ``getattr`` is. A fixed one was
# built already knowing it, the way ``attrgetter("keywords")`` is.
_FETCH_NAMED = "named"
_FETCH_FIXED = "fixed"
# The builtins that consume a mapping by walking its keys. A partial's keys
# are always strings, so what these answer with holds no way back to the
# mapping: a number, a bool, one key, or a fresh container of keys. Measured
# rather than assumed, by walking ``gc.get_referents`` from each answer.
# ``iter``, ``reversed``, and ``id`` were dropped for failing that walk: the
# first two answer with an iterator that holds the mapping, and the third
# answers with its address, which ``ctypes`` will dereference. Every other
# callee can hand the mapping on, so the mapping is treated as at risk.
_MAPPING_READERS = frozenset(
    {
        "all", "any", "bool", "frozenset", "len",
        "list", "max", "min", "set", "sorted", "sum", "tuple",
    }
)
# The builtin that answers with a mapping rather than with the keys. ``dict``
# reads like its neighbours above and behaves like ``copy``: what it hands
# back holds the same value objects the original does, so rendering the copy
# runs their ``__repr__`` and reaches the original through it. Spared only
# when every bound value is a literal.
_COPYING_READERS = frozenset({"dict"})
# The builtins that render a mapping. Rendering reaches every value, so a
# value that is not a literal runs its own ``__repr__`` and can drop the pin
# in the middle of what the source reads as a look. Spared only when every
# bound value is a literal.
_RENDERING_READERS = frozenset({"ascii", "format", "print", "repr", "str"})
# Every reader a file can shadow by binding its name. Held as one set because
# shadowing does not care what a reader does with the mapping, only that the
# spelling no longer reaches the builtin.
_SHADOWABLE_READERS = _MAPPING_READERS | _RENDERING_READERS | _COPYING_READERS
_UNKNOWN = object()
_PARTIAL = "functools.partial"
# Marks the null sink. Held beside the entry points so an imported ``DEVNULL``
# is recognised at a call site, and filtered out of every path that answers
# "is this a subprocess entry point".
_DEVNULL = "subprocess.DEVNULL"
# The two sentinels that ask for a pipe. Recognised by name so an import of
# either reads as what it is rather than as an opaque attribute.
_PIPE = "subprocess.PIPE"
_STDOUT = "subprocess.STDOUT"

# The ``operator`` factories that reach a runner without ever spelling its
# name at the call site. Each builds a callable, and it is the object handed
# to that callable that decides what comes back: ``attrgetter("run")`` reads
# the attribute off whatever module it is given, ``itemgetter(0)`` selects an
# element out of whatever container it is given. The factory call and the
# call that uses it are two separate nodes, so a scan that only reads the
# outer ``func`` sees a call on a call and stops.
_OPERATOR_METHODCALLER = "methodcaller"
# methodcaller reads an attribute off its argument exactly as attrgetter does.
# What sets it apart is that it also calls the result, so the keywords that
# decide the codec sit on the factory rather than on the call this scan
# resolves. See _keyword_site.
_OPERATOR_ATTRGETTER = "attrgetter"
_OPERATOR_GETTERS = frozenset({_OPERATOR_ATTRGETTER, _OPERATOR_METHODCALLER})
_OPERATOR_SELECTOR = "itemgetter"
_OPERATOR_FACTORIES = _OPERATOR_GETTERS | frozenset({_OPERATOR_SELECTOR})
_OPERATOR_MODULE = "operator"
# Namespace prefix for every ``operator`` name recorded in the imported-name
# table. The table's other values are entry points, so an unprefixed factory
# name would read as one; the prefix keeps the two apart in one dict.
_OPERATOR_ALIAS = "*op*"

_NOT_ENTRY_POINTS = frozenset({_PARTIAL, _DEVNULL, _PIPE, _STDOUT}) | frozenset(
    _OPERATOR_ALIAS + name for name in _OPERATOR_FACTORIES
)

# Calls the scan treats as pass-through: the reference handed in is the one
# tracked coming out. ``nullcontext`` literally returns its argument;
# ``staticmethod`` returns a wrapper that dereferences to the same callable;
# ``enter_context`` returns ``__enter__()``'s value, which for the context
# managers tracked here is the manager itself. Each one is a place a
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
     "enumerate", "chain"}
)

# Callables that yield elements of the containers handed to them, but only
# after a leading argument that is not one: a predicate for the itertools
# filters, a count for the heapq selectors. Reading that leading argument as a
# container would flag ``filter(subprocess.run, rows)``, where the runner
# merely decides which row comes out and never starts a process itself.
_TRAILING_CONTAINERS = frozenset(
    {"filter", "filterfalse", "takewhile", "dropwhile", "nlargest", "nsmallest"}
)

# Every callable that yields elements of its arguments, mapped to the first
# argument that is a container. One table rather than a branch per family, so
# a new element-yielding callable is one row and the resolution reads once.
_CONTAINER_ARGS: dict[str, int] = {
    label: 0 for label in _ELEMENT_BUILTINS | _PASS_THROUGH | {"getitem"}
} | {label: 1 for label in _TRAILING_CONTAINERS}

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
    "subprocess": {attr: attr for attr in _SUBPROCESS_ATTRS}
    | {"DEVNULL": _DEVNULL, "PIPE": _PIPE, "STDOUT": _STDOUT},
    "functools": {"partial": _PARTIAL},
    "os": {"popen": _OS_POPEN},
    _OPERATOR_MODULE: {
        name: _OPERATOR_ALIAS + name for name in _OPERATOR_FACTORIES
    },
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

    A ``**{}`` or ``**{"cwd": "."}`` splat is a literal dict whose keys are
    visible at parse time. If none of those keys are text-mode keywords the
    splat cannot select text mode, so it does not count as a splat for
    purposes of this check. Any key the scan cannot see, including a nested
    ``**inner`` inside the literal, is treated conservatively: the splat
    counts as opaque and the call is flagged.
    """
    for keyword in call.keywords:
        if keyword.arg is not None:
            continue
        if not isinstance(keyword.value, ast.Dict):
            return True
        # Literal dict: flag only if any key is a text-mode keyword or
        # the key is unknown (nested splat inside the dict literal).
        for key in keyword.value.keys:
            if key is None:
                return True  # nested ``**inner`` expands unknowns
            if not isinstance(key, ast.Constant):
                return True  # non-literal key: value unknown at parse time
            if key.value in _TEXT_MODE_KEYWORDS:
                return True
    return False


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
    call: ast.Call, modules: dict[str, str], functions: dict[str, str]
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

    ``nullcontext``, ``staticmethod`` and ``enter_context`` hand a reference
    straight back out too, and a dict or list method that selects one element
    (``TABLE.get("run")``, ``max(candidates)``) reads exactly as an unindexed
    subscript does: the element is not known, so the whole receiver answers.
    """
    label = _call_label(call)
    if isinstance(call.func, ast.Call):
        # ``attrgetter("run")(subprocess)`` is a call on a call, so the label
        # above is empty and every branch below keys off it. Nothing else here
        # can match, which is what makes returning straight out safe.
        return _resolve_operator_getter(call, call.func, modules, functions)
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
    first = _CONTAINER_ARGS.get(label)
    if first is not None and len(call.args) > first:
        # ``list(RUNNERS)`` reads every argument; ``filter(None, RUNNERS)`` and
        # ``nlargest(1, RUNNERS)`` read every argument after the first, because
        # theirs is a predicate or a count. Reading that leading argument as a
        # container would flag a runner that only decides which element comes
        # out and never starts a process itself.
        return _resolve_elements(list(call.args[first:]), modules, functions)
    view = _dict_view(call)
    if view is not None:
        return _resolve_elements(view, modules, functions)
    returned = functions.get(f"{label}{_CALL_SUFFIX}")
    if returned is not None:
        return returned
    if label == "getattr" and len(call.args) >= 2:
        return _module_attribute(call.args[0], call.args[1], modules, functions)
    return None


def _module_attribute(
    owner: ast.expr,
    attr: ast.expr,
    modules: dict[str, str],
    functions: dict[str, str],
) -> str | None:
    """Resolve the attribute *attr* names, read off the module *owner* names.

    ``getattr(subprocess, "run")`` and ``operator.attrgetter("run")(subprocess)``
    both spell the owner and the attribute as two separate expressions, so one
    resolution answers for both rather than two that can drift apart.
    """
    if isinstance(attr, ast.Constant) and attr.value in _FORWARDING_ATTRS:
        # ``getattr(subprocess.run, "__call__")`` composes the two shapes
        # below, so resolving the owner answers for the pair.
        return _resolve_callable(owner, modules, functions)
    held = _owner_module(owner, modules)
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


def _operator_label(factory: ast.Call, functions: dict[str, str]) -> str:
    """Return the canonical ``operator`` factory *factory* builds, or ``""``.

    Reads both spellings: an attribute on an imported ``operator`` module, and
    a name bound by ``from operator import ... as ...``. A name reaching
    neither is some other callable that happens to share a word, which is why
    a local ``def itemgetter`` does not answer here.
    """
    func = factory.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        owner = functions.get(_OPERATOR_ALIAS + func.value.id)
        if owner == _OPERATOR_MODULE and func.attr in _OPERATOR_FACTORIES:
            return func.attr
        return ""
    if isinstance(func, ast.Name):
        canonical = functions.get(func.id, "")
        if canonical.startswith(_OPERATOR_ALIAS):
            return canonical[len(_OPERATOR_ALIAS) :]
    return ""


def _resolve_operator_getter(
    call: ast.Call,
    factory: ast.Call,
    modules: dict[str, str],
    functions: dict[str, str],
) -> str | None:
    """Resolve ``attrgetter("run")(subprocess)`` and ``itemgetter(0)(RUNNERS)``.

    The factory call names what to read; the call using it names what to read
    it from. Neither node alone spells a runner, which is what makes the pair
    an evasion: a scan reading only the outer ``func`` sees a call on a call
    and stops one step short of the entry point.
    """
    label = _operator_label(factory, functions)
    if not label or not call.args:
        return None
    if label == _OPERATOR_SELECTOR:
        # The index is not modelled, exactly as for a subscript, so every
        # element of the container handed in answers.
        return _resolve_elements(list(call.args), modules, functions)
    if not factory.args:
        return None
    return _module_attribute(call.args[0], factory.args[0], modules, functions)


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
    node: ast.Attribute, modules: dict[str, str], functions: dict[str, str]
) -> str | None:
    """Return the subprocess entry point ``owner.attr`` names, or ``None``."""
    owner = _owner_module(node.value, modules)
    if owner is None:
        owner = _module_from_container(node.value, modules)
    attr = node.attr
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


def _class_scope(body: list[ast.stmt]) -> list[ast.stmt]:
    """Return every statement of *body* that runs in the same class namespace.

    A class body executes like any other block, so a binding inside an ``if``,
    a ``try`` or a ``match`` lands in the class namespace exactly as one at the
    top level does. A nested function or class opens its own namespace and both
    already have their own handling, so the walk stops there rather than
    reading a method local as a class attribute.
    """
    found: list[ast.stmt] = []
    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        found.append(statement)
        for field in ("body", "orelse", "finalbody"):
            found.extend(_class_scope(getattr(statement, field, [])))
        for block in list(getattr(statement, "handlers", ())) + list(
            getattr(statement, "cases", ())
        ):
            found.extend(_class_scope(block.body))
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
    are recorded under the attribute prefix and read back the same way. Every
    binding shape counts, not the plain assignment alone: an annotation, a
    walrus, an in-place extension, a loop target and a match capture each
    outlive their statement and leave a class attribute behind. The walrus
    pass is additive rather than an arm of the same branch, because
    ``x = (runner := subprocess.run)`` binds two attributes at once.
    """
    found: list[tuple[str, ast.expr]] = []
    for statement in node.body:
        found.extend(_class_walrus(statement))
    for statement in _class_scope(node.body):
        pairs: list[tuple[str, ast.expr]] = []
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.NamedExpr):
            pairs = _assign_bindings(statement.value)
        elif isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            pairs = _assign_bindings(statement)
        elif isinstance(statement, (ast.For, ast.AsyncFor)):
            pairs = _iter_bindings(statement.target, statement.iter)
        elif isinstance(statement, ast.Match):
            pairs = _match_bindings(statement)
        found.extend((_ATTRIBUTE + name, bound) for name, bound in pairs)
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
    comprehension targets, ``match`` captures, mutating method calls,
    ``setattr`` calls, ``with`` targets, class bodies, and default arguments,
    every one of which binds a name without an assignment statement to find.
    Assignment targets are unpacked, so a name bound by destructuring is as
    visible as one bound on its own.
    """
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
            found.extend(_assign_bindings(node))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            found.extend(_entered(node))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            # ``for runner in (subprocess.run,)`` binds a name with no
            # assignment statement anywhere in sight.
            found.extend(_iter_bindings(node.target, node.iter))
        elif isinstance(node, ast.Call):
            found.extend(_mutation_bindings(node))
            found.extend(_installed(node))
        elif isinstance(node, ast.Match):
            found.extend(_match_bindings(node))
        elif isinstance(node, ast.ClassDef):
            found.extend(_class_bindings(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            found.extend(_defaults(node.args))
            if not isinstance(node, ast.Lambda):
                # A lambda body is an expression, so it holds no return for
                # _return_bindings to attribute, and no name to attribute it
                # to. Asking anyway read an attribute lambdas do not have.
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
                elif alias.name == _OPERATOR_MODULE:
                    # Recorded beside the imported names rather than in
                    # ``modules`` because ``operator`` holds no entry point.
                    # It only names the factories that reach one.
                    functions[_OPERATOR_ALIAS + (alias.asname or alias.name)] = (
                        _OPERATOR_MODULE
                    )
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


def _module_sources(value: ast.expr) -> list[str]:
    """Return every name *value* may evaluate to, unwinding containers.

    A module reference reaches a name through a container as easily as
    through a plain assignment: ``[subprocess][0]`` and ``HOLDER[0]`` both
    hand the module back with no name on the right to match against. The
    index is not modelled, exactly as for a subscript elsewhere, so every
    element answers, breadth-first so the answer follows source order.

    Only the node handed in is unwound. A name bound to another binding is
    left to the caller's fixpoint, which already settles those, and keeping
    the walk inside one expression is what bounds it: chasing bindings from
    here re-walks a chain of length N once per link and costs N squared.

    The queue is a deque because a list pops its front by shifting every
    remaining element. A wide container puts all of its elements in at once,
    so that shift costs the width on every pop. It hides at the sizes real
    sources reach, where the shift is a cache-friendly move, and shows up
    plainly past it: 50000 elements took 0.160s, 100000 took 0.664 and 200000
    took 2.779, near enough 4x per doubling.
    """
    queue = deque([value])
    found: list[str] = []
    while queue:
        node = queue.popleft()
        if isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Subscript):
            queue.append(node.value)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            queue.extend(node.elts)
    return found


def _settle(
    bindings: list[tuple[str, ast.expr]],
    seed: dict[str, str],
    *,
    blocked: set[str] | None = None,
) -> dict[str, str]:
    """Grow *seed* with every name that inherits from a name already in it.

    ``sp = subprocess`` and ``runner = base`` are one problem twice: a name
    takes on what another name holds, with no import or construction site of
    its own to read. A container in between changes nothing, so sources are
    read through one. Each pass can only add names and there are finitely
    many, so the repetition settles.

    Sources do not depend on what has settled, so they are read once per
    value node rather than once per pass or once per name. Reading them per
    pass re-walks a chain of length N once per link: 20000 links took 83.2
    seconds against a 10 second budget. Reading them per name re-walks a
    shared node once per name, and an unpacking that does not line up pairs
    every name with the whole right side, so 4000 names took 4.5 seconds
    against a 3 second budget.

    Which group to revisit is decided by the dependency edges rather than by
    repeating the sweep. A sweep that repeats until nothing changes learns
    one link per pass on a chain of aliases and scans every group on every
    pass, which is quadratic: 8000 links took 14.0 seconds. Indexing each
    group under the names it waits on wakes only the groups a newly settled
    name can answer for, and a group that has settled is skipped outright, so
    each group is read once and each edge is followed once.
    """
    blocked = blocked or set()
    grown = {name: value for name, value in seed.items() if name not in blocked}
    groups: dict[int, tuple[list[str], list[str]]] = {}
    for name, value in bindings:
        key = id(value)
        if key not in groups:
            groups[key] = (_module_sources(value), [])
        groups[key][1].append(name)
    waiting: dict[str, list[int]] = {}
    for key, (candidates, _) in groups.items():
        for candidate in candidates:
            waiting.setdefault(candidate, []).append(key)
    settled: set[int] = set()
    queue = deque(groups)
    while queue:
        key = queue.popleft()
        if key in settled:
            continue
        candidates, names = groups[key]
        pending = [one for one in names if one not in grown and one not in blocked]
        if not pending:
            settled.add(key)
            continue
        source = next((one for one in candidates if one in grown), None)
        if source is None:
            continue
        for one in pending:
            grown[one] = grown[source]
            queue.extend(waiting.get(one, ()))
        settled.add(key)
    return grown


def _module_from_container(node: ast.expr, modules: dict[str, str]) -> str | None:
    """Return the module every element of a subscripted container maps to.

    ``[subprocess][0].run`` resolves the attribute against the sole module
    the container holds. Only resolves when every element in the innermost
    unwound container names the same module: ``[os, subprocess][1].run``
    stays unresolved because index arithmetic is not modelled and the two
    elements disagree.
    """
    while isinstance(node, ast.Subscript):
        node = node.value
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    found: set[str] = set()
    for elt in node.elts:
        m = _owner_module(elt, modules)
        if m is None:
            return None
        found.add(m)
    return found.pop() if len(found) == 1 else None



def _owner_name(node: ast.expr) -> str | None:
    """Return the table key the owner expression *node* reads under.

    A class body binds its attributes under the attribute prefix, the same
    way the function table records them, so ``Holder.sp`` reads back exactly
    as a plain ``sp`` does.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _ATTRIBUTE + node.attr
    return None


def _owner_module(node: ast.expr, modules: dict[str, str]) -> str | None:
    """Return the module the owner expression *node* names, or ``None``."""
    key = _owner_name(node)
    return None if key is None else modules.get(key)


def _names_other_key(parent: ast.Subscript) -> bool:
    """Report whether a subscript spells out a key that is not the codec.

    ``runner.keywords["timeout"] = 1`` reaches the mapping but cannot reach
    the pin. A key the source does not spell out could be any key, so only a
    literal answers here.
    """
    key = parent.slice
    return isinstance(key, ast.Constant) and key.value != _ENCODING


def _rebound_builtins(
    tree: ast.Module, bindings: list[tuple[str, ast.expr]]
) -> frozenset[str]:
    """Name every mapping reader the file binds for itself.

    ``def len(mapping): mapping["encoding"] = None`` reads at the call site
    exactly as the builtin does and runs as a mutation. The trusted sets are
    spellings, not resolutions, so a file that defines or imports one of
    those spellings can redefine its way past the scan.

    A parameter binds a name the same way, and binds it to whatever the
    caller supplies. ``def sneak(len): len(runner.keywords)`` reads as the
    builtin and runs as whatever was passed in, which the file may never
    spell out: a method reached through an instance, a lambda handed on, a
    callback the framework calls.

    A parameter is answered per scope rather than for the whole file, because
    a parameter binds its name only inside its own function. Reading it
    file-wide let ``def harmless(list)`` in one helper stop every other
    ``list`` call in a 4800 line file from reading as the builtin, which is a
    false positive the scan does not have to take. See :func:`_scoped_shadows`.
    Everything else here really does bind for the whole module.
    """
    found = {name for name, _ in bindings} | _imported_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return frozenset(found & _SHADOWABLE_READERS)


def _reader_params(node: ast.AST) -> frozenset[str]:
    """Name every mapping reader the parameters of *node* shadow."""
    args = getattr(node, "args", None)
    if not isinstance(args, ast.arguments):
        return frozenset()
    every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        every.append(args.vararg)
    if args.kwarg is not None:
        every.append(args.kwarg)
    return frozenset(arg.arg for arg in every) & _SHADOWABLE_READERS


def _scoped_shadows(
    node: ast.AST, parents: dict[int, ast.AST], shadowed: frozenset[str]
) -> frozenset[str]:
    """Add the readers the scopes enclosing *node* shadow with a parameter.

    Walked upward rather than recorded on the way down, because the parent
    map is already built and a mapping read is rare enough that paying per
    read costs less than paying per node. The walk is a loop, so a file that
    nests two thousand deep costs depth rather than a blown stack.
    """
    found: set[str] = set()
    current: ast.AST | None = node
    while current is not None:
        found.update(_reader_params(current))
        current = parents.get(id(current))
    return shadowed | found if found else shadowed


def _spares_pin(
    node: ast.AST,
    parent: ast.AST | None,
    grandparent: ast.AST | None,
    literal: bool,
    shadowed: frozenset[str],
) -> bool:
    """Report whether the keywords mapping at *node* leaves its codec standing.

    Six shapes are provably harmless: a dict method that reaches only the
    keys, a subscript that either loads or names some other key, a walk that
    yields the keys, a double-star splat that fills a fresh mapping for
    someone else, a builtin that only walks the keys, and, when *literal*
    says every bound value is a literal, a method that hands a value out, a
    copy, a render, or a comparison. Everything else counts against the pin,
    including handing the mapping to a function that could pass it on, which
    can change it out of sight.

    A dict method is spared only where it is called. Naming one without
    calling it answers with a bound method, and every bound method carries
    the mapping it came from under ``__self__``, which is the mapping itself
    and takes a write. ``runner.keywords.keys.__self__["encoding"] = None``
    reads as the tamest reader there is and drops the pin. *grandparent* is
    what separates the call from the bare name.

    *literal* is what separates a look from a leak. Rendering or comparing a
    mapping reaches its values, so a value carrying its own ``__repr__`` or
    ``__eq__`` runs code that can drop the pin. Copying reaches them one step
    later, because the copy holds the same objects the original does.
    Literals cannot run anything either way.

    *shadowed* names the readers the file binds for itself. Those resolve to
    the file's own code, so none of them is spared.
    """
    if isinstance(parent, ast.Attribute):
        called = isinstance(grandparent, ast.Call) and grandparent.func is parent
        return called and (
            parent.attr in _KEY_READERS or (literal and parent.attr in _VALUE_READERS)
        )
    if isinstance(parent, ast.Subscript):
        return isinstance(parent.ctx, ast.Load) or _names_other_key(parent)
    if isinstance(parent, _WALKING_PARENTS):
        return parent.iter is node
    if isinstance(parent, ast.keyword):
        return parent.arg is None
    if isinstance(parent, ast.Call):
        if not isinstance(parent.func, ast.Name) or parent.func.id in shadowed:
            return False
        return parent.func.id in _MAPPING_READERS or (
            literal
            and parent.func.id in (_RENDERING_READERS | _COPYING_READERS)
        )
    return literal and isinstance(parent, _INSPECTING_PARENTS)


def _partial_roots(
    bindings: list[tuple[str, ast.expr]], functions: dict[str, str]
) -> dict[str, str]:
    """Map every name holding a partial back to the name it was built under.

    An alias shares the partial's keyword mapping rather than copying it, so
    ``alias.keywords["encoding"] = None`` unpins the call made through the
    original name too. Resolving both to one root is what lets a mutation
    found under either name answer for both.
    """
    seed = {
        name: name
        for name, value in bindings
        if isinstance(value, ast.Call) and _is_partial(_call_label(value), functions)
    }
    return _settle(bindings, seed)


def _renders_as_literal(value: ast.expr) -> bool:
    """Answer whether rendering this value can only run builtin code.

    A literal answers for itself: a string, a number, or a bool renders
    without calling back into the module. Python writes several values that
    are still numbers as something other than a constant, though. ``-1`` is a
    unary minus over ``1``, and ``60 * 60`` is arithmetic over two of them.
    Both fold to a number the moment the partial is built, so both render
    through builtin code alone.

    Containers answer the same way one level up. A tuple, list, set, or
    mapping display renders by rendering what it holds, so it is safe exactly
    while every leaf in it is. One name anywhere inside is enough to lose
    that: rendering reaches the name's own ``__repr__``, and a splat hides
    what it spreads, so neither can be read as a literal here.
    """
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, ast.UnaryOp):
        return _renders_as_literal(value.operand)
    if isinstance(value, ast.BinOp):
        return _renders_as_literal(value.left) and _renders_as_literal(value.right)
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return all(_renders_as_literal(one) for one in value.elts)
    if isinstance(value, ast.Dict):
        return all(
            key is not None and _renders_as_literal(key) and _renders_as_literal(one)
            for key, one in zip(value.keys, value.values, strict=True)
        )
    return False


def _literal_roots(
    bindings: list[tuple[str, ast.expr]],
    functions: dict[str, str],
    roots: dict[str, str],
) -> frozenset[str]:
    """Name the partial roots whose bound keyword values are every one a literal.

    Rendering or comparing a keywords mapping reaches every value it holds, so
    a value carrying its own ``__repr__`` or ``__eq__`` runs code that can drop
    the pin while the source still reads as a look. A literal cannot, for the
    reason :func:`_renders_as_literal` gives.

    A root that is built more than once keeps the answer only while every one
    of its constructions is literal, and a double-star splat never is, because
    what it spreads is not visible here.
    """
    settled: dict[str, bool] = {}
    for name, value in bindings:
        if not isinstance(value, ast.Call):
            continue
        if not _is_partial(_call_label(value), functions):
            continue
        literal = all(
            keyword.arg is not None and _renders_as_literal(keyword.value)
            for keyword in value.keywords
        )
        root = roots.get(name, name)
        settled[root] = settled.get(root, True) and literal
    return frozenset(root for root, literal in settled.items() if literal)


def _getter_names_keywords(factory: ast.Call, functions: dict[str, str]) -> bool:
    """Report whether *factory* builds an attrgetter that reads ``keywords``.

    An attrgetter can name several attributes at once, and answers with a
    tuple holding one value per name. The mapping is in that tuple whichever
    position it was asked for in, so any name matching is enough.

    Reaching it out of that tuple takes a subscript this scan does not model,
    so ``attrgetter("keywords", "func")(runner)[0]["encoding"] = None`` is
    read as a look and stays spared. Measured, not assumed: that spelling
    does undo the pin at runtime. It is left open because closing it needs
    the whole tuple-index hop threaded into the sparing rule for a spelling
    nothing writes, while the one-name form above is the one that appears.
    """
    if _operator_label(factory, functions) == _OPERATOR_METHODCALLER:
        return _dunder_methodcaller(factory)
    if _operator_label(factory, functions) != _OPERATOR_ATTRGETTER:
        return False
    return any(_names_keywords(arg) for arg in factory.args)


def _dunder_methodcaller(factory: ast.Call) -> bool:
    """Report whether a methodcaller runs an attribute read for ``keywords``.

    ``methodcaller("__getattribute__", "keywords")`` names the dunder as a
    string and the attribute as its argument, so neither node spells the
    mapping and the pair reads as an ordinary call on a call. What it builds
    fetches the same dict ``attrgetter("keywords")`` does.
    """
    if not factory.args or not isinstance(factory.args[0], ast.Constant):
        return False
    if factory.args[0].value not in _ATTR_DUNDERS:
        return False
    return any(_names_keywords(arg) for arg in factory.args[1:])


def _keyword_fetchers(
    bindings: list[tuple[str, ast.expr]], functions: dict[str, str]
) -> dict[str, str]:
    """Map every name that fetches a keywords mapping to how it asks for one.

    Two kinds arrive here. ``getattr`` and anything renamed from it take the
    attribute name as an argument, so the call site decides what is fetched.
    An attrgetter is built with the name already in it, so the binding decides
    and the call supplies only the owner.

    Assignments are revisited until the set settles, because a rename can be
    renamed again.
    """
    found = {_GETATTR: _FETCH_NAMED}
    for name, value in bindings:
        if isinstance(value, ast.Call) and _getter_names_keywords(value, functions):
            found[name] = _FETCH_FIXED
    growing = True
    while growing:
        growing = False
        for name, value in bindings:
            if not isinstance(value, ast.Name) or value.id not in found:
                continue
            if found.get(name) != found[value.id]:
                found[name] = found[value.id]
                growing = True
    return found


def _fetched_keywords(
    node: ast.AST, functions: dict[str, str], fetchers: dict[str, str]
) -> ast.expr | None:
    """Return the owner whose keywords mapping a fetching call reaches.

    A third argument to ``getattr`` is the default, which decides nothing
    here: a partial always carries a keywords mapping, so the attribute is
    always found and the default is never the value that comes back.
    """
    if not isinstance(node, ast.Call):
        return None
    return _dunder_fetch(node) or _getter_fetch(node, functions, fetchers)


def _names_keywords(node: ast.expr) -> bool:
    """Report whether *node* is the constant string ``keywords``."""
    return isinstance(node, ast.Constant) and node.value == _KEYWORDS


def _dunder_fetch(call: ast.Call) -> ast.expr | None:
    """Return the owner in ``x.__getattribute__("keywords")``, or None.

    An attribute read is a call to one of these dunders, so spelling the call
    out by hand reaches the same mapping the attribute does. ``__getattr__``
    joins it because a partial subclass can define one, and a scan that reads
    only the sugar lets either spelling undo a pin in silence.
    """
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in _ATTR_DUNDERS:
        return None
    if len(call.args) == 1:
        return func.value if _names_keywords(call.args[0]) else None
    if len(call.args) == 2 and _names_keywords(call.args[1]):
        # ``object.__getattribute__(runner, "keywords")`` runs the same
        # descriptor the bound spelling runs, reached off the base class
        # instead of off the partial, so the owner arrives as an argument
        # rather than as the attribute's value. Measured: it drops the pin.
        return call.args[0]
    return None


def _getter_fetch(
    call: ast.Call, functions: dict[str, str], fetchers: dict[str, str]
) -> ast.expr | None:
    """Return the owner a ``getattr`` or ``attrgetter`` call reads, or None.

    ``attrgetter("keywords")(runner)`` splits the question across two calls:
    the factory names the attribute, the call names what to read it from.
    Neither node alone spells the mapping, which is what makes the pair an
    evasion, and binding the factory to a name splits it across two
    statements as well.
    """
    if isinstance(call.func, ast.Call):
        if not _getter_names_keywords(call.func, functions):
            return None
        return call.args[0] if call.args else None
    if isinstance(call.func, ast.Name):
        return _named_fetch(call, fetchers.get(call.func.id))
    if isinstance(call.func, ast.Attribute):
        # A fetcher reached through a dotted name fetches what the bare name
        # fetches. ``builtins.getattr`` is the builtin itself, and a class
        # body that binds ``fetch = getattr`` hands the same callable out as
        # ``Holder.fetch``. Reading only the bare name lets either spelling
        # reach the mapping in silence.
        return _named_fetch(call, fetchers.get(call.func.attr))
    # Known and open: a fetcher stored as a container value stays missed.
    # ``d = {"f": getattr}`` followed by ``d["f"](runner, "keywords")`` puts an
    # ``ast.Subscript`` in call position, and resolving it needs to know both
    # which key the subscript reads and what that key held at that point in
    # execution. That is data-flow analysis, not the name resolution this
    # detector does, and the same hole covers list and tuple elements. The
    # shape does leak: run the assignment, the subscripted call, and a render
    # of the result and the pin moves from ``'utf-8'`` to ``None``. Left open
    # rather than papered over, alongside the ``dict(**m)`` and multi-name
    # ``attrgetter`` limitations recorded elsewhere in this module.
    return None


def _named_fetch(call: ast.Call, kind: str | None) -> ast.expr | None:
    """Return the owner a fetching call named by *kind* reads, or None.

    A fixed fetcher was built already knowing the attribute, so the first
    argument is the owner. A named one is told the attribute at the call, so
    the second argument has to be the one this scan cares about.
    """
    if kind == _FETCH_FIXED:
        return call.args[0] if call.args else None
    if kind != _FETCH_NAMED or len(call.args) not in (2, 3):
        return None
    return call.args[0] if _names_keywords(call.args[1]) else None


def _keyword_mapping(
    node: ast.AST, functions: dict[str, str], fetchers: dict[str, str]
) -> ast.expr | None:
    """Return the expression whose keywords mapping *node* reaches, if any.

    Four spellings arrive at the same dict. ``runner.keywords`` reads the
    attribute directly; ``getattr(runner, "keywords")`` asks for it by name;
    ``runner.__getattribute__("keywords")`` runs the lookup the first two
    delegate to; ``attrgetter("keywords")(runner)`` defers the owner to a
    second call. A scan that knows only the first lets the rest undo a pin in
    silence.
    """
    if isinstance(node, ast.Attribute) and node.attr == _KEYWORDS:
        return node.value
    return _fetched_keywords(node, functions, fetchers)


def _undone_pins(
    tree: ast.AST,
    roots: dict[str, str],
    literal_roots: frozenset[str],
    shadowed: frozenset[str],
    functions: dict[str, str],
    fetchers: dict[str, str],
) -> set[str]:
    """Return the partials whose bound codec the source can undo.

    ``functools.partial`` keeps its bound keywords in a plain dict that stays
    reachable through the result, so ``del runner.keywords["encoding"]`` and
    ``runner.keywords["encoding"] = None`` both drop a pin the construction
    site still spells out. Reading that site alone reports a codec the call
    will never use.

    Everything that is not a provable read counts, because a mapping handed
    to another function comes back changed with nothing at this site to say
    so. The answer errs toward flagging, which is the direction this scan
    takes throughout.
    """
    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    undone: set[str] = set()
    for node in ast.walk(tree):
        owner = _keyword_mapping(node, functions, fetchers)
        if owner is None:
            continue
        name = _owner_name(owner)
        root = roots.get(name) if name is not None else None
        parent = parents.get(id(node))
        grandparent = parents.get(id(parent)) if parent is not None else None
        if _spares_pin(
            node,
            parent,
            grandparent,
            root in literal_roots,
            _scoped_shadows(node, parents, shadowed),
        ):
            continue
        if root is not None:
            undone.add(root)
    return undone


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
    mark, through a container or not, because rebinding the name changes
    nothing about what it holds.
    """
    seed = {
        name: name
        for name, value in bindings
        if isinstance(value, ast.Call)
        and _is_partial(_call_label(value), functions)
        and _supplies_capture(value, modules, functions)
    }
    return set(_settle(bindings, seed))


def _pins_codec(value: ast.expr, functions: dict[str, str]) -> bool:
    """Report whether *value* is a partial fixing the codec where it is built."""
    return (
        isinstance(value, ast.Call)
        and _is_partial(_call_label(value), functions)
        and _pins_utf8(value)
    )


def _imported_names(tree: ast.Module) -> set[str]:
    """Name every binding an import statement makes.

    ``from subprocess import run as runner`` rebinds a name to the bare entry
    point, exactly as ``runner = subprocess.run`` does, and the scan reads
    neither as pinning a codec. A construction that pinned one earlier under
    that name says nothing about the call that follows.

    The answer is order-blind, which matches how a rebinding is read
    everywhere else here: a name bound bare anywhere carries no pin, whether
    the bare binding comes before the pinned one or after.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for alias in node.names:
            found.add(alias.asname or alias.name.split(".")[0])
    return found


def _prepinned(
    bindings: list[tuple[str, ast.expr]],
    functions: dict[str, str],
    undone: set[str],
    imported: set[str],
) -> set[str]:
    """Name every callable whose codec was pinned where it was built.

    The mirror of :func:`_presupplied`. ``partial(subprocess.run,
    capture_output=True, encoding="utf-8")`` decides the codec at the
    construction site, and the call site that adds ``text=True`` carries no
    ``encoding`` keyword for :func:`_pins_utf8` to find. Without this, a call
    that pins its codec correctly reads as a violation, which is worse than a
    missed one: it nags the author who did the right thing. An alias inherits
    the pin, through a container or not, because rebinding the name changes
    nothing about what it holds.

    A construction site the source can undo supplies no pin at all, which is
    what keeps ``del runner.keywords["encoding"]`` reported at both ends.

    A name is only trusted when every binding it carries pins the codec. One
    name can be bound in two scopes, and a pinned partial built inside some
    unrelated function says nothing about the runner called out here. The
    same holds after the fixpoint has grown the set, because a name can
    inherit a pin from an alias and then be rebound to something bare.

    A name an import binds is one of those bare bindings. It carries no
    keywords, so it pins nothing.
    """
    pinning: dict[str, bool] = {}
    source_groups: dict[int, tuple[bool, bool, list[str], set[str]]] = {}
    for name, value in bindings:
        pins = _pins_codec(value, functions)
        pinning[name] = pinning.get(name, True) and pins
        key = id(value)
        if key not in source_groups:
            empty_container = (
                isinstance(value, (ast.List, ast.Tuple, ast.Set)) and not value.elts
            ) or (isinstance(value, ast.Dict) and not value.keys)
            source_groups[key] = (
                pins,
                empty_container,
                _module_sources(value),
                set(),
            )
        source_groups[key][3].add(name)
    seed = {
        name: name
        for name, pins in pinning.items()
        if pins and name not in undone and name not in imported
    }
    bound = set(pinning)
    blocked: set[str] = set()
    waiting: dict[str, list[int]] = {}
    for key, (pins, empty_container, sources, names) in source_groups.items():
        if pins:
            continue
        if (not sources and not empty_container) or any(
            source not in bound for source in sources
        ):
            blocked.update(names)
        for source in sources:
            waiting.setdefault(source, []).append(key)
    queue = deque(blocked)
    blocked_groups: set[int] = set()
    while queue:
        source = queue.popleft()
        for key in waiting.get(source, ()):
            if key in blocked_groups:
                continue
            blocked_groups.add(key)
            for name in source_groups[key][3]:
                if name not in blocked:
                    blocked.add(name)
                    queue.append(name)
    return set(_settle(bindings, seed, blocked=blocked))


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
    module or through a reference is not covered. Call sites are indexed in
    the same walk that finds the definitions, because walking the tree once
    per definition is quadratic in a file that holds many of both.
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


class _Names(NamedTuple):
    """Everything one pass over a tree learns about the names in it.

    Held as a named bundle rather than a bare tuple because the members are
    six tables that all read alike at a call site, and a positional mix-up
    between two of them would type-check silently.
    """

    modules: dict[str, str]
    functions: dict[str, str]
    containers: dict[str, _Container]
    presupplied: set[str]
    voided: set[int]
    """Construction sites whose bound codec the source undoes.

    Node identity is the key because a construction site is a value node, not
    a name. Every node stays alive for as long as the tree that owns it,
    which outlives this answer, so an address cannot be recycled underneath
    it.
    """

    prepinned: set[str]


def _subprocess_names(tree: ast.Module) -> _Names:
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
    modules = _settle(bindings, modules)
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
    roots = _partial_roots(bindings, functions)
    undone = _undone_pins(
        tree,
        roots,
        _literal_roots(bindings, functions, roots),
        _rebound_builtins(tree, bindings),
        functions,
        _keyword_fetchers(bindings, functions),
    )
    return _Names(
        modules,
        functions,
        containers,
        _presupplied(bindings, modules, functions),
        {
            id(value)
            for name, value in bindings
            if name in undone and isinstance(value, ast.Call)
        },
        _prepinned(bindings, functions, undone, _imported_names(tree)),
    )


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
    if _call_label(call) in presupplied:
        # The mirror image: capture was fixed where the partial was built, so
        # this site adding text mode completes a decoding call between them.
        return True
    if target in _ALWAYS_CAPTURES:
        # check_output supplies stdout=PIPE itself. Text mode is the whole
        # condition, so requiring a capture keyword as well misses the decode.
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


def _keyword_site(call: ast.Call, functions: dict[str, str]) -> ast.Call:
    """Return the call whose keywords decide what *call* does.

    ``methodcaller("run", ["x"], text=True)(subprocess)`` runs
    ``subprocess.run(["x"], text=True)``, but the keywords are given to the
    factory, not to the call this scan resolves. Reading the resolved node
    alone finds no keywords at all and reports nothing, which is what let the
    shape through.

    Every other shape answers for itself, so the call handed in comes back
    unchanged.
    """
    factory = call.func
    if (
        isinstance(factory, ast.Call)
        and _operator_label(factory, functions) == _OPERATOR_METHODCALLER
    ):
        return factory
    return call


def unpinned_lines(source: str) -> list[int]:
    """Return the line numbers of text-capturing calls that do not pin UTF-8."""
    tree = ast.parse(source)
    names = _subprocess_names(tree)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _target(node, names.modules, names.functions, names.containers)
        if target is None:
            continue
        if target == "os.popen":
            # os.popen has no encoding parameter at all, so the only compliant
            # move is to not use it.
            offenders.append(node.lineno)
            continue
        site = _keyword_site(node, names.functions)
        if target not in _DECODES_UNCONDITIONALLY and not _captures_text(
            site, names.functions, target, names.modules, names.presupplied
        ):
            continue
        if _pins_utf8(site) and id(node) not in names.voided:
            continue
        if (
            _keyword(site, "encoding") is None
            and not _has_splat(site)
            and _call_label(node) in names.prepinned
        ):
            # The codec was pinned where this callable was built, and nothing
            # since has undone it, so the call site needs no keyword of its
            # own. A call site that names an encoding, or splats keywords this
            # scan cannot read, overrides that pin and answers for itself.
            continue
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
        (
            "import subprocess\nclass C:\n    def m(self):\n"
            "        runner = subprocess.run\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "a method local opens its own namespace and is not a class attribute",
        ),
        (
            "import subprocess\nclass C:\n    if True:\n        runner = subprocess.run\n"
            "C.runner(['x'], text=True, capture_output=True, encoding='utf-8')",
            "a class attribute reached through a block is still pinned when pinned",
        ),
        (
            "import subprocess\nclass C:\n    try:\n        import fast\n"
            "    except ImportError:\n        pass\nprint(1)",
            "a class body block that binds no entry point stays quiet",
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
        (
            'import subprocess\n'
            'next(filter(subprocess.run, [print]))(["x"], capture_output=True, text=True)',
            "a filter predicate decides which element comes out and is not one",
        ),
        (
            'import subprocess\n'
            'from heapq import nlargest\n'
            'nlargest(1, [print])[0](["x"], capture_output=True, text=True)',
            "a selector over a container of something else selects something else",
        ),
        (
            'import subprocess\n'
            'from itertools import chain\n'
            'next(chain())(["x"], capture_output=True, text=True)',
            "chain with nothing to chain yields nothing that starts a process",
        ),
        (
            'import subprocess\n'
            'next(filter(None, [subprocess.run]))(\n'
            '    ["x"], capture_output=True, text=True, encoding="utf-8"\n'
            ')',
            "a runner reached through a filter is still pinned by its call site",
        ),
        (
            'import operator, shutil\n'
            'operator.attrgetter("which")(shutil)(["x"], capture_output=True, text=True)',
            "an attribute read off a module we do not track starts nothing",
        ),
        (
            'import subprocess\n'
            'from operator import itemgetter\n'
            'itemgetter(0)([print])(["x"], capture_output=True, text=True)',
            "a selector over a container of something else selects something else",
        ),
        (
            'import subprocess\n'
            'from operator import attrgetter\n'
            'attrgetter("run")(subprocess)(\n'
            '    ["x"], capture_output=True, text=True, encoding="utf-8"\n'
            ')',
            "a runner reached through a getter is still pinned by its call site",
        ),
        (
            'import subprocess\n'
            'def itemgetter(index):\n'
            '    return lambda rows: print\n'
            'itemgetter(0)([subprocess.run])(["x"], capture_output=True, text=True)',
            "a local factory sharing the name is not the one from operator",
        ),
        (
            'import operator, subprocess\n'
            'operator.attrgetter("Popen")(subprocess)(["x"])',
            "a spawn with neither capture nor text decodes nothing",
        ),
        (
            'import shutil\n'
            'module = [shutil][0]\n'
            'module.which("x", capture_output=True, text=True)',
            "a container holding a module we do not track holds no entry point",
        ),
        (
            'import subprocess\n'
            'class Holder:\n'
            '    sp = subprocess\n'
            'Holder.sp.run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "a module reached through a class body is still pinned at its call site",
        ),
        (
            'import subprocess\n'
            'module = [subprocess][0]\n'
            'module.run(["x"])',
            "a module reached through a container still decodes nothing untold",
        ),
        (
            'import functools, subprocess\n'
            'base = functools.partial(subprocess.run, capture_output=True)\n'
            'holders = [base]\n'
            'runner = holders[0]\n'
            'runner(["x"], text=True, encoding="utf-8")',
            "a partial reached through a container is still pinned at its call site",
        ),
        (
            'import functools, subprocess\n'
            'base = functools.partial(subprocess.run)\n'
            'holders = [base]\n'
            'runner = holders[0]\n'
            'runner(["x"], text=True)',
            "a partial that fixed no capture leaves nothing to decode",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'other.keywords["encoding"] = None\n'
            'runner(["x"])',
            "a mapping belonging to some other name leaves this pin standing",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'assert runner.keywords.get("encoding") == "utf-8"\n'
            'runner(["x"])',
            "asking the mapping what it holds cannot change what it holds",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'assert "encoding" in runner.keywords\n'
            'runner(["x"])',
            "testing the mapping for a key cannot change what it holds",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'codec = runner.keywords["encoding"]\n'
            'runner(["x"])',
            "loading one key out of the mapping leaves the mapping alone",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'for key in runner.keywords:\n'
            '    print(key)\n'
            'runner(["x"])',
            "walking the mapping yields its keys and leaves the mapping alone",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'names = [key for key in runner.keywords]\n'
            'runner(["x"])',
            "a comprehension walks the mapping the same way a for loop does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'print(f"{runner.keywords}")\n'
            'runner(["x"])',
            "interpolating the mapping into a string only formats it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'copied = dict(**runner.keywords)\n'
            'runner(["x"])',
            "splatting the mapping fills a new dict and leaves the source alone",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'for key in runner.keywords:\n'
            '    print(key)\n'
            'runner(["x"], text=True)',
            "a walked mapping still answers for a call site that adds the text",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner.keywords["timeout"] = 1\n'
            'runner(["x"], text=True)',
            "storing under some other key leaves the bound codec where it was",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'alias(["x"], text=True)',
            "an alias that only ever holds the pinned runner still answers for it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'del runner.keywords["timeout"]\n'
            'runner(["x"], text=True)',
            "deleting some other key leaves the bound codec where it was",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'seen = len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a builtin that only measures the mapping cannot change it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner(["x"], text=True)',
            "a codec pinned where the partial was built covers the call site",
        ),
        (
            'import functools, subprocess\n'
            'base = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'holders = [base]\n'
            'runner = holders[0]\n'
            'runner(["x"], text=True)',
            "the pin follows the partial through a container",
        ),
        (
            "import operator, subprocess\n"
            'operator.methodcaller(\n'
            '    "run", ["x"], capture_output=True, text=True, encoding="utf-8"\n'
            ")(subprocess)",
            "a methodcaller carrying the codec pins it where the keywords sit",
        ),
        (
            "import operator, subprocess\n"
            'operator.methodcaller("run", ["x"])(subprocess)',
            "a methodcaller that captures nothing decodes nothing",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'next_alias = alias\n'
            'next_alias(["x"], text=True)',
            "a wholly pinned alias chain keeps the construction-site codec",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'holders = []\n'
            'holders.append(runner)\n'
            'alias = holders[0]\n'
            'alias(["x"], text=True)',
            "an empty container can later receive a wholly pinned runner",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'holders = {}\n'
            'holders["runner"] = runner\n'
            'alias = holders["runner"]\n'
            'alias(["x"], text=True)',
            "an empty mapping can later receive a wholly pinned runner",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=-1\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a negated number is written as a unary minus and still renders as a number",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=~1\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "every unary operator over a number answers with a number",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=60 * 60\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "arithmetic over two numbers answers with a number",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", args=(1, 2)\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a tuple of literals renders through the builtin tuple repr",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env={"A": "b"}\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a mapping display of literals renders through the builtin dict repr",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", args=[[1], {2: -3}]\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a container of containers is literal while every leaf of it is",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=1\n'
            ')\n'
            'seen = dict(runner.keywords)\n'
            'runner(["x"], text=True)',
            "copying a mapping of literals hands out nothing that can run code",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = repr(sorted(runner.keywords))\n'
            'runner(["x"], text=True)',
            "sorting a mapping answers with its keys, which are always strings",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = repr(tuple(runner.keywords))\n'
            'runner(["x"], text=True)',
            "rendering a tuple of keys renders strings, whatever the values are",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = dict(**runner.keywords)\n'
            'runner(["x"], text=True)',
            "a splat fills a fresh mapping for someone else, as every splat does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def fine(other):\n'
            '    seen = len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a parameter named for nothing in particular shadows nothing",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def fine(encoding, timeout):\n'
            '    seen = sorted(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a parameter named for a keyword is not a parameter named for a reader",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = runner.keywords.keys()\n'
            'runner(["x"], text=True)',
            "calling the reader answers with the keys and hands out no mapping",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=1\n'
            ')\n'
            'seen = runner.keywords.copy()\n'
            'runner(["x"], text=True)',
            "calling a value reader over literals is still the read it always was",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = len(runner.keywords) + max(runner.keywords).count("a")\n'
            'runner(["x"], text=True)',
            "a reader that answers with a number or a key hands back no way in",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = frozenset(runner.keywords) | set(sorted(runner.keywords))\n'
            'runner(["x"], text=True)',
            "a fresh container of keys holds strings and nothing that leads back",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'for key in runner.keywords:\n'
            '    seen = key\n'
            'runner(["x"], text=True)',
            "a plain walk yields the keys without ever naming an iterator",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = runner.__getattribute__("func")\n'
            'runner(["x"], text=True)',
            "a dunder fetch of some other attribute reaches no keywords mapping",
        ),
        (
            'import functools, operator, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = operator.attrgetter("func")(runner)\n'
            'runner(["x"], text=True)',
            "attrgetter naming another attribute selects no keywords mapping",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def attrgetter(name):\n'
            '    return lambda owner: {}\n'
            'seen = attrgetter("keywords")(runner)\n'
            'runner(["x"], text=True)',
            "a local attrgetter is some other callable sharing a word",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'fetch = getattr\n'
            'seen = fetch(runner, "func")\n'
            'runner(["x"], text=True)',
            "a getattr under another name still only answers for the name it asks",
        ),
        (
            'import functools, operator, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'fetch = operator.attrgetter("func")\n'
            'seen = fetch(runner)\n'
            'runner(["x"], text=True)',
            "an attrgetter bound to a name carries the attribute it was built for",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def attrgetter(*names):\n'
            '    return lambda owner: {}\n'
            'fetch = attrgetter("keywords")\n'
            'seen = fetch(runner)\n'
            'runner(["x"], text=True)',
            "a name bound to a local attrgetter fetches nothing from the partial",
        ),
        (
            'import functools, subprocess\n'
            'def harmless(list):\n'
            '    return list\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'seen = list(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a parameter shadows a reader inside its own function, not the file",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], **{})',
            "an empty literal-dict splat carries no text-mode key and returns bytes",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], **{"cwd": "."})',
            "a literal-dict splat with only non-text-mode keys cannot decode",
        ),
    ],
)
def test_detector_stays_quiet(source: str, why: str) -> None:
    """The guard must not fire on calls that decode nothing."""
    assert unpinned_lines(source) == [], f"false positive on {why}"


def test_a_lambda_carries_no_return_for_the_scan_to_attribute() -> None:
    """A lambda has no name, and no return to bind to one.

    ``_return_bindings`` reads ``node.name`` while building its result, and
    ``ast.Lambda`` has no such attribute. The read sat behind a comprehension
    that a lambda always leaves empty, because a lambda body is an expression
    and an expression cannot hold a ``return``. That made the call latent
    rather than live, but it was one edit away from an ``AttributeError`` and
    the type checker flagged it on every run. The scan now asks only the two
    node types that carry a name. The lambda default case in
    ``test_detector_flags_an_unpinned_call`` is the control proving the other
    half of the branch, ``_defaults``, still runs for lambdas.
    """
    lam = ast.parse("f = lambda a=subprocess.run: a").body[0]
    assert isinstance(lam, ast.Assign)
    assert isinstance(lam.value, ast.Lambda)
    assert not hasattr(lam.value, "name")
    assert [node for node in ast.walk(lam.value) if isinstance(node, ast.Return)] == []


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
            "import subprocess\nclass C:\n    runner: Any = subprocess.run\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "an annotated assignment in a class body binds a class attribute",
        ),
        (
            "import subprocess\nclass C:\n    (runner := subprocess.run)\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "a walrus in a class body binds a class attribute",
        ),
        (
            "import subprocess\nclass C:\n    held = [print]\n    held += [subprocess.run]\n"
            "C.held[0](['x'], text=True, capture_output=True)",
            "an in-place extension in a class body reaches the class attribute",
        ),
        (
            "import subprocess\nclass C:\n    if True:\n        runner = subprocess.run\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "a class body runs its if blocks in the class namespace",
        ),
        (
            "import subprocess\nclass C:\n    try:\n        runner = subprocess.run\n"
            "    except ImportError:\n        pass\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "a class body runs its try blocks in the class namespace",
        ),
        (
            "import subprocess\nclass C:\n    for runner in [subprocess.run]:\n        pass\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "a loop target in a class body outlives the loop as an attribute",
        ),
        (
            "import subprocess\nclass C:\n    match subprocess.run:\n        case runner:\n"
            "            pass\nC.runner(['x'], text=True, capture_output=True)",
            "a match capture in a class body binds a class attribute",
        ),
        (
            "import subprocess\nclass C:\n    match 1:\n        case 1:\n"
            "            runner = subprocess.run\n"
            "C.runner(['x'], text=True, capture_output=True)",
            "a class body runs its match case blocks in the class namespace",
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
        (
            'import subprocess\n'
            'next(filter(None, [subprocess.run]))(["x"], capture_output=True, text=True)',
            "filter yields the elements it was handed, so the runner comes out",
        ),
        (
            'import subprocess\n'
            'from itertools import filterfalse\n'
            'next(filterfalse(None, [subprocess.run]))(["x"], capture_output=True, text=True)',
            "filterfalse keeps what filter drops and yields the same elements",
        ),
        (
            'import subprocess\n'
            'from itertools import takewhile\n'
            'next(takewhile(None, [subprocess.run]))(["x"], capture_output=True, text=True)',
            "takewhile yields a prefix of its input, and a prefix holds elements",
        ),
        (
            'import subprocess\n'
            'from itertools import dropwhile\n'
            'next(dropwhile(None, [subprocess.run]))(["x"], capture_output=True, text=True)',
            "dropwhile yields a suffix of its input, and a suffix holds elements",
        ),
        (
            'import subprocess\n'
            'from itertools import chain\n'
            'next(chain([], [subprocess.run]))(["x"], capture_output=True, text=True)',
            "chain yields the elements of every container handed to it",
        ),
        (
            'import subprocess\n'
            'from heapq import nlargest\n'
            'nlargest(1, [subprocess.run])[0](["x"], capture_output=True, text=True)',
            "nlargest returns a list of the elements it selected from",
        ),
        (
            'import subprocess\n'
            'from heapq import nsmallest\n'
            'nsmallest(1, [subprocess.run])[0](["x"], capture_output=True, text=True)',
            "nsmallest selects from the same container from the other end",
        ),
        (
            'import operator, subprocess\n'
            'operator.attrgetter("run")(subprocess)(["x"], capture_output=True, text=True)',
            "attrgetter reads the named attribute off the module handed to it",
        ),
        (
            'import operator as op, subprocess\n'
            'op.attrgetter("run")(subprocess)(["x"], capture_output=True, text=True)',
            "an aliased operator module builds the same factory",
        ),
        (
            'import subprocess\n'
            'from operator import attrgetter\n'
            'name = "run"\n'
            'attrgetter(name)(subprocess)(["x"], capture_output=True, text=True)',
            "a computed attribute on a subprocess module still reaches one of ours",
        ),
        (
            'import subprocess\n'
            'from operator import itemgetter\n'
            'itemgetter(0)([subprocess.run])(["x"], capture_output=True, text=True)',
            "itemgetter selects an element, so the container it reads answers",
        ),
        (
            'import subprocess\n'
            'from operator import itemgetter as pick\n'
            'pick(0)([subprocess.run])(["x"], capture_output=True, text=True)',
            "an import alias renames the selector and nothing else",
        ),
        (
            'import subprocess\n'
            'from operator import itemgetter\n'
            'HOLDER = [subprocess.run]\n'
            'itemgetter(0)(HOLDER)(["x"], capture_output=True, text=True)',
            "a selector reading a named container reads what the name holds",
        ),
        (
            'import subprocess\n'
            'from operator import getitem\n'
            'getitem([subprocess.run], 0)(["x"], capture_output=True, text=True)',
            "getitem is the subscript spelled as a call",
        ),
        (
            'import subprocess\n'
            'module = [subprocess][0]\n'
            'module.run(["x"], capture_output=True, text=True)',
            "a module reaches a name through a container with no name to match",
        ),
        (
            'import subprocess\n'
            'HOLDER = (subprocess,)\n'
            'module = HOLDER[0]\n'
            'module.run(["x"], capture_output=True, text=True)',
            "the container holding the module can itself be behind a name",
        ),
        (
            'import subprocess\n'
            'class Holder:\n'
            '    sp = subprocess\n'
            'Holder.sp.run(["x"], capture_output=True, text=True)',
            "a class body binds a module alias that no import statement shows",
        ),
        (
            'import functools, subprocess\n'
            'base = functools.partial(subprocess.run, capture_output=True)\n'
            'holders = [base]\n'
            'runner = holders[0]\n'
            'runner(["x"], text=True)',
            "a partial keeps its fixed capture through a container",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'del runner.keywords["encoding"]\n'
            'runner(["x"])',
            "deleting the bound encoding leaves the locale codec behind",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'runner.keywords["encoding"] = None\n'
            'runner(["x"])',
            "overwriting the bound encoding asks for the locale codec by name",
        ),
        (
            'import functools, subprocess\n'
            'class A:\n'
            '    b = functools.partial(\n'
            '        subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            '    )\n'
            'a = A()\n'
            'a.b.keywords["encoding"] = None\n'
            'a.b(["x"])',
            "a partial bound in a class body is mutated the same way",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'runner.keywords.update({"encoding": None})\n'
            'runner(["x"])',
            "updating the mapping replaces the bound encoding wholesale",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'dropped = [runner.keywords.pop(k) for k in list(runner.keywords)]\n'
            'runner(["x"])',
            "a comprehension that walks the mapping can still empty it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'print(f"{runner.keywords.pop(\'encoding\')}")\n'
            'runner(["x"])',
            "interpolation formats whatever it is given, including a mutation",
        ),
        (
            'import functools, subprocess\n'
            'def mutate(mapping):\n'
            '    mapping.pop("encoding")\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, text=True, encoding="utf-8"\n'
            ')\n'
            'mutate(runner.keywords)\n'
            'runner(["x"])',
            "handing the mapping to something else changes it out of sight",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="latin-1"\n'
            ')\n'
            'runner(["x"], text=True)',
            "a construction site pinning the wrong codec pins nothing",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'del runner.keywords["encoding"]\n'
            'runner(["x"], text=True)',
            "a construction pin the source undoes covers no later call site",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner(["x"], text=True, encoding="latin-1")',
            "a call site naming its own codec overrides the one it was built with",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner(["x"], text=True, **overrides)',
            "a splat at the call site can carry an encoding nothing here can read",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'alias.keywords["encoding"] = None\n'
            'runner(["x"], text=True)',
            "an alias shares the keyword mapping rather than copying it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'alias = subprocess.run\n'
            'alias(["x"], capture_output=True, text=True)',
            "a later unpinned binding keeps a mixed alias out of the pinned set",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'raw = subprocess.run\n'
            'alias = runner\n'
            'alias = raw\n'
            'next_alias = alias\n'
            'next_alias(["x"], capture_output=True, text=True)',
            "a transitive unpinned binding taints every downstream alias",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'raw = subprocess.run\n'
            'holders = [runner, raw]\n'
            'alias = holders[1]\n'
            'alias(["x"], capture_output=True, text=True)',
            "a container with an unpinned alternative cannot confer a codec pin",
        ),
        (
            "import operator, subprocess\n"
            'operator.methodcaller("run", ["x"], capture_output=True, text=True)(\n'
            "    subprocess\n"
            ")",
            "methodcaller runs the entry point with keywords held one call out",
        ),
        (
            "import operator as op, subprocess\n"
            'op.methodcaller("run", ["x"], capture_output=True, text=True)(subprocess)',
            "an operator alias hides the methodcaller the same way",
        ),
        (
            "from operator import methodcaller\n"
            "import subprocess\n"
            'methodcaller("run", ["x"], capture_output=True, text=True)(subprocess)',
            "a directly imported methodcaller needs no module name at all",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'getattr(runner, "keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "getattr reaches the same mapping the attribute does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'getattr(runner, "keywords").pop("encoding")\n'
            'runner(["x"], text=True)',
            "a mapping fetched by getattr can be emptied by any of its methods",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner.__getattribute__("keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "the dunder getattr calls by hand is the lookup an attribute runs",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner.__getattr__("keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "the fallback dunder answers with the same mapping",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'fetch = getattr\n'
            'fetch(runner, "keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a getattr under another name fetches what getattr fetches",
        ),
        (
            'import functools, operator, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'operator.attrgetter("keywords")(runner)["encoding"] = None\n'
            'runner(["x"], text=True)',
            "attrgetter names the attribute on the factory and reads it on the call",
        ),
        (
            'import functools, subprocess\n'
            'from operator import attrgetter\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'attrgetter("keywords")(runner)["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a directly imported attrgetter needs no module name to reach it",
        ),
        (
            'import functools, operator, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'fetch = operator.attrgetter("keywords")\n'
            'fetch(runner)["encoding"] = None\n'
            'runner(["x"], text=True)',
            "an attrgetter bound to a name reads the attribute the same way",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'fetch = getattr\n'
            'again = fetch\n'
            'again(runner, "keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a rename of a rename still reaches the builtin it started as",
        ),
        (
            'import functools, subprocess\n'
            'key = "encoding"\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'runner.keywords[key] = None\n'
            'runner(["x"], text=True)',
            "a key that is not spelled out could be any key, including the codec",
        ),
        (
            'import functools, subprocess\n'
            'runner = subprocess.run\n'
            'def unrelated():\n'
            '    runner = functools.partial(print, encoding="utf-8")\n'
            '    return runner\n'
            'runner(["x"], capture_output=True, text=True)',
            "a pin bound to the same name somewhere else answers for nothing here",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'alias = subprocess.run\n'
            'alias(["x"], capture_output=True, text=True)',
            "an alias that inherits a pin and is then rebound holds it no longer",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'alias = subprocess.run\n'
            'second = alias\n'
            'second(["x"], capture_output=True, text=True)',
            "a name reading a rebound alias reads what the rebinding left",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'alias = subprocess.run\n'
            'second = alias\n'
            'third = second\n'
            'third(["x"], capture_output=True, text=True)',
            "a rebinding travels the whole chain that reads from it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'alias = runner\n'
            'second = alias\n'
            'alias = subprocess.run\n'
            'second(["x"], capture_output=True, text=True)',
            "reading an alias before it is rebound still reads one binding of two",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "repr renders every value, so a value's __repr__ runs and can drop the pin",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", args=(1, guard)\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a tuple holding one name renders that name, so the container is no literal",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env={"A": guard}\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a mapping display renders its values, so one name in it is enough",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=-guard\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "negating a name calls its __neg__ and answers with whatever that returns",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=60 * guard\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "arithmetic against a name answers with whatever that name multiplies to",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env={**spread}\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a mapping display that splats another mapping shows none of what it holds",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=(1, *rest)\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a starred element spreads what the tuple display does not show",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = dict(runner.keywords)\n'
            'runner(["x"], text=True)',
            "copying a mapping carries the same values, which carry their own repr",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'seen = repr(dict(runner.keywords))\n'
            'runner(["x"], text=True)',
            "rendering a copy renders the values the copy shares with the original",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'copied = dict(runner.keywords)\n'
            'seen = repr(copied)\n'
            'runner(["x"], text=True)',
            "the copy carries the risk to wherever it is bound, not just to one line",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def sneak(len):\n'
            '    len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a parameter named for a reader resolves to whatever the caller passes",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'async def sneak(len):\n'
            '    len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "an async parameter shadows a reader exactly as a plain one does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'shown = lambda sorted: sorted(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a lambda takes parameters too, and they shadow the same names",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'class K:\n'
            '    def m(self, len):\n'
            '        len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a method parameter is reached through a call the file never spells out",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def sneak(*, len):\n'
            '    len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a keyword-only parameter binds the name the same way a positional one does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'def sneak(len, /):\n'
            '    len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a positional-only parameter binds the name the same way as well",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            '@app.route\n'
            'def cb(sorted):\n'
            '    sorted(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a registered callback is called from outside, so its parameters are unknown",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'runner.keywords.keys.__self__["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a bound method carries the mapping it came from under __self__",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'reader = runner.keywords.keys\n'
            'reader.__self__["encoding"] = None\n'
            'runner(["x"], text=True)',
            "the bound method carries the mapping to wherever it is bound",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'reader = runner.keywords.keys\n'
            'runner(["x"], text=True)',
            "handing the bound method out is enough, whatever is done with it later",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=1\n'
            ')\n'
            'runner.keywords.items.__self__["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a mapping of literals still hands its own mapping back under __self__",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=1\n'
            ')\n'
            'runner.keywords.copy.__self__["encoding"] = None\n'
            'runner(["x"], text=True)',
            "every dict method carries __self__, not just the ones that read keys",
        ),
        (
            'import functools, subprocess, gc\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'gc.get_referents(iter(runner.keywords))[0]["encoding"] = None\n'
            'runner(["x"], text=True)',
            "an iterator holds the mapping it walks, and hands it back on request",
        ),
        (
            'import functools, subprocess, gc\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'gc.get_referents(reversed(runner.keywords))[0]["encoding"] = None\n'
            'runner(["x"], text=True)',
            "walking a mapping backwards holds it exactly as walking it forwards does",
        ),
        (
            'import functools, subprocess, ctypes\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", env=guard\n'
            ')\n'
            'ctypes.cast(id(runner.keywords), ctypes.py_object).value["encoding"] = None\n'
            'runner(["x"], text=True)',
            "an address is a reference to the mapping for anyone willing to follow it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = str(runner.keywords)\n'
            'runner(["x"], text=True)',
            "str renders the mapping the same way repr does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'print(runner.keywords)\n'
            'runner(["x"], text=True)',
            "print renders its argument before writing it",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'print(f"{runner.keywords}")\n'
            'runner(["x"], text=True)',
            "an interpolation renders the mapping, which renders every value",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = runner.keywords == {"encoding": "utf-8", "timeout": 1}\n'
            'runner(["x"], text=True)',
            "comparing against a same-shape mapping runs __eq__ on every value",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = 1 in runner.keywords.values()\n'
            'runner(["x"], text=True)',
            "values() hands out the values, and membership runs __eq__ on them",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = repr(runner.keywords.copy())\n'
            'runner(["x"], text=True)',
            "a copy shares the value objects, so rendering it renders them",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = repr(runner.keywords.get("timeout"))\n'
            'runner(["x"], text=True)',
            "get hands back a value whose __repr__ reaches the mapping",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8", timeout=guard\n'
            ')\n'
            'seen = repr(list(runner.keywords.items()))\n'
            'runner(["x"], text=True)',
            "items pairs every key with its value, so rendering reaches the values",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'getattr(runner, "keywords", {})["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a default argument does not stop getattr reaching the mapping",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'from subprocess import run as runner\n'
            'runner(["x"], text=True)',
            "an import rebinds the name to the bare entry point",
        ),
        (
            'import functools\n'
            'import subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'import subprocess.run as runner\n'
            'runner(["x"], text=True)',
            "a plain import rebinds the name the same way a from-import does",
        ),
        (
            'import functools, subprocess\n'
            'def len(mapping):\n'
            '    mapping["encoding"] = None\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'len(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a file that defines its own len is not handing the mapping to the builtin",
        ),
        (
            'import functools, subprocess\n'
            'def repr(mapping):\n'
            '    mapping["encoding"] = None\n'
            '    return ""\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'seen = repr(runner.keywords)\n'
            'runner(["x"], text=True)',
            "a shadowed renderer runs the file's code, literal values or not",
        ),
        (
            'import functools, subprocess\n'
            'from helpers import sorted\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'seen = sorted(runner.keywords)\n'
            'runner(["x"], text=True)',
            "an imported name shadows the builtin as thoroughly as a def does",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'class Holder:\n'
            '    fetch = getattr\n'
            'Holder.fetch(runner, "keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "a class attribute carries the fetcher as well as a bare name does",
        ),
        (
            'import functools, subprocess, builtins\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'builtins.getattr(runner, "keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "the builtins module spells the same fetch as a qualified name",
        ),
        (
            'import functools, subprocess\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'object.__getattribute__(runner, "keywords")["encoding"] = None\n'
            'runner(["x"], text=True)',
            "the unbound base descriptor fetches what the bound dunder fetches",
        ),
        (
            'import functools, subprocess, operator\n'
            'runner = functools.partial(\n'
            '    subprocess.run, capture_output=True, encoding="utf-8"\n'
            ')\n'
            'fetch = operator.methodcaller("__getattribute__", "keywords")\n'
            'fetch(runner)["encoding"] = None\n'
            'runner(["x"], text=True)',
            "methodcaller names the dunder as a string and calls it later",
        ),
        (
            'import subprocess\n[subprocess][0].run(["x"], capture_output=True, text=True)',
            "a module in a subscripted list still reaches its entry point",
        ),
        (
            'import subprocess\nk = "text"\nsubprocess.run(["x"], **{k: True})',
            "a dict splat with a non-constant key is treated as opaque and flagged",
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


def test_a_deep_module_alias_chain_stays_linear() -> None:
    """A chain of module aliases must cost one pass, not one pass per link.

    The sibling test above ends its chain at ``subprocess.run``. That is an
    attribute rather than a module name, so no link ever resolves as a module
    alias, the fixpoint makes a single pass and the shape is linear whatever
    the implementation does. Ending the chain at the module instead is what
    makes every link resolvable, and a sweep that repeats until nothing
    changes then learns exactly one link per pass.

    That difference is worth 14.0 seconds at this depth: repeated sweeps
    measured 0.235s at 1000 links, 0.887 at 2000, 3.425 at 4000 and 14.047 at
    8000, near enough 4x per doubling. Propagating along the dependency edges
    instead settles the whole chain in one pass over the edges.

    The loaded pre-push suite measured 3.8 seconds. Five seconds keeps margin
    for shared CPU while still rejecting the repeated full-chain sweep.
    """
    depth = 8000
    source = "\n".join(
        ["import subprocess"]
        + [f"m{index} = m{index + 1}" for index in range(depth)]
        + [f"m{depth} = subprocess", 'm0.run(["x"], capture_output=True, text=True)']
    )

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [depth + 3], "the module survives every alias on the way"
    assert elapsed < 5.0, f"alias resolution took {elapsed:.1f}s for {depth} links"


def test_unwinding_a_wide_container_stays_linear() -> None:
    """Reading the names out of one wide container must not cost the width.

    Every element goes into the queue at once, so a queue that pops its front
    by shifting the rest pays the width on every pop. At the sizes a real
    source reaches that shift is a cache-friendly move and the shape looks
    linear, which is why the wide-unpack test above passes either way. Past
    that it is plainly quadratic: 50000 elements took 0.160s, 100000 took
    0.664 and 200000 took 2.779.

    Only the unwinding is timed. Parsing a literal this wide costs about
    0.45 seconds on its own and would swamp the measurement. The budget
    leaves a wide margin: popping from both ends does this in 0.015 seconds
    and shifting does it in about 0.95.
    """
    width = 120000
    source = "WIDE = [" + ", ".join(f"n{index}" for index in range(width)) + "]"
    container = ast.parse(source).body[0]
    assert isinstance(container, ast.Assign)

    started = time.perf_counter()
    found = _module_sources(container.value)
    elapsed = time.perf_counter() - started

    assert len(found) == width, "every element of the container answers"
    assert elapsed < 0.3, f"unwinding took {elapsed:.2f}s for {width} elements"


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
    """A module chained through containers is found, and the chain stays cheap.

    Each link wraps the next in a container, so settling the chain needs both
    the fixpoint that resolves names and the unwinding that reads through a
    subscript. Reading the sources of a link once per pass rather than once
    per node turns that into a walk per pass per link: 20000 plain links took
    83.2 seconds that way against a 10 second budget.

    The spawn at the end is what makes this a correctness test and not only a
    timing one. A chain that settles fast but loses the module answers
    nothing.
    """
    depth = 2000
    lines = ["import subprocess"]
    lines += [f"m{index} = [m{index + 1}][0]" for index in range(depth)]
    lines.append(f"m{depth} = subprocess")
    lines.append('m0.run(["x"], capture_output=True, text=True)')
    source = "\n".join(lines)

    started = time.perf_counter()
    flagged = unpinned_lines(source)
    elapsed = time.perf_counter() - started

    assert flagged == [depth + 3], "the module survives every container on the way"
    assert elapsed < 3.0, f"chain resolution took {elapsed:.1f}s for {depth} links"


def test_a_value_reading_many_names_is_walked_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value node that reads N names is walked once, not once per wake-up.

    The wide list waits on every name it reads, so resolving those names queues
    the same group thousands of times. Timing that behavior is not a stable
    proxy for the invariant: under the pre-push hook's concurrent jobs, the
    4000-name working set contends differently from the 1000-name baseline and
    has twice exceeded the ratio ceiling while the implementation was correct.

    Count the actual expensive operation instead. ``_settle`` precomputes a
    group's sources once, before any dependency can wake it. Re-queueing the
    old implementation moved that walk into the queue and this count rises.
    Refs #4048.
    """
    width = 4000
    wide_value = ast.parse(
        "[" + ", ".join(f"n{index}" for index in range(width)) + "]",
        mode="eval",
    ).body
    bindings = [("WIDE", wide_value)] + [
        (f"n{index}", ast.Name(id="subprocess", ctx=ast.Load()))
        for index in range(width)
    ]

    original = _module_sources
    wide_walks = 0

    def counted_module_sources(value: ast.expr) -> list[str]:
        nonlocal wide_walks
        if value is wide_value:
            wide_walks += 1
        return original(value)

    monkeypatch.setitem(_settle.__globals__, "_module_sources", counted_module_sources)
    settled = _settle(bindings, {"subprocess": "subprocess"})

    assert settled["WIDE"] == "subprocess", "the wide group must actually resolve"
    assert wide_walks == 1, f"the wide value was walked {wide_walks} times"


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
    # The loaded pre-push suite measured 3.7 seconds for this fixed-size input.
    assert elapsed < 5.0, f"resolution took {elapsed:.1f}s at depth {depth}"


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
