"""What pytest collects, read statically, for the ADR-127 evidence check.

``skill_rewrite_scenarios.py`` uses it to confirm that a replacement test a
scenario names is one pytest would run.
"""

from __future__ import annotations

import ast
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

    - a ``[param]`` id, an empty segment, or a file that does not parse
    - any ``__test__`` store but a truthy constant, for the module, a class in
      the chain, or the test (pytest skips on a falsy one)
    - a class in the chain that binds ``__init__`` or ``__new__`` (pytest 9
      skips it, ``_pytest/python.py``), has a base, or has a decorator that is
      not a ``pytest.mark``: either can switch collection off unseen
    - a test with a decorator that is not a ``pytest.mark`` (``@pytest.fixture``)
    - a name a later statement rebinds, such as ``test_x = None``, even inside a
      ``try`` or ``if`` body: pytest reads the final binding
    - a ``global`` or ``nonlocal`` of a name in the id, or an attribute store such
      as ``TestA.test_a = None``

    ``setattr``, ``globals()`` and other dynamic rebinds are not read. Whether
    the file itself is collected is ``is_collected_file``'s question, not this one's.
    """
    named_like_tests = func.startswith(PYTEST_FUNC_PREFIX) and "[" not in func
    if not named_like_tests or not all(c.startswith(PYTEST_CLASS_PREFIX) for c in classes):
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    if _rebound_elsewhere(tree, {*classes, func}):
        return False
    body = tree.body
    for name in classes:
        found = _final_binding(body, name)
        if not (isinstance(found, ast.ClassDef) and found.name == name and _plain_class(found)):
            return False
        body = found.body
    last = _final_binding(body, func)
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    return isinstance(last, funcs) and last.name == func and _marks_only(last.decorator_list)


def _plain_class(node: ast.ClassDef) -> bool:
    """No base, no decorator but a mark, and no constructor binding."""
    if node.bases or node.keywords or not _marks_only(node.decorator_list):
        return False
    return not any(_bound_names(n) & _CONSTRUCTORS for n in node.body)


def _marks_only(decorators: list[ast.expr]) -> bool:
    """True when every decorator is ``pytest.mark.<x>`` or ``mark.<x>``, called or not."""
    for decorator in decorators:
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.insert(0, node.attr)
            node = node.value
        chain = ([node.id] if isinstance(node, ast.Name) else []) + parts
        start = 2 if chain[:2] == ["pytest", "mark"] else 1 if chain[:1] == ["mark"] else 0
        if not start or len(chain) <= start:
            return False
    return True


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
            safe |= {id(t) for t in targets} if node.value.value else set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)) and names & set(node.names):
            return True
        if id(node) in safe or not isinstance(getattr(node, "ctx", None), (ast.Store, ast.Del)):
            continue
        if isinstance(node, ast.Name) and node.id == "__test__":
            return True
        if isinstance(node, ast.Attribute) and (
            node.attr in names or (node.attr == "__test__" and _root_name(node) in names)
        ):
            return True
    return False


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
