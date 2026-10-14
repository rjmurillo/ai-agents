#!/usr/bin/env python3
"""Citation accuracy for the duplicate-key loader that detect_adr_changes mirrors.

Issue #6338: the `_has_duplicate_keys` docstring named a `_no_duplicate_keys`
function in `build/scripts/generate_adr_index.py` and quoted it by line range.
That script has no such function, so a reader who followed the citation landed
on an unrelated "Parsing" header. The canonical loader is `_no_duplicate_keys`
in `scripts/validation/frontmatter_contract.py`.

These tests hold the citation honest in every shipped tree. They resolve the
cited line at test time instead of pinning a literal number, so a later edit
that moves the function fails here until the citation moves with it.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "scripts" / "validation" / "frontmatter_contract.py"
STALE_TARGET = "generate_adr_index.py"
CITATION = re.compile(r"scripts/validation/frontmatter_contract\.py:(\d+)")

DETECTOR_TREES = [
    ".claude/skills/adr-review/scripts/detect_adr_changes.py",
    "src/claude/skills/adr-review/scripts/detect_adr_changes.py",
    "src/codex/skills/adr-review/scripts/detect_adr_changes.py",
    "src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py",
]


def _docstring(path: Path, name: str) -> str:
    """Return the docstring of the function `name` defined anywhere in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            doc = ast.get_docstring(node, clean=False)
            assert doc is not None, f"{name} in {path} has no docstring"
            return doc
    pytest.fail(f"{name} not found in {path}")


def _quoted_block(doc: str) -> str:
    """Return the dedented code block that follows the `::` marker."""
    after = doc.split("::\n", 1)[1]
    lines: list[str] = []
    for line in after.splitlines():
        if line and not line.startswith("        "):
            break
        lines.append(line)
    return textwrap.dedent("\n".join(lines)).strip()


@pytest.fixture(scope="module")
def canonical_lines() -> list[str]:
    return CANONICAL.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("tree", DETECTOR_TREES)
class TestDetectorDocstringCitation:
    """The mirror's docstring points at the file that really holds the loader."""

    def test_does_not_name_the_script_that_lacks_the_loader(self, tree: str) -> None:
        doc = _docstring(REPO_ROOT / tree, "_has_duplicate_keys")
        assert STALE_TARGET not in doc

    def test_cites_the_canonical_loader_by_line(
        self, tree: str, canonical_lines: list[str]
    ) -> None:
        doc = _docstring(REPO_ROOT / tree, "_has_duplicate_keys")
        match = CITATION.search(doc)
        assert match is not None, "docstring must cite frontmatter_contract.py:<line>"
        cited = canonical_lines[int(match.group(1)) - 1]
        assert cited.startswith("def _no_duplicate_keys(")

    def test_cites_a_single_line_not_a_range(self, tree: str) -> None:
        doc = _docstring(REPO_ROOT / tree, "_has_duplicate_keys")
        assert not re.search(r"frontmatter_contract\.py:\d+-\d+", doc)

    def test_quoted_body_appears_verbatim_in_the_canonical_loader(self, tree: str) -> None:
        doc = _docstring(REPO_ROOT / tree, "_has_duplicate_keys")
        quoted = _quoted_block(doc)
        canonical = textwrap.dedent("\n".join(_function_body(CANONICAL, "_no_duplicate_keys")))
        assert quoted in canonical

    def test_quoted_body_raises_the_constructor_error_the_canonical_loader_raises(
        self, tree: str
    ) -> None:
        doc = _docstring(REPO_ROOT / tree, "_has_duplicate_keys")
        quoted = _quoted_block(doc)
        assert "yaml.constructor.ConstructorError" in quoted
        assert "_DuplicateKeyError" not in quoted

    def test_divergence_note_names_the_local_exception(self, tree: str) -> None:
        doc = _docstring(REPO_ROOT / tree, "_has_duplicate_keys")
        note = doc.split("Stricter/looser/different than canonical:", 1)[1]
        assert "_Dup" in note.split("Keys are compared", 1)[0]


def _function_body(path: Path, name: str) -> list[str]:
    """Return the source lines of `name`'s body after its docstring."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            first = node.body[1] if len(node.body) > 1 else node.body[0]
            return lines[first.lineno - 1 : node.end_lineno]
    pytest.fail(f"{name} not found in {path}")


class TestCanonicalLoaderDocstring:
    """`frontmatter_contract._no_duplicate_keys` no longer mirrors a ghost."""

    def test_does_not_cite_a_line_in_generate_adr_index(self) -> None:
        doc = _docstring(CANONICAL, "_no_duplicate_keys")
        assert STALE_TARGET not in doc

    def test_keeps_the_unhashable_key_rationale(self) -> None:
        doc = _docstring(CANONICAL, "_no_duplicate_keys")
        assert "TypeError" in doc
        assert "==" in doc

    def test_does_not_promise_a_verbatim_mirror_of_another_file(self) -> None:
        doc = _docstring(CANONICAL, "_no_duplicate_keys")
        assert "Mirrors" not in doc
