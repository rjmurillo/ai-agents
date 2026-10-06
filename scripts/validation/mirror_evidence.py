"""Structural evidence for mirror claims (issue #5399).

`.claude/rules/canonical-source-mirror.md` asks for evidence that B conforms
to canonical A. Evidence ranks: shared implementation, executable conformance
test, generated projection, symbolic path reference, copied prose last.
`check_canonical_citations.py` uses these helpers to accept the first three
without a path (a shared import counts only when its module resolves on
disk), and to report a copied contract that no structure backs.

A conformance test counts only when a named test token resolves to a
`def test_...` under the repository's `tests/` tree. A token that names no
defined test is not evidence. Limit: the resolver proves the test exists, not
that it reads the canonical source or fails when the source changes; a reviewer
still opens it, per the rule's reviewer checklist.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

# A test identifier that names conformance, parity, contract, or equivalence.
_CONFORMANCE_TEST = re.compile(r"\btest_\w*(?:conform|parity|contract|equival)\w*", re.IGNORECASE)

# A test function definition; the name is what a docstring token must resolve to.
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)", re.MULTILINE)

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
        if not _resolves(node.module, node.level, bases, file_dir):
            return []
        return [alias.asname or alias.name for alias in node.names]
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
    if level:
        anchor = file_dir
        for _ in range(level - 1):
            anchor = anchor.parent
        return _exists_under(anchor, parts)
    return bool(parts) and any(_exists_under(base, parts) for base in bases)


def _exists_under(base: Path, parts: list[str]) -> bool:
    if not all(p.isidentifier() for p in parts):
        return False
    target = base.joinpath(*parts)
    return target.is_dir() or target.with_suffix(".py").is_file()


@lru_cache(maxsize=8)
def defined_tests(repo_root: Path) -> frozenset[str]:
    """Return every `test_*` function name defined under `repo_root/tests`."""
    names: set[str] = set()
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return frozenset()
    for path in tests_dir.rglob("*.py"):
        try:
            names.update(_TEST_DEF.findall(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return frozenset(names)


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
