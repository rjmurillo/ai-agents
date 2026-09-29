"""Guards for the stdlib-only frontmatter splitter (issue #5592)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = REPO_ROOT / "scripts" / "validation" / "frontmatter_split.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validation.frontmatter_split import split_leading_frontmatter


def test_splits_frontmatter_and_body():
    assert split_leading_frontmatter("---\nname: foo\n---\n# body\n") == ("name: foo", "# body\n")


def test_multiline_frontmatter_keeps_inner_newlines():
    text = "---\na: 1\nb: 2\n---\nbody"
    assert split_leading_frontmatter(text) == ("a: 1\nb: 2", "body")


def test_empty_body_after_fence():
    assert split_leading_frontmatter("---\nname: foo\n---\n") == ("name: foo", "")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# just a heading\n",
        "---\nname: foo\n# never closed\n",
        "--- \nname: foo\n---\n",
        "\n---\nname: foo\n---\n",
        "---\nname: foo\n---",
    ],
)
def test_returns_whole_text_when_no_block(text):
    assert split_leading_frontmatter(text) == ("", text)


def test_empty_frontmatter_block_is_not_recognized():
    """``---\\n---\\n`` has no ``\\n---\\n`` after the opener, so it is unterminated."""
    text = "---\n---\nbody\n"
    assert split_leading_frontmatter(text) == ("", text)


def test_first_closing_fence_wins():
    text = "---\na: 1\n---\nbody\n---\nmore\n"
    assert split_leading_frontmatter(text) == ("a: 1", "body\n---\nmore\n")


def test_module_imports_only_the_standard_library():
    """The interpreter-portability ratchet fails a bare-python3 caller otherwise."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported <= {"__future__"}
