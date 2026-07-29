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
_PARTIAL = "functools.partial"

# Entry points that hand back str no matter what keywords a call passes.
_DECODES_UNCONDITIONALLY = _ALWAYS_TEXT_ATTRS | frozenset({_DYNAMIC})


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


def _resolve_callable(
    node: ast.expr, modules: set[str], functions: dict[str, str]
) -> str | None:
    """Return the subprocess entry point *node* evaluates to, or ``None``."""
    while isinstance(node, ast.Subscript):
        # ``RUNNERS[0](...)`` reaches whatever the container holds. Resolving
        # the base rather than the index means a computed index cannot slip a
        # subprocess reference past this scan. A subscript chain is left
        # recursive, so the parser caps no depth and unwinding it must not
        # recurse.
        node = node.value
    if isinstance(node, ast.Name):
        resolved = functions.get(node.id)
        return None if resolved == _PARTIAL else resolved
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name):
            owner, attr = node.value.id, node.attr
            if owner in modules and attr in _SUBPROCESS_ATTRS:
                return attr
            if owner == "os" and attr == "popen":
                return _OS_POPEN
        # No partial filter here, unlike the bare-name branch above. The
        # sentinel is only ever written for an imported name, and every
        # attribute binding is resolved through that branch, which drops it.
        return functions.get(_ATTRIBUTE + node.attr)
    if isinstance(node, ast.Call):
        return _resolve_indirect(node, modules, functions)
    if isinstance(node, ast.NamedExpr):
        # ``(r := subprocess.run)(...)`` binds and calls in one expression.
        return _resolve_callable(node.value, modules, functions)
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


def _bindings(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    """Collect every ``name = value`` binding at any depth.

    Covers plain assignment, annotated assignment, the walrus, loop and
    comprehension targets, class bodies, and default arguments, every one of
    which binds a name without an assignment statement to find.
    Assignment targets are unpacked, so a name bound by destructuring is as
    visible as one bound on its own.
    """
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                found.extend(_unpack(target, node.value))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                found.append((node.target.id, node.value))
        elif isinstance(node, ast.NamedExpr):
            found.append((node.target.id, node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            # ``for runner in (subprocess.run,)`` binds a name with no
            # assignment statement anywhere in sight.
            found.extend(_unpack(node.target, node.iter))
        elif isinstance(node, ast.ClassDef):
            # A class body binds attributes without ever naming ``self``.
            for statement in node.body:
                if isinstance(statement, ast.Assign):
                    for target in statement.targets:
                        found.extend(
                            (_ATTRIBUTE + name, bound)
                            for name, bound in _unpack(target, statement.value)
                        )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(_defaults(node.args))
    return found


def _subprocess_names(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """Collect every name in *tree* that reaches a subprocess entry point.

    ``import subprocess as sp`` and ``from subprocess import run`` are both
    ordinary Python, and an owner-name check that only knows the literal word
    ``subprocess`` misses each of them. So is ``_run = subprocess.run``, which
    needs no import statement at all.
    """
    modules = {"subprocess"}
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_ATTRS:
                    functions[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module == "functools":
            for alias in node.names:
                if alias.name == "partial":
                    functions[alias.asname or alias.name] = _PARTIAL

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
    bindings = _bindings(tree)
    dependents: dict[str, list[int]] = {}
    for index, (_, value) in enumerate(bindings):
        for free in {
            node.id for node in ast.walk(value) if isinstance(node, ast.Name)
        }:
            dependents.setdefault(free, []).append(index)

    queue = list(range(len(bindings)))
    while queue:
        name, value = bindings[queue.pop()]
        # The first binding of a name wins. That is what bounds the queue, and
        # it is why a name rebound to an unrelated callable keeps reading as a
        # subprocess entry point.
        if name in functions:
            continue
        resolved = _resolve_callable(value, modules, functions)
        if resolved is None:
            continue
        functions[name] = resolved
        queue.extend(dependents.get(name, ()))
    return modules, functions


def _target(call: ast.Call, modules: set[str], functions: dict[str, str]) -> str | None:
    """Return the subprocess entry point *call* reaches, or ``None``."""
    direct = _resolve_callable(call.func, modules, functions)
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


def _captures_text(call: ast.Call, functions: dict[str, str]) -> bool:
    """Report whether *call* may decode captured output into ``str``.

    Deliberately conservative. Anything other than a literal ``False`` counts,
    because ``text=1`` and ``capture_output=flag`` both decode at runtime while
    reading as compliant to a check that only recognises ``True``.

    A ``functools.partial`` that selects text mode counts even with no capture
    keyword, because the capture can be supplied where the partial is called.

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
    modules, functions = _subprocess_names(tree)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _target(node, modules, functions)
        if target is None:
            continue
        if target == "os.popen":
            # os.popen has no encoding parameter at all, so the only compliant
            # move is to not use it.
            offenders.append(node.lineno)
            continue
        if target not in _DECODES_UNCONDITIONALLY and not _captures_text(node, functions):
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
