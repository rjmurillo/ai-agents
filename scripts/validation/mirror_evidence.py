"""Structural evidence for mirror claims (issue #5399).

`.claude/rules/canonical-source-mirror.md` asks for evidence that B conforms
to canonical A. Evidence ranks: shared implementation, executable conformance
test, generated projection, symbolic path reference, copied prose last.
`check_canonical_citations.py` uses these helpers to accept the first three
without a path, and to report a copied contract that no structure backs.
"""

from __future__ import annotations

import ast
import re
import sys

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


def imported_project_names(source: str) -> frozenset[str]:
    """Return names imported from non-stdlib modules, or an empty set if unparseable."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset()
    names: set[str] = set()
    for node in ast.walk(tree):
        names.update(_node_names(node))
    return frozenset(n for n in names if len(n) >= _MIN_NAME_LENGTH)


def _node_names(node: ast.AST) -> list[str]:
    """Return the project names one import statement binds."""
    if isinstance(node, ast.ImportFrom) and _is_project_root(node.module, node.level):
        return [alias.asname or alias.name for alias in node.names]
    if isinstance(node, ast.Import):
        return [
            alias.asname or alias.name for alias in node.names if _is_project_root(alias.name, 0)
        ]
    return []


def _is_project_root(module: str | None, level: int) -> bool:
    if level:
        return True
    root = (module or "").split(".")[0]
    return root not in sys.stdlib_module_names and root != "__future__"


def structural_evidence(text: str, imported: frozenset[str]) -> str | None:
    """Name the structural evidence the text carries, or None."""
    if _CONFORMANCE_TEST.search(text):
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
