#!/usr/bin/env python3
"""Tests for the shared frontmatter contract (issue #5275).

Covers positive, negative and edge cases per `.agents/governance/TESTING-RIGOR.md`,
plus a negative control for each integration hazard the buy-vs-build evaluation
recorded at `.agents/analysis/frontmatter-parser-build-vs-buy.md`. The hazard
tests exist so a future "simplify this to frontmatter.loads()" change fails
loudly instead of silently losing a distinction a gate depends on.
"""

from __future__ import annotations

import pytest
import yaml
from frontmatter.default_handlers import YAMLHandler

from scripts.validation.frontmatter_contract import (
    FrontmatterError,
    FrontmatterStatus,
    parse_frontmatter,
)

BODY = "id: ADR-999\nstatus: accepted"


class TestAcceptedFences:
    """Fence shapes the contract accepts, with the mapping intact."""

    @pytest.mark.parametrize(
        ("label", "text"),
        [
            ("clean", f"---\n{BODY}\n---\nBody.\n"),
            # The exact case issue #5275 reported: one trailing space crashed
            # generate_adr_index.py while the lifecycle gate passed it.
            ("closing fence with one trailing space", f"---\n{BODY}\n--- \nBody.\n"),
            ("closing fence with a tab", f"---\n{BODY}\n---\t\nBody.\n"),
            ("four dashes", f"---\n{BODY}\n----\nBody.\n"),
            ("opening fence padded", f"--- \n{BODY}\n---\nBody.\n"),
            ("crlf line endings", f"---\r\n{BODY}\r\n---\r\nBody.\r\n"),
            ("closing fence at EOF, no newline", f"---\n{BODY}\n---"),
        ],
    )
    def test_accepts(self, label: str, text: str) -> None:
        result = parse_frontmatter(text)
        assert result.status is FrontmatterStatus.VALID, label
        assert result.metadata == {"id": "ADR-999", "status": "accepted"}, label
        assert result.ok and result.present, label


class TestRejectedFences:
    """Shapes that must not be read as a closed block."""

    def test_trailing_text_after_fence_is_not_a_close(self) -> None:
        """`--- nope` is the one slip that signals a real authoring mistake."""
        result = parse_frontmatter(f"---\n{BODY}\n--- nope\nBody.\n")
        assert result.status is FrontmatterStatus.UNTERMINATED
        assert result.metadata is None
        assert result.present is True

    def test_no_closing_fence(self) -> None:
        result = parse_frontmatter(f"---\n{BODY}\nBody.\n")
        assert result.status is FrontmatterStatus.UNTERMINATED
        assert result.error is not None
        assert "closing" in result.error

    def test_bom_before_opening_fence_is_absent(self) -> None:
        """A BOM means the file does not start with the fence. Matches every
        pre-existing parser, all of which returned "no frontmatter" here."""
        result = parse_frontmatter(f"﻿---\n{BODY}\n---\nBody.\n")
        assert result.status is FrontmatterStatus.ABSENT

    def test_no_frontmatter_at_all(self) -> None:
        result = parse_frontmatter("Just body text.\n")
        assert result.status is FrontmatterStatus.ABSENT
        assert result.metadata is None
        assert result.body == "Just body text.\n"
        assert result.present is False


class TestStatusDiscrimination:
    """H1: `frontmatter.loads()` collapses these four into `metadata == {}`.

    Each must stay distinguishable; generate_adr_index.py raises a named error
    for one of them and routes another to "Needs backfill".
    """

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Just body.\n", FrontmatterStatus.ABSENT),
            (f"---\n{BODY}\nBody.\n", FrontmatterStatus.UNTERMINATED),
            ("---\n---\nBody.\n", FrontmatterStatus.EMPTY),
            ("---\n- a\n- b\n---\nBody.\n", FrontmatterStatus.NOT_A_MAPPING),
            ("---\njust a string\n---\nBody.\n", FrontmatterStatus.NOT_A_MAPPING),
            ('---\nid: "ADR-1\n---\nBody.\n', FrontmatterStatus.MALFORMED),
            ("---\ndesc: foo: bar\n---\nBody.\n", FrontmatterStatus.MALFORMED),
            (f"---\n{BODY}\n---\nBody.\n", FrontmatterStatus.VALID),
        ],
    )
    def test_each_state_is_distinct(self, text: str, expected: FrontmatterStatus) -> None:
        assert parse_frontmatter(text).status is expected

    def test_all_four_would_collapse_under_the_naive_library_call(self) -> None:
        """Negative control proving the distinction is not free.

        If this ever fails, upstream started distinguishing these and the
        adapter's reason for existing should be re-examined.
        """
        import frontmatter

        collapsing = [
            "Just body.\n",
            f"---\n{BODY}\nBody.\n",
            "---\n---\nBody.\n",
            "---\n- a\n---\nBody.\n",
        ]
        assert all(frontmatter.loads(t).metadata == {} for t in collapsing)
        assert len({parse_frontmatter(t).status for t in collapsing}) == 4

    def test_empty_block_parses_to_an_empty_mapping(self) -> None:
        result = parse_frontmatter("---\n---\nBody.\n")
        assert result.metadata == {}
        assert result.ok is True


class TestDuplicateKeys:
    """Repeated keys are a defect for the ADR gates, not last-one-wins."""

    def test_duplicate_key_rejected_by_default(self) -> None:
        result = parse_frontmatter("---\nid: A\nid: B\n---\nBody.\n")
        assert result.status is FrontmatterStatus.MALFORMED
        assert result.error is not None
        assert "duplicate key" in result.error

    def test_duplicate_key_nested_in_a_value_is_rejected(self) -> None:
        text = "---\nmeta:\n  a: 1\n  a: 2\n---\nBody.\n"
        assert parse_frontmatter(text).status is FrontmatterStatus.MALFORMED

    def test_duplicate_key_allowed_when_opted_in(self) -> None:
        result = parse_frontmatter("---\nid: A\nid: B\n---\nBody.\n", allow_duplicate_keys=True)
        assert result.status is FrontmatterStatus.VALID
        assert result.metadata == {"id": "B"}

    def test_unhashable_key_does_not_raise_typeerror(self) -> None:
        """`? [a, b]` builds a list key. A set-based duplicate check raises
        TypeError here, escaping the caller's YAMLError handling and turning a
        documented exit code into a traceback (generate_adr_index.py:202)."""
        result = parse_frontmatter("---\n? [a, b]\n: value\n---\nBody.\n")
        assert result.status in (FrontmatterStatus.VALID, FrontmatterStatus.MALFORMED)

    def test_genuinely_duplicated_unhashable_keys_are_caught(self) -> None:
        result = parse_frontmatter("---\n? [a, b]\n: 1\n? [a, b]\n: 2\n---\nBody.\n")
        assert result.status is FrontmatterStatus.MALFORMED


class TestLoaderPin:
    """H4 and H5: loader selection must be explicit and must not leak."""

    def test_loader_is_not_injected_into_metadata(self) -> None:
        """The obvious spelling, `frontmatter.loads(text, Loader=...)`, puts a
        `Loader` key in the parsed mapping because that parameter means default
        metadata. This is the negative control for that footgun."""
        import frontmatter

        naive = frontmatter.loads(f"---\n{BODY}\n---\nB\n", Loader=yaml.SafeLoader)
        assert "Loader" in naive.metadata

        result = parse_frontmatter(f"---\n{BODY}\n---\nB\n")
        assert result.metadata is not None
        assert "Loader" not in result.metadata

    def test_unsafe_python_tags_are_rejected(self) -> None:
        text = "---\na: 1\nb: !!python/object/apply:os.system []\n---\nX\n"
        assert parse_frontmatter(text).status is FrontmatterStatus.MALFORMED


class TestBodySplit:
    """The body is what prose consumers read."""

    def test_body_excludes_the_frontmatter(self) -> None:
        result = parse_frontmatter(f"---\n{BODY}\n---\n# Title\n\nPara.\n")
        assert result.body == "# Title\n\nPara.\n"
        assert "status: accepted" not in result.body

    def test_body_keeps_a_later_horizontal_rule(self) -> None:
        """Only the first two fences delimit the block; `---` in prose stays."""
        result = parse_frontmatter(f"---\n{BODY}\n---\nA.\n\n---\n\nB.\n")
        assert "---" in result.body
        assert result.body.endswith("B.\n")

    def test_raw_is_the_text_between_the_fences(self) -> None:
        result = parse_frontmatter(f"---\n{BODY}\n---\nBody.\n")
        assert "id: ADR-999" in result.raw
        assert "Body." not in result.raw

    def test_absent_frontmatter_returns_the_whole_text_as_body(self) -> None:
        text = "# Title\n\nNo frontmatter here.\n"
        assert parse_frontmatter(text).body == text


class TestStrictMode:
    """`strict` is for callers that already propagate an exception."""

    @pytest.mark.parametrize(
        "text",
        [
            f"---\n{BODY}\nBody.\n",
            '---\nid: "ADR-1\n---\nBody.\n',
            "---\n- a\n---\nBody.\n",
        ],
    )
    def test_strict_raises_on_a_broken_block(self, text: str) -> None:
        with pytest.raises(FrontmatterError):
            parse_frontmatter(text, strict=True)

    def test_strict_does_not_raise_on_absent_frontmatter(self) -> None:
        """A file with no block is a routine input, not a defect."""
        result = parse_frontmatter("Just body.\n", strict=True)
        assert result.status is FrontmatterStatus.ABSENT

    def test_strict_does_not_raise_on_a_valid_block(self) -> None:
        result = parse_frontmatter(f"---\n{BODY}\n---\nBody.\n", strict=True)
        assert result.status is FrontmatterStatus.VALID


class TestNoLocalFenceLogic:
    """The module must keep delegating rather than re-deriving.

    Hand-copying this library's pattern instead of calling it is what produced
    the twelfth fence contract at memory_index.py:888. This test is the guard
    against the adapter becoming the thirteenth.
    """

    def test_module_defines_no_fence_regex(self) -> None:
        """Checked with `ast`, not text search: the module docstring quotes the
        library's pattern verbatim, as canonical-source-mirror.md requires, so a
        substring check would match its own documentation."""
        import ast
        from pathlib import Path

        import scripts.validation.frontmatter_contract as mod

        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert "re" not in imported, "the adapter must not import re"

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
        ]
        assert calls == [], "the adapter must not compile its own pattern"

    def test_boundary_comes_from_the_library(self) -> None:
        assert YAMLHandler.FM_BOUNDARY.pattern == r"^-{3,}\s*$"
