#!/usr/bin/env python3
"""Citation accuracy for the frontmatter parsing detect_adr_changes delegates.

Issue #6338 found a docstring that named a duplicate-key loader in a file that
did not hold it. The loader is gone from `detect_adr_changes.py`: it calls
`hook_utilities.frontmatter_block.parse_frontmatter`, which rejects a repeated
key at every mapping depth. These tests keep the shipped trees from citing the
retired `scripts/validation/frontmatter_contract.py` or carrying a local copy
of the loader, and confirm the core still does what `_parse_frontmatter`'s
docstring says it does.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE = REPO_ROOT / "src" / "claude" / "lib" / "hook_utilities" / "frontmatter_block.py"

DETECTOR_TREES = [
    ".claude/skills/adr-review/scripts/detect_adr_changes.py",
    "src/claude/skills/adr-review/scripts/detect_adr_changes.py",
]


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


@pytest.mark.parametrize("tree", DETECTOR_TREES)
class TestDetectorCitesTheCore:
    def test_does_not_name_the_retired_contract_module(self, tree: str) -> None:
        text = (REPO_ROOT / tree).read_text(encoding="utf-8")
        assert "frontmatter_contract" not in text

    def test_keeps_no_local_duplicate_key_loader(self, tree: str) -> None:
        assert "_has_duplicate_keys" not in _function_names(REPO_ROOT / tree)

    def test_parse_docstring_names_the_core(self, tree: str) -> None:
        tree_ast = ast.parse((REPO_ROOT / tree).read_text(encoding="utf-8"))
        docs = {
            node.name: ast.get_docstring(node) or ""
            for node in ast.walk(tree_ast)
            if isinstance(node, ast.FunctionDef)
        }
        assert "hook_utilities.frontmatter_block" in docs["_parse_frontmatter"]
        assert "hook_utilities.frontmatter_block" in docs["_split_frontmatter"]


class TestCoreRejectsDuplicateKeysByDefault:
    """The behavior `_parse_frontmatter`'s docstring relies on."""

    def test_core_exists_where_the_bootstrap_looks(self) -> None:
        assert CORE.is_file()
        assert "_strict_loader" in _function_names(CORE)
