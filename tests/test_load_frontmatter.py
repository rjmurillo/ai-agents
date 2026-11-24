"""Tests for ``load_frontmatter``, the dict-or-None view of the one frontmatter parser.

These moved from ``tests/validation_pre_pr/test_frontmatter.py`` when the
``yaml_utils._parse_yaml_frontmatter`` helper they covered was deleted. They pin
what its former callers still rely on.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from scripts.hook_utilities.frontmatter_block import load_frontmatter


def _parse_yaml_frontmatter(text: str) -> dict[str, Any] | None:
    """The ``dict | None`` view the DESIGN-REVIEW gate reads, from the one parser."""
    return load_frontmatter(text, yaml)


class TestParseYamlFrontmatter:
    """Tests for YAML frontmatter parser."""

    def test_parses_valid_frontmatter(self) -> None:
        text = '---\nstatus: "APPROVED"\npriority: "P1"\nblocking: false\n---\n# Title\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"
        assert result["blocking"] is False

    def test_returns_none_without_frontmatter(self) -> None:
        text = "# Title\nSome content\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_returns_none_for_unclosed_frontmatter(self) -> None:
        text = "---\nstatus: APPROVED\n# No closing delimiter\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_parses_boolean_true(self) -> None:
        text = "---\nblocking: true\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["blocking"] is True

    def test_parses_integer_values(self) -> None:
        text = "---\npr: 1205\nissue: 937\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["pr"] == 1205
        assert result["issue"] == 937

    def test_strips_quotes(self) -> None:
        text = "---\nstatus: \"BLOCKED\"\nreviewer: 'architect'\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "BLOCKED"
        assert result["reviewer"] == "architect"

    def test_skips_comments_and_blank_lines(self) -> None:
        text = "---\n# comment\n\nstatus: APPROVED\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert len(result) == 1

    def test_strips_inline_yaml_comments(self) -> None:
        text = (
            "---\n"
            "status: APPROVED              # APPROVED | NEEDS_CHANGES\n"
            "priority: P1  # severity\n"
            "---\n"
        )
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"

    def test_preserves_hash_inside_quotes(self) -> None:
        text = '---\nvalue: "has # in it"\n---\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["value"] == "has # in it"

    def test_returns_none_for_malformed_yaml(self) -> None:
        text = "---\ndescription: Agent examples: Context: user asks\n---\n"
        assert _parse_yaml_frontmatter(text) is None


class TestDelegatesToTheSharedContract:
    """Issue #5275 follow-up: the dict-or-None view reads the one shared parser.

    `scripts/hook_utilities/frontmatter_block.py` owns the fence and the load.
    These tests pin what the old `yaml_utils._parse_yaml_frontmatter` callers
    (`check_adr_lifecycle.py`, `validate_design_review.py`,
    `validate_copilot_agent_frontmatter.py`) still rely on.
    """

    def test_trailing_text_after_the_fence_no_longer_closes_the_block(self) -> None:
        """The one deliberate tightening.

        `text.find("\\n---", 3)` was a substring search, so any line starting
        with three dashes closed the block. A forged close could therefore hide
        whatever followed it from every caller of this helper.
        """
        assert _parse_yaml_frontmatter("---\nid: A\n--- nope\nBody.\n") is None

    @pytest.mark.parametrize(
        ("label", "text"),
        [
            ("padded closing fence", "---\nid: A\n--- \nBody.\n"),
            ("tabbed closing fence", "---\nid: A\n---\t\nBody.\n"),
            ("four dashes", "---\nid: A\n----\nBody.\n"),
            ("closing fence at EOF", "---\nid: A\n---"),
            ("crlf", "---\r\nid: A\r\n---\r\nBody.\r\n"),
        ],
    )
    def test_shapes_this_helper_already_accepted_still_parse(self, label: str, text: str) -> None:
        """The substring search accepted all of these; so does the contract.

        This is the half of the migration that must NOT change, and it is why
        #5275's divergence ran the other way: the index generator rejected
        shapes this helper had always allowed.
        """
        assert _parse_yaml_frontmatter(text) == {"id": "A"}, label

    def test_duplicate_keys_still_resolve_last_wins(self) -> None:
        """Deliberately unchanged, per acceptance criterion 3.

        The contract can reject duplicates and the ADR gates ask it to, but this
        helper's other callers were not written against that rule. Changing it
        here would alter three gates nobody reviewed for it.
        """
        assert _parse_yaml_frontmatter("---\nid: A\nid: B\n---\nBody.\n") == {"id": "B"}

    def test_an_empty_block_is_none_not_an_empty_mapping(self) -> None:
        """Regression: the first migration returned `{}` here and broke a gate.

        The contract counts an empty block as parsed (status EMPTY, metadata
        `{}`), but `yaml.safe_load("")` returns None, which the old
        `isinstance(result, dict)` test rejected. Returning `{}` flipped
        `check_adr_lifecycle`'s reason for such a record from "frontmatter block
        is empty" to a missing-field complaint, and
        `test_empty_frontmatter_block_names_itself` caught it. No file in the
        corpus has an empty block, so only the suite could find this.
        """
        assert _parse_yaml_frontmatter("---\n---\nBody.\n") is None

    def test_still_collapses_absent_and_malformed_to_none(self) -> None:
        """The `dict | None` signature is what four call sites depend on."""
        assert _parse_yaml_frontmatter("no frontmatter here\n") is None
        assert _parse_yaml_frontmatter('---\nid: "unclosed\n---\nBody.\n') is None
        assert _parse_yaml_frontmatter("---\n- a\n- b\n---\nBody.\n") is None
        assert _parse_yaml_frontmatter("---\nid: A\nBody.\n") is None
