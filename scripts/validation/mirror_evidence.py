"""Structural evidence for mirror claims (issue #5399).

`.claude/rules/canonical-source-mirror.md` asks for evidence that B conforms
to canonical A. Evidence ranks: shared implementation, executable conformance
test, generated projection, symbolic path reference, copied prose last.
`check_canonical_citations.py` uses these helpers to accept the first three
without a path (a shared import counts only when its module resolves on
disk), and to report a copied contract that no structure backs.

A conformance test counts only when a named test token resolves to a function
definition (parsed, not text-matched) under the repository's `tests/` tree. A
token that names no defined test is not evidence. A `from module import name`
counts only when `name` is a submodule or a top-level binding of that module.

Limits: the resolver proves a test or symbol exists, not that the test reads the
canonical source or fails when it changes. A shared import counts when its bound
name appears in the claim; the claim is free text, so the check cannot tell
which imported name is the claimed canonical source. A reviewer still opens the
cited source, per the rule's reviewer checklist.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

# A test identifier that names conformance, parity, contract, or equivalence.
_CONFORMANCE_TEST = re.compile(r"\btest_\w*(?:conform|parity|contract|equival)\w*", re.IGNORECASE)

# The file says it is generated from a source, so it is a projection.
_GENERATED = re.compile(r"\bgenerated\s+(?:from|by|via)\b", re.IGNORECASE)

# Prose that marks a hand-copied contract.
_COPY_MARKER = re.compile(
    r"\b(?:verbatim|character-for-character|copied\s+(?:from|exactly))\b", re.IGNORECASE
)

_MIN_NAME_LENGTH = 4

REMEDIATION = (
    "Eliminate the copy: import the canonical source, generate this file "
    "from it, or add a conformance test that fails when the source changes. "
    "Keep copied prose only when none of these is possible."
)


def owned_roots(repo_root: Path, file_dir: Path) -> frozenset[str]:
    """Return top-level import names this repository owns.

    Covers repo-root directories and modules, packages under `.claude/lib`, and
    sibling modules of the scanned file (skill scripts import each other by bare
    name). A third-party package never appears here, so it is not evidence.
    """
    names: set[str] = set()
    for base in (repo_root, repo_root / ".claude" / "lib", file_dir):
        if base.is_dir():
            names.update(_module_names(base))
    return frozenset(names)


def _module_names(base: Path) -> set[str]:
    found: set[str] = set()
    for entry in base.iterdir():
        if entry.is_dir() and entry.name.isidentifier():
            found.add(entry.name)
        elif entry.suffix == ".py" and entry.stem.isidentifier():
            found.add(entry.stem)
    return found


def imported_project_names(source: str, repo_root: Path, file_dir: Path) -> frozenset[str]:
    """Return names imported from modules that exist in the scanned repository.

    An import counts only when its full module path resolves to a package
    directory or a `.py` file under the repository root, `.claude/lib`, or the
    scanned file's directory (absolute imports), or under the file's own
    directory tree (relative imports). Returns empty if the source is
    unparseable.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset()
    bases = _import_bases(repo_root, file_dir)
    names: set[str] = set()
    for node in ast.walk(tree):
        names.update(_node_names(node, bases, file_dir))
    return frozenset(n for n in names if len(n) >= _MIN_NAME_LENGTH)


def _import_bases(repo_root: Path, file_dir: Path) -> tuple[Path, ...]:
    return (repo_root, repo_root / ".claude" / "lib", file_dir)


def _node_names(node: ast.AST, bases: tuple[Path, ...], file_dir: Path) -> list[str]:
    """Return the resolvable names one import statement binds."""
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            # `from . import foo` binds submodules of the anchor: each must exist.
            return [
                alias.asname or alias.name
                for alias in node.names
                if _resolves(alias.name, node.level, bases, file_dir)
            ]
        target = _locate(node.module.split("."), node.level, bases, file_dir)
        if target is None:
            return []
        return [
            alias.asname or alias.name for alias in node.names if _member_exists(target, alias.name)
        ]
    if isinstance(node, ast.Import):
        return [
            alias.asname or alias.name
            for alias in node.names
            if _resolves(alias.name, 0, bases, file_dir)
        ]
    return []


def _resolves(module: str | None, level: int, bases: tuple[Path, ...], file_dir: Path) -> bool:
    """Return True when the dotted module path names a package or file on disk."""
    parts = (module or "").split(".") if module else []
    return _locate(parts, level, bases, file_dir) is not None


def _locate(parts: list[str], level: int, bases: tuple[Path, ...], file_dir: Path) -> Path | None:
    """Return the package directory or `.py` file a dotted path names, or None."""
    if level:
        anchor = file_dir
        for _ in range(level - 1):
            anchor = anchor.parent
        return _path_under(anchor, parts)
    if not parts:
        return None
    for base in bases:
        found = _path_under(base, parts)
        if found is not None:
            return found
    return None


def _path_under(base: Path, parts: list[str]) -> Path | None:
    if not all(p.isidentifier() for p in parts):
        return None
    target = base.joinpath(*parts)
    if target.is_dir():
        return target
    module_file = target.with_suffix(".py")
    return module_file if module_file.is_file() else None


def _member_exists(target: Path, name: str) -> bool:
    """Return True when `from <target> import name` would bind something real.

    `name` is a submodule of a package, or a top-level binding (definition,
    assignment, or import) in the module file or the package `__init__.py`.
    """
    if target.is_dir():
        if (target / name).is_dir() or (target / f"{name}.py").is_file():
            return True
        target = target / "__init__.py"
    if not target.is_file():
        return False
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return False
    return name in _top_level_names(tree.body)


def _top_level_names(body: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in stmt.names)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            names.update(_assigned_names(stmt))
        else:
            names.update(_nested_names(stmt))
    return names


def _assigned_names(stmt: ast.Assign | ast.AnnAssign | ast.AugAssign) -> set[str]:
    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
    return {
        node.id for target in targets for node in ast.walk(target) if isinstance(node, ast.Name)
    }


def _nested_names(stmt: ast.stmt) -> set[str]:
    """Collect bindings inside `if`, `try`, and `with` blocks at module level."""
    names: set[str] = set()
    for field in ("body", "orelse", "finalbody"):
        names.update(_top_level_names(getattr(stmt, field, [])))
    for handler in getattr(stmt, "handlers", []):
        names.update(_top_level_names(handler.body))
    return names


@lru_cache(maxsize=8)
def defined_tests(repo_root: Path) -> frozenset[str]:
    """Return every `test_*` function name defined under `repo_root/tests`."""
    names: set[str] = set()
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return frozenset()
    for path in tests_dir.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        names.update(_test_function_names(tree))
    return frozenset(names)


def _test_function_names(tree: ast.Module) -> set[str]:
    """Return the `test_*` names pytest would collect.

    Those are module-level functions and the methods of top-level `Test*`
    classes. A `def test_...` nested inside a helper is not collected, so it is
    not evidence.
    """
    names = set(_collected_test_names(tree.body))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            names.update(_collected_test_names(node.body))
    return names


def _collected_test_names(body: list[ast.stmt]) -> list[str]:
    return [
        node.name
        for node in body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _names_defined_test(text: str, tests: frozenset[str]) -> bool:
    return any(match.group(0) in tests for match in _CONFORMANCE_TEST.finditer(text))


def structural_evidence(text: str, imported: frozenset[str], tests: frozenset[str]) -> str | None:
    """Name the structural evidence the text carries, or None.

    `tests` is the set of test names defined under the repository's tests tree;
    a conformance token that is not in it is not evidence.
    """
    if _names_defined_test(text, tests):
        return "conformance-test"
    if _GENERATED.search(text):
        return "generated"
    for name in imported:
        if re.search(rf"\b{re.escape(name)}\b", text):
            return "shared-import"
    return None


def copied_contract_marker(text: str) -> str | None:
    """Return the marker word that says the text carries a hand copy, or None."""
    match = _COPY_MARKER.search(text)
    return match.group(0).lower() if match else None
