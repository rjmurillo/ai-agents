"""Import closure for the shipped harness trees (issue #7221).

A harness tree under ``src/`` is installed on its own. A skill script or lib
module in it can import only the standard library, a declared third-party
package, or a module that ships in the same tree. ``lib_mirror.py`` once left
``paths.py`` out of three trees, and four skill scripts crashed on
``from paths import artifact_dir`` while every build gate stayed green.

:func:`check_import_closure` reads every ``skills/**/scripts/**/*.py`` and
``lib/**/*.py`` file in each tree and reports an import whose top-level module
resolves nowhere. ``check_surface_parity.run_checks`` calls it, so
``build_all.py --check`` and the standalone parity gate run it without a new
entry point.

A tree is a directory under ``src/`` that holds ``skills/`` or ``lib/``. The
Hermes packs (``src/hermes/<pack>``) are trees of their own.

An absolute import resolves when its top-level name is one of:

* in ``sys.stdlib_module_names``;
* a runtime dependency in ``pyproject.toml`` ``[project].dependencies``;
* a module or package (a directory, so namespace packages count) in the
  tree's ``lib/``;
* a module or package next to the importing file.

A relative import resolves when the named module exists beside the file (or
in the parent for deeper levels). ``from . import name`` is not checked.

Imports the author guards are skipped: the body and handlers of a ``try``
that catches ``ImportError`` or ``ModuleNotFoundError`` and lets the script
carry on (the handler holds the fallback import), and an ``if TYPE_CHECKING:``
body. A handler that raises or exits makes the import a hard requirement, so
that import is checked like any other (``run_retrospective.py`` and
``generate_experiment.py`` import ``paths`` this way).
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import tomllib

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from surface_manifest import Finding  # noqa: E402

FINDING_KIND = "UNRESOLVED-IMPORT"
SRC_REL = "src"

# Distribution names whose import name is not the normalized distribution name.
_IMPORT_NAME_ALIASES: dict[str, str] = {
    "pyyaml": "yaml",
    "markdown-it-py": "markdown_it",
    "python-frontmatter": "frontmatter",
}
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})


def declared_third_party(repo_root: Path) -> frozenset[str]:
    """Return import names of the runtime dependencies in ``pyproject.toml``."""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return frozenset()
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return frozenset()
    names: set[str] = set()
    for requirement in data.get("project", {}).get("dependencies", []):
        match = _REQUIREMENT_NAME.match(requirement)
        if match:
            dist = re.sub(r"[-_.]+", "-", match.group(1)).lower()
            names.add(_IMPORT_NAME_ALIASES.get(dist, dist.replace("-", "_")))
    return frozenset(names)


def harness_trees(repo_root: Path) -> list[Path]:
    """Return every shipped tree under ``src/``, sorted, as absolute paths."""
    src = repo_root / SRC_REL
    if not src.is_dir():
        return []
    trees: list[Path] = []
    for child in sorted(p for p in src.iterdir() if p.is_dir()):
        if _is_tree(child):
            trees.append(child)
            continue
        trees.extend(sorted(p for p in child.iterdir() if p.is_dir() and _is_tree(p)))
    return trees


def _is_tree(path: Path) -> bool:
    return (path / "skills").is_dir() or (path / "lib").is_dir()


def _shipped_files(tree: Path) -> Iterator[Path]:
    for pattern in ("skills/**/scripts/**/*.py", "lib/**/*.py"):
        for path in sorted(tree.glob(pattern)):
            if "__pycache__" not in path.parts and path.is_file():
                yield path


def _exists_as_module(directory: Path, name: str) -> bool:
    return (directory / f"{name}.py").is_file() or (directory / name).is_dir()


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    if caught is None:
        return False
    nodes = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any(
        (isinstance(n, ast.Name) and n.id in _IMPORT_ERRORS)
        or (isinstance(n, ast.Attribute) and n.attr in _IMPORT_ERRORS)
        for n in nodes
    )


def _exits_process(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name in {"exit", "quit"}


def _walk_running_code(node: ast.AST) -> Iterator[ast.AST]:
    """Walk ``node`` without entering a nested def, lambda, or class body."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if not isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            stack.extend(ast.iter_child_nodes(current))


def _handler_is_fatal(handler: ast.ExceptHandler) -> bool:
    """True when the handler raises or exits, so the import is a hard requirement.

    A ``raise`` inside a function the handler only defines does not run on the
    failed import, so it does not count.
    """
    return any(isinstance(n, ast.Raise) or _exits_process(n) for n in _walk_running_code(handler))


def _optional_import_guard(node: ast.Try) -> bool:
    """True for a ``try`` whose ImportError handler lets the script carry on."""
    handlers = [h for h in node.handlers if _catches_import_error(h)]
    return bool(handlers) and not any(_handler_is_fatal(h) for h in handlers)


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _unguarded_imports(node: ast.AST) -> Iterator[ast.Import | ast.ImportFrom]:
    """Yield imports under ``node`` that no ``try`` or ``TYPE_CHECKING`` guard covers."""
    for child in ast.iter_child_nodes(node):
        yield from _visit(child)


def _visit(node: ast.AST) -> Iterator[ast.Import | ast.ImportFrom]:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield node
    elif isinstance(node, ast.Try) and _optional_import_guard(node):
        for part in (*node.orelse, *node.finalbody):
            yield from _visit(part)
    elif isinstance(node, ast.If) and _is_type_checking(node.test):
        for part in node.orelse:
            yield from _visit(part)
    else:
        yield from _unguarded_imports(node)


def _relative_target(path: Path, node: ast.ImportFrom) -> str | None:
    """Return the top-level name a relative import needs beside ``path``, or None."""
    if not node.module:
        return None
    base = path.parent
    for _ in range(node.level - 1):
        base = base.parent
    top = node.module.split(".")[0]
    return None if _exists_as_module(base, top) else top


def _module_findings(
    repo_root: Path, tree: Path, path: Path, allowed: frozenset[str]
) -> list[Finding]:
    try:
        parsed = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    rel = path.relative_to(repo_root).as_posix()
    tree_rel = tree.relative_to(repo_root).as_posix()
    findings: list[Finding] = []
    for node in _unguarded_imports(parsed):
        missing: list[str] = []
        if isinstance(node, ast.Import):
            tops = [alias.name.split(".")[0] for alias in node.names]
            missing = [t for t in tops if not _resolves(t, tree, path, allowed)]
        elif node.level == 0 and node.module:
            top = node.module.split(".")[0]
            missing = [] if _resolves(top, tree, path, allowed) else [top]
        elif node.level > 0:
            target = _relative_target(path, node)
            missing = [target] if target else []
        for name in missing:
            detail = f"module '{name}' is not stdlib, declared, or shipped in {tree_rel}"
            findings.append(Finding(FINDING_KIND, tree_rel, f"{rel}:{node.lineno}", detail))
    return findings


def _resolves(name: str, tree: Path, path: Path, allowed: frozenset[str]) -> bool:
    return (
        name in sys.stdlib_module_names
        or name in allowed
        or _exists_as_module(tree / "lib", name)
        or _exists_as_module(path.parent, name)
    )


def check_import_closure(repo_root: Path) -> list[Finding]:
    """Return one finding per unresolved import in every shipped harness tree."""
    allowed = declared_third_party(repo_root)
    findings: list[Finding] = []
    for tree in harness_trees(repo_root):
        for path in _shipped_files(tree):
            findings.extend(_module_findings(repo_root, tree, path, allowed))
    return findings
