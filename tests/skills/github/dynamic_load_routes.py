"""Detector for the dynamic-load routes the completion gate does not recognise.

Issue #6032. ``run_completion_gate._dynamic_loads`` is a denylist of call
names, so a trusted verifier that runs a PR-edited file through a route the
denylist omits is dispatched unverified and reads as ``command_trust:
trusted``. This module names each omitted route and finds it by walking the
syntax tree, so a ratchet test can fail on the first verifier that adds one.

The detector is deliberately broader than the gate's scanner on the routes the
gate omits: a recognised load name reached by alias, import-as or an uncalled
reference, and the unrecognised names wherever they appear. A hit is a
question for a maintainer, not proof of a load.

Not covered, named so nobody reads this as complete: ``os.system`` and the
``os.spawn*`` family, ``shell=True`` strings, a Python launcher held in a
variable (``PY = sys.executable; [PY, "x.py"]``), ``code`` and ``codeop``
interpreters, ``types.FunctionType(compile(...))``, and a module alias such as
``import sys as s`` for any route other than ``builtins`` and ``sys.modules``.

Each route lists the shapes it matches in its own function below.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator
from typing import NamedTuple


class RouteHit(NamedTuple):
    """One site that reaches a dynamic-load route the gate does not model."""

    line: int
    route: str
    detail: str


# Every route key, so a test can prove the fixture set covers each one.
ROUTES = (
    "alias",
    "getattr",
    "builtins",
    "loader-api",
    "serialization-or-native",
    "subprocess-python",
    "sys-modules",
)

# Calls the gate's own scanner recognises when called by name. Reaching one by
# any other shape (alias, uncalled reference, import-as) is the "alias" route.
_RECOGNISED_LOADS = frozenset(
    {
        "__import__",
        "import_module",
        "run_module",
        "run_path",
        "spec_from_file_location",
        "SourceFileLoader",
        "exec",
        "eval",
    }
)

# Loader names the gate does not recognise at all.
_UNRECOGNISED_LOADER_NAMES = frozenset(
    {"ExtensionFileLoader", "SourcelessFileLoader", "spec_from_loader", "zipimporter"}
)
_UNRECOGNISED_LOADER_MODULES = frozenset({"zipimport", "pkgutil"})
_SERIALIZATION_OR_NATIVE_MODULES = frozenset({"pickle", "_pickle", "marshal", "ctypes"})

# Names whose attributes `getattr` could use to reach a recognised load.
_LOAD_RECEIVERS = frozenset(
    {"importlib", "builtins", "__builtins__", "runpy", "pkgutil", "zipimport", "sys"}
)
_BUILTINS_RECEIVERS = frozenset({"builtins", "__builtins__"})
_BUILTIN_LOADS = frozenset({"exec", "eval", "compile", "__import__"})
_PYTHON_EXE = re.compile(r"^(?:.*[/\\])?python(?:\d+(?:\.\d+)*)?t?(?:\.exe)?$", re.IGNORECASE)
_SYS_MODULES_MUTATORS = frozenset({"update", "setdefault", "__setitem__"})


def _names_bound_to(tree: ast.AST, module: str) -> frozenset[str]:
    """``module`` plus every ``import module as alias`` name in ``tree``."""
    names = {module}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(
                alias.asname for alias in node.names if alias.name == module and alias.asname
            )
    return frozenset(names)


def _is_sys_modules(node: ast.AST, sys_names: frozenset[str]) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id in sys_names
    )


def _is_python_interpreter(node: ast.AST) -> bool:
    """True for ``sys.executable`` or a literal ``python`` / ``python3`` name."""
    if isinstance(node, ast.Attribute):
        return (
            node.attr == "executable"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        )
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _PYTHON_EXE.match(node.value) is not None
    )


def _reference_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _called_function_ids(tree: ast.AST) -> set[int]:
    """Node ids sitting in call-target position, which the gate already sees."""
    return {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def _is_load_reference(node: ast.AST, called: set[int]) -> bool:
    """A Name or Attribute read that is not the target of a call.

    A store or delete is a rebinding of the name, not a reference to the load,
    so ``run_path = repo / "x"`` is not an alias.
    """
    if id(node) in called:
        return False
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Load)
    return isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)


def _alias_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """A recognised load reached by import-as or an uncalled reference."""
    called = _called_function_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _RECOGNISED_LOADS and alias.asname:
                    yield RouteHit(node.lineno, "alias", f"{alias.name} as {alias.asname}")
        elif isinstance(node, ast.Name | ast.Attribute) and _is_load_reference(node, called):
            name = _reference_name(node)
            if name in _RECOGNISED_LOADS:
                yield RouteHit(node.lineno, "alias", f"uncalled reference to {name}")


def _getattr_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """``getattr(importlib, name)`` or any ``getattr`` naming a load literally."""
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
        ):
            continue
        target, attribute = node.args[0], node.args[1]
        if isinstance(attribute, ast.Constant):
            if attribute.value in _RECOGNISED_LOADS | _UNRECOGNISED_LOADER_NAMES:
                yield RouteHit(node.lineno, "getattr", f"getattr of {attribute.value}")
        elif isinstance(target, ast.Name) and target.id in _LOAD_RECEIVERS:
            yield RouteHit(node.lineno, "getattr", f"computed getattr on {target.id}")


def _builtins_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """``builtins.exec``, ``builtins.eval`` and ``__builtins__["exec"]``."""
    receivers = _BUILTINS_RECEIVERS | _names_bound_to(tree, "builtins")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in receivers
            and node.attr in _BUILTIN_LOADS
        ):
            yield RouteHit(node.lineno, "builtins", f"{node.value.id}.{node.attr}")
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in receivers
        ):
            yield RouteHit(node.lineno, "builtins", f"{node.value.id}[...]")


def _imported_top_level_modules(node: ast.AST) -> list[tuple[int, str]]:
    """``(line, top-level module)`` for each module an import statement names."""
    if isinstance(node, ast.Import):
        return [(node.lineno, alias.name.split(".")[0]) for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [(node.lineno, node.module.split(".")[0])]
    return []


def _literal_module_loads(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """``(line, module)`` for ``__import__("pickle")`` and ``import_module("ctypes")``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _reference_name(node.func) in {
            "__import__",
            "import_module",
        }:
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                yield node.lineno, first.value.split(".")[0]


def _loader_api_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """Loader classes and importers the gate has no entry for."""
    for node in ast.walk(tree):
        for line, module in _imported_top_level_modules(node):
            if module in _UNRECOGNISED_LOADER_MODULES:
                yield RouteHit(line, "loader-api", f"import {module}")
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _UNRECOGNISED_LOADER_NAMES:
                    yield RouteHit(node.lineno, "loader-api", f"import {alias.name}")
        elif isinstance(node, ast.Name | ast.Attribute):
            name = _reference_name(node)
            if name in _UNRECOGNISED_LOADER_NAMES:
                yield RouteHit(node.lineno, "loader-api", f"reference to {name}")


def _serialization_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """``pickle``, ``marshal`` and ``ctypes`` run code the closure never parses."""
    named = [
        (line, module, "import")
        for node in ast.walk(tree)
        for line, module in _imported_top_level_modules(node)
    ] + [(line, module, "load of") for line, module in _literal_module_loads(tree)]
    for line, module, how in named:
        if module in _SERIALIZATION_OR_NATIVE_MODULES:
            yield RouteHit(line, "serialization-or-native", f"{how} {module}")


def _launches_python(node: ast.List | ast.Tuple) -> bool:
    return bool(node.elts) and _is_python_interpreter(node.elts[0])


def _subprocess_python_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """An argv literal that starts a Python interpreter.

    This is the shape ``[sys.executable, "-I", script]`` and
    ``[sys.executable, "-c", code]`` take. The gate's import closure never
    follows an argv, so the launched file is outside byte verification unless
    something else names it.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.List | ast.Tuple) and _launches_python(node):
            flags = [
                elt.value
                for elt in node.elts[1:]
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
            detail = "python -c" if "-c" in flags else "python launching a script or module"
            yield RouteHit(node.lineno, "subprocess-python", detail)


def _sys_modules_hits(tree: ast.AST) -> Iterator[RouteHit]:
    """Writes to ``sys.modules``, which make a later import resolve to injected code."""
    sys_names = _names_bound_to(tree, "sys")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and _is_sys_modules(node.value, sys_names)
            and isinstance(node.ctx, ast.Store | ast.Del)
        ):
            yield RouteHit(node.lineno, "sys-modules", "sys.modules[...] write")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SYS_MODULES_MUTATORS
            and _is_sys_modules(node.func.value, sys_names)
        ):
            yield RouteHit(node.lineno, "sys-modules", f"sys.modules.{node.func.attr}")


_DETECTORS: tuple[Callable[[ast.AST], Iterator[RouteHit]], ...] = (
    _alias_hits,
    _getattr_hits,
    _builtins_hits,
    _loader_api_hits,
    _serialization_hits,
    _subprocess_python_hits,
    _sys_modules_hits,
)


def unrecognised_routes(source: bytes | str) -> list[RouteHit]:
    """Every site in ``source`` that reaches a route the gate does not model.

    Raises ``SyntaxError`` on a file that does not parse. The ratchet scans
    shipped verifiers, so a parse failure there is a defect to surface, not a
    clean result.
    """
    tree = ast.parse(source)
    hits = {hit for detector in _DETECTORS for hit in detector(tree)}
    return sorted(hits)
