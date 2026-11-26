"""What pytest collects, read statically, for the ADR-127 evidence check.

``skill_rewrite_scenarios.py`` uses it to confirm that a replacement test a
scenario names is one pytest would run.
"""

from __future__ import annotations

import ast
import io
import tokenize
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

_CONSTRUCTORS = frozenset({"__init__", "__new__"})

# What pytest collects, from [tool.pytest.ini_options] in pyproject.toml:
# testpaths = ["tests"], python_files = ["test_*.py"],
# python_classes = ["Test*"], python_functions = ["test_*"].
# TestCollectionRules.test_constants_match_pyproject fails when they drift.
PYTEST_ROOT = "tests"
PYTEST_FILE_GLOB = "test_*.py"
PYTEST_CLASS_PREFIX = "Test"
PYTEST_FUNC_PREFIX = "test_"


def is_collected_file(path: str) -> bool:
    """True when pytest collects *path*: under ``tests/`` with a ``test_*.py`` name."""
    parts = PurePosixPath(path).parts
    return (
        len(parts) > 1
        and parts[0] == PYTEST_ROOT
        and ".." not in parts
        and fnmatchcase(parts[-1], PYTEST_FILE_GLOB)
    )


def defines_test(source: str, classes: list[str], func: str) -> bool:
    """True when pytest would collect *func*, defined directly in nested *classes* of *source*.

    *classes* and *func* are the segments of a pytest node id after the path.
    Every class must start with ``Test`` and *func* with ``test_``. False means
    pytest skips the test, or no static read can prove it does not. So False for:

    - a ``[param]`` id, an empty segment, a file that does not compile, or a
      coding cookie other than UTF-8
    - any ``__test__`` store but a truthy constant, for the module, a class in
      the chain, or the test (pytest skips on a falsy one)
    - a class in the chain that binds ``__init__`` or ``__new__`` (pytest 9
      skips it, ``_pytest/python.py``), has a base, or has a decorator that is
      not a ``pytest.mark``: either can switch collection off unseen
    - a test with a decorator that is not a ``pytest.mark`` (``@pytest.fixture``),
      or a mark called with one function, which pytest applies as a decorator
    - a generator test, which pytest 9 reports as an error
    - a name a later statement rebinds, such as ``test_x = None``, even inside a
      ``try`` or ``if`` body: pytest reads the final binding
    - a ``global`` or ``nonlocal`` of a name in the id, or an attribute store such
      as ``TestA.test_a = None`` or ``pytest.mark.x = ...``
    - a module that binds ``__getattr__``, ``pytest`` or ``mark`` other than by
      importing pytest, or any ``pytest_*`` name (a hook or ``pytest_plugins``)

    - module or class code, outside a def, that holds a ``raise`` or calls a
      ``skip``, ``importorskip``, ``exit`` or ``fail`` (a mark is not a call here)

    Other code that fails at import, such as a raising default, is not read,
    nor are ``setattr`` or ``globals()``. Whether
    the file itself is collected is ``is_collected_file``'s question, not this one's.
    """
    named_like_tests = func.startswith(PYTEST_FUNC_PREFIX) and "[" not in func
    if not named_like_tests or not all(c.startswith(PYTEST_CLASS_PREFIX) for c in classes):
        return False
    try:
        tree = ast.parse(source)
        compile(tree, "<test>", "exec")
    except (SyntaxError, ValueError):
        return False
    if not _declares_utf8(source) or _module_hooks(tree) or _may_stop_at_import(tree):
        return False
    if _rebound_elsewhere(tree, {*classes, func}) or _odd_pytestmark(tree):
        return False
    body = tree.body
    top = _final_binding(body, classes[0] if classes else func)
    before = body[: body.index(top)] if top else []
    roots = {r for node in before for r in _pytest_roots(node)}
    for name in classes:
        found = _final_binding(body, name)
        if not (
            isinstance(found, ast.ClassDef) and found.name == name and _plain_class(found, roots)
        ):
            return False
        body = found.body
    last = _final_binding(body, func)
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    if not (isinstance(last, funcs) and last.name == func):
        return False
    generator = any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(last))
    return not generator and _marks_only(last.decorator_list, roots)


def _declares_utf8(source: str) -> bool:
    """False for a coding cookie pytest would read as another encoding."""
    readline = io.BytesIO(source.encode("utf-8")).readline
    try:
        encoding, _ = tokenize.detect_encoding(readline)
    except SyntaxError:
        return False
    return encoding in {"utf-8", "utf-8-sig"}


def _module_hooks(tree: ast.Module) -> bool:
    """True when the module binds ``__getattr__``, a ``pytest_*`` name, or its own ``pytest``."""
    for node in tree.body:
        bound = _bound_names(node)
        if "__getattr__" in bound or any(n.startswith("pytest_") for n in bound):
            return True
        if bound & {"pytest", "mark"} - _pytest_roots(node):
            return True
    return False


_STOPS = frozenset({"skip", "importorskip", "exit", "fail"})


def _may_stop_at_import(tree: ast.Module) -> bool:
    """True when module or class code, outside a def or lambda, may raise or skip."""
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Raise) or (isinstance(node, ast.Call) and _stops(node)):
            return True
        stack.extend(ast.iter_child_nodes(node))
    return False


def _stops(call: ast.Call) -> bool:
    """True for a call such as ``pytest.skip(...)`` or ``importorskip(...)``, not a mark."""
    node, parts = call.func, []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    last = parts[0] if parts else getattr(node, "id", None)
    return last in _STOPS and "mark" not in parts


def _pytest_roots(node: ast.stmt) -> set[str]:
    """``pytest`` for ``import pytest``, ``mark`` for ``from pytest import mark``, unaliased."""
    if isinstance(node, ast.ImportFrom) and node.module == "pytest":
        return {"mark" for a in node.names if a.name == "mark" and a.asname in (None, "mark")}
    if isinstance(node, ast.Import):
        return {"pytest" for a in node.names if a.name == "pytest" and a.asname in (None, "pytest")}
    return set()


def _plain_class(node: ast.ClassDef, roots: set[str]) -> bool:
    """No base, no decorator but a mark, and no constructor binding."""
    if node.bases or node.keywords or not _marks_only(node.decorator_list, roots):
        return False
    return not any(_bound_names(n) & _CONSTRUCTORS for n in node.body)


def _marks_only(decorators: list[ast.expr], roots: set[str]) -> bool:
    """True when every decorator is ``pytest.mark.<x>`` or ``mark.<x>``, called or not.

    *roots* holds ``pytest`` or ``mark`` when an import above the test binds it.
    """
    for decorator in decorators:
        call = decorator if isinstance(decorator, ast.Call) else None
        # pytest applies a mark called with one function or class as a decorator.
        callables = (ast.Name, ast.Attribute, ast.Lambda)
        if call and len(call.args) == 1 and not call.keywords:
            if isinstance(call.args[0], callables):
                return False
        # A starred or double-starred argument may expand to that one callable.
        if call and any(isinstance(a, ast.Starred) for a in call.args):
            return False
        if call and any(k.arg is None for k in call.keywords):
            return False
        node = call.func if call else decorator
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.insert(0, node.attr)
            node = node.value
        chain = ([node.id] if isinstance(node, ast.Name) else []) + parts
        root = chain[0] if chain and chain[0] in roots else None
        full = ["pytest", *chain] if root == "mark" else chain
        if root is None or len(full) != 3 or full[1] != "mark":
            return False
    return True


def _odd_pytestmark(tree: ast.Module) -> bool:
    """True when a ``pytestmark`` binding may not be a mark list pytest can read.

    pytest raises at collection on a ``pytestmark`` that holds anything but
    marks. Only ``pytestmark = <marks>`` directly in the module body, or in a
    class body there, counts as safe; the marks must use an import above it.
    """
    safe: set[int] = set()
    roots: set[str] = set()
    for node in tree.body:
        nested = node.body if isinstance(node, ast.ClassDef) else []
        safe |= {id(n) for n in [node, *nested] if _marks_assign(n, roots)}
        roots |= _pytest_roots(node)
    return any(
        isinstance(n, ast.stmt) and id(n) not in safe and "pytestmark" in _bound_names(n)
        for n in ast.walk(tree)
    )


def _marks_assign(node: ast.stmt, roots: set[str]) -> bool:
    """True for ``pytestmark = <mark>`` or a list of marks; pytest rejects a tuple."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
        return False
    target, value = node.targets[0], node.value
    if not (isinstance(target, ast.Name) and target.id == "pytestmark"):
        return False
    marks = value.elts if isinstance(value, ast.List) else [value]
    return _marks_only(marks, roots)


def _rebound_elsewhere(tree: ast.Module, names: set[str]) -> bool:
    """True for a ``__test__`` store, a ``global``, or an attribute store that may hide the test.

    A ``__test__`` store counts unless it is a plain assignment of a truthy
    constant. An attribute ``__test__`` store counts when its root is a name in
    *names*. Any store to an attribute named like a name in *names* counts.
    """
    safe: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Constant):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            safe |= {id(node), *(id(t) for t in targets)} if node.value.value else set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)) and names & set(node.names):
            return True
        marks = isinstance(node, ast.Attribute) and node.attr == "pytestmark"
        if id(node) in safe and not marks:
            continue
        if isinstance(node, ast.stmt) and "__test__" in _bound_names(node):
            return True
        if isinstance(node, (ast.Attribute, ast.Subscript)) and _stores_over(node, names):
            return True
    return False


_SWITCHES = frozenset({"__test__", "pytestmark"})


def _stores_over(node: ast.Attribute | ast.Subscript, names: set[str]) -> bool:
    """True when *node* stores to an id name, a switch key, or anything under ``pytest``."""
    if not isinstance(node.ctx, (ast.Store, ast.Del)):
        return False
    if isinstance(node, ast.Subscript):
        key = node.slice
        return isinstance(key, ast.Constant) and key.value in {*_SWITCHES, *names}
    root = _root_name(node)
    switch = node.attr in _SWITCHES and root in names
    return node.attr in names or switch or root in {"pytest", "mark"}


def _root_name(node: ast.expr) -> str | None:
    """The name an attribute chain such as ``TestA.test_a.x`` starts from."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _final_binding(body: list[ast.stmt], name: str) -> ast.stmt | None:
    """The last statement directly in *body* that binds *name*, or None.

    A def, a class, an import, ``del``, an assignment with a value, a ``type``
    alias, a ``for``, ``with`` or ``except`` target, a ``case`` capture, or a
    walrus in a statement's own expressions (a comprehension included) binds.
    A star import may bind any name, so it counts. A wrapper such as
    ``test_x = mark(test_x)`` counts too and fails closed: use decorator syntax.
    A block body (``if``, ``try``, ``match`` and the rest) shares the scope, so
    a binding in it at any depth makes the whole statement the binding, which
    is not a def and fails closed: no static read knows which branch runs.
    """
    found = None
    for node in body:
        if _bound_names(node) & {name, "*"}:
            found = node
    return found


def _bound_names(node: ast.stmt) -> set[str]:
    """Names *node* binds or deletes in its own scope; ``*`` for a star import."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in node.names}
    targets = _statement_targets(node) + _walrus_targets(node)
    stores = (ast.Store, ast.Del)
    names = {
        n.id
        for t in targets
        for n in ast.walk(t)
        if isinstance(n, ast.Name) and isinstance(n.ctx, stores)
    }
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.add(node.name)
        return names
    return names | _block_names(node)


def _block_names(node: ast.stmt) -> set[str]:
    """Names bound in the block bodies of *node*, which run in its own scope."""
    blocks = [*getattr(node, "body", []), *getattr(node, "orelse", [])]
    blocks += getattr(node, "finalbody", [])
    names: set[str] = set()
    for handler in getattr(node, "handlers", []):
        blocks += handler.body
        names.update([handler.name] if handler.name else [])
    for case in getattr(node, "cases", []):
        blocks += case.body
        names.update(_capture_names(case.pattern))
    for child in blocks:
        names |= _bound_names(child)
    return names


def _capture_names(pattern: ast.pattern) -> set[str]:
    """Names a ``case`` pattern captures."""
    captures = (ast.MatchAs, ast.MatchStar)
    found = {n.name for n in ast.walk(pattern) if isinstance(n, captures) and n.name}
    return found | {n.rest for n in ast.walk(pattern) if isinstance(n, ast.MatchMapping) and n.rest}


def _statement_targets(node: ast.stmt) -> list[ast.expr]:
    """The target expressions an assignment-like statement binds or deletes."""
    if isinstance(node, (ast.Assign, ast.Delete)):
        return node.targets
    if isinstance(node, ast.AugAssign) or (
        isinstance(node, ast.AnnAssign) and node.value is not None
    ):
        return [node.target]
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return [node.target]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [i.optional_vars for i in node.items if i.optional_vars is not None]
    if isinstance(node, ast.TypeAlias):
        return [node.name]
    return []


def _walrus_targets(node: ast.stmt) -> list[ast.expr]:
    """Walrus targets in the expressions *node* runs itself, not in a block body.

    A walrus binds in the enclosing scope, even inside a comprehension, so a
    comprehension is walked. A lambda body opens its own scope, so only its
    defaults are walked. Annotations are evaluated lazily, so they are not.
    """
    heads = _statement_heads(node)
    found: list[ast.expr] = []
    while heads:
        current = heads.pop()
        if isinstance(current, ast.Lambda):
            heads.extend(_argument_defaults(current.args))
            continue
        if isinstance(current, ast.NamedExpr):
            found.append(current.target)
        heads.extend(ast.iter_child_nodes(current))
    return found


def _statement_heads(node: ast.stmt) -> list[ast.AST]:
    """The expressions *node* evaluates in the enclosing scope, outside any block body."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [*node.decorator_list, *_argument_defaults(node.args)]
    if isinstance(node, ast.ClassDef):
        return [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]
    if isinstance(node, (ast.Try, ast.TryStar)):
        return [h.type for h in node.handlers if h.type]
    if isinstance(node, (ast.If, ast.While)):
        return [node.test]
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return [node.iter]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [i.context_expr for i in node.items]
    if isinstance(node, ast.Match):
        return [node.subject, *(c.guard for c in node.cases if c.guard)]
    return [node]


def _argument_defaults(args: ast.arguments) -> list[ast.AST]:
    """Default values, which run where the def or lambda is evaluated."""
    return [*args.defaults, *(d for d in args.kw_defaults if d is not None)]
