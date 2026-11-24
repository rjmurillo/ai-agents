#!/usr/bin/env python3
"""Merge-key cases for the strict duplicate-key check in ``frontmatter_block.py``.

A real ``<<:`` merge and a quoted ``"<<"`` string key are different keys.
PyYAML's ``safe_load`` keeps both, so the strict loader must too. A second
real merge, or a second quoted ``"<<"``, at one level is still a duplicate.
Split from ``test_frontmatter_block.py`` to keep that file under the
500-line taste ceiling.
"""

from __future__ import annotations

import functools

import pytest
import yaml

import scripts.hook_utilities.frontmatter_block as frontmatter_block
from scripts.hook_utilities.frontmatter_block import FrontmatterStatus

parse = functools.partial(frontmatter_block.parse_frontmatter, yaml=yaml)


@pytest.mark.parametrize(
    "child",
    [
        '  <<: *b\n  "<<": q\n',
        '  "<<": q\n  <<: *b\n',
        "  <<: *b\n  '<<': q\n",
        "  '<<': q\n  <<: *b\n",
    ],
    ids=["merge-then-double", "double-then-merge", "merge-then-single", "single-then-merge"],
)
def test_a_quoted_merge_spelling_beside_a_real_merge_key_loads(child: str) -> None:
    """A quoted `"<<"` is a plain string key, not a merge; PyYAML keeps both."""
    result = parse(f"---\nbase: &b {{x: 1}}\nchild:\n{child}---\nBody.\n")

    assert result.status is FrontmatterStatus.VALID, result.error
    assert result.metadata == {"base": {"x": 1}, "child": {"x": 1, "<<": "q"}}


@pytest.mark.parametrize(
    "block",
    [
        "<<: {a: 1}\n<<: {b: 2}\n",
        '"<<": q\n"<<": r\n',
        "\"<<\": q\n'<<': r\n",
    ],
    ids=["two-real-merges", "two-quoted-keys", "mixed-quote-styles"],
)
def test_a_repeated_merge_or_repeated_quoted_key_is_still_rejected(block: str) -> None:
    result = parse(f"---\n{block}---\nBody.\n")

    assert result.status is FrontmatterStatus.MALFORMED
    assert result.error is not None
    assert "duplicate key '<<'" in result.error
