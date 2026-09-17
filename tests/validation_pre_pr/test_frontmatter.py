"""Frontmatter validation tests for pre-PR architecture checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.validation.pre_pr import (
    _parse_yaml_frontmatter,
    validate_design_review_frontmatter,
)


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
        text = '---\nstatus: "BLOCKED"\nreviewer: \'architect\'\n---\n'
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
        text = (
            "---\n"
            "description: Agent examples: Context: user asks\n"
            "---\n"
        )
        assert _parse_yaml_frontmatter(text) is None


class TestValidateDesignReviewFrontmatter:
    """Tests for DESIGN-REVIEW frontmatter validation."""

    def _write_review(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper to create a DESIGN-REVIEW file."""
        review_dir = tmp_path / ".agents" / "architecture"
        review_dir.mkdir(parents=True, exist_ok=True)
        filepath = review_dir / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_no_directory_returns_true(self, tmp_path: Path) -> None:
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_no_review_files_returns_true(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "architecture").mkdir(parents=True)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_valid_frontmatter_passes(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_missing_frontmatter_fails(self, tmp_path: Path) -> None:
        content = "# Design Review: Test\nNo frontmatter here.\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_missing_required_fields_fails(self, tmp_path: Path) -> None:
        content = '---\nstatus: "APPROVED"\n---\n# Design Review: Test\n'
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_status_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "INVALID"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_priority_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P99"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_blocking_review_detected(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: true\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        # Blocking reviews still pass validation (they just warn)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_blocking_null_does_not_count_as_blocking(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: null\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)

        assert validate_design_review_frontmatter(tmp_path) is True

        captured = capsys.readouterr()
        assert "should have blocking: true" in captured.out
        assert "blocking review(s) detected" not in captured.out

    def test_multiple_files_all_valid(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", valid)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_one_invalid_among_valid_fails(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        invalid = "# No frontmatter\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", invalid)
        assert validate_design_review_frontmatter(tmp_path) is False


class TestDelegatesToTheSharedContract:
    """Issue #5275 follow-up: this helper no longer parses fences itself.

    It delegates to `scripts/validation/frontmatter_contract.py`, and through it
    to `python-frontmatter`. These tests pin what that changed and, more
    importantly, what it did not, because the helper has four call sites
    (`pre_pr.py`, `check_adr_lifecycle.py`, `validate_design_review.py`,
    `validate_copilot_agent_frontmatter.py`) whose behaviour #5275's third
    acceptance criterion holds fixed.
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
    def test_shapes_this_helper_already_accepted_still_parse(
        self, label: str, text: str
    ) -> None:
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

    def test_helper_defines_no_fence_logic_of_its_own(self) -> None:
        """Checked with `ast`: the module docstring quotes the old expression."""
        import ast
        from pathlib import Path

        import scripts.validation.yaml_utils as mod

        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert "re" not in imported
        assert "yaml" not in imported, "the helper should no longer load YAML itself"
