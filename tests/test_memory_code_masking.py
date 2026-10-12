"""Tests for code_masking, which hides markdown code from citation parsing."""

from __future__ import annotations

import pytest

from memory_enhancement.code_masking import mask_code

CITE = "[cite:file](does/not/exist.py)"


class TestMaskCodeFences:
    """Fenced blocks are blanked; surrounding text is untouched."""

    @pytest.mark.unit
    def test_backtick_fence_is_blanked(self):
        text = f"before\n```\n{CITE}\n```\nafter\n"
        masked = mask_code(text)
        assert "cite" not in masked
        assert masked.startswith("before\n")
        assert masked.endswith("\nafter\n")

    @pytest.mark.unit
    def test_tilde_fence_is_blanked(self):
        assert "cite" not in mask_code(f"~~~\n{CITE}\n~~~\n")

    @pytest.mark.unit
    def test_fence_with_info_string_is_blanked(self):
        assert "cite" not in mask_code(f"```bash\n{CITE}\n```\n")

    @pytest.mark.unit
    def test_indented_fence_is_blanked(self):
        assert "cite" not in mask_code(f"   ```\n   {CITE}\n   ```\n")

    @pytest.mark.unit
    def test_fence_nested_in_list_item_is_blanked(self):
        assert "cite" not in mask_code(f"- item\n\n      ```\n      {CITE}\n      ```\n")

    @pytest.mark.unit
    def test_unterminated_fence_runs_to_end(self):
        masked = mask_code(f"intro\n```\n{CITE}\nmore\n")
        assert "cite" not in masked
        assert masked.startswith("intro\n")

    @pytest.mark.unit
    def test_unterminated_fence_on_last_line_without_newline(self):
        assert mask_code("text\n```") == "text\n   "

    @pytest.mark.unit
    def test_longer_closer_ends_the_block(self):
        text = f"````\n{CITE}\n`````\n{CITE}\n"
        masked = mask_code(text)
        assert masked.count("cite") == 1

    @pytest.mark.unit
    def test_shorter_closer_does_not_end_the_block(self):
        text = f"````\n```\n{CITE}\n````\nafter\n"
        masked = mask_code(text)
        assert "cite" not in masked
        assert masked.endswith("after\n")

    @pytest.mark.unit
    def test_backtick_closer_does_not_end_a_tilde_block(self):
        text = f"~~~\n```\n{CITE}\n~~~\n"
        assert "cite" not in mask_code(text)

    @pytest.mark.unit
    def test_closer_with_trailing_text_does_not_end_the_block(self):
        text = f"```\n``` not a closer\n{CITE}\n```\nafter\n"
        assert "cite" not in mask_code(text)

    @pytest.mark.unit
    def test_backtick_in_info_string_is_not_a_fence(self):
        text = f"```lang`x`\n{CITE}\n"
        assert CITE in mask_code(text)

    @pytest.mark.unit
    def test_tilde_fence_allows_backtick_in_info_string(self):
        assert "cite" not in mask_code(f"~~~ lang`x`\n{CITE}\n~~~\n")

    @pytest.mark.unit
    def test_two_fences_leave_text_between_them_live(self):
        text = f"```\na\n```\n{CITE}\n```\nb\n```\n"
        masked = mask_code(text)
        assert masked.count("cite") == 1

    @pytest.mark.unit
    def test_fence_inside_a_block_is_not_reopened(self):
        text = f"````\n```\ninner\n```\n````\n{CITE}\n"
        masked = mask_code(text)
        assert masked.count("cite") == 1

    @pytest.mark.unit
    def test_blockquote_fence_is_blanked_as_a_span(self):
        text = f"> ```\n> {CITE}\n> ```\n"
        assert "cite" not in mask_code(text)


class TestMaskCodeSpans:
    """Inline code spans are blanked."""

    @pytest.mark.unit
    def test_single_backtick_span_is_blanked(self):
        masked = mask_code(f"see `{CITE}` here")
        assert "cite" not in masked
        assert masked.startswith("see ")
        assert masked.endswith(" here")

    @pytest.mark.unit
    def test_double_backtick_span_is_blanked(self):
        assert "cite" not in mask_code(f"see ``{CITE}`` here")

    @pytest.mark.unit
    def test_span_closes_only_on_a_run_of_equal_length(self):
        text = f"``a ` {CITE}`` tail {CITE}"
        masked = mask_code(text)
        assert masked.count("cite") == 1

    @pytest.mark.unit
    def test_unmatched_backtick_leaves_text_live(self):
        assert CITE in mask_code(f"a ` stray {CITE}")

    @pytest.mark.unit
    def test_span_does_not_cross_a_blank_line(self):
        text = f"a `open\n\nclose` {CITE}"
        assert CITE in mask_code(text)

    @pytest.mark.unit
    def test_span_may_cross_a_single_newline(self):
        assert "cite" not in mask_code(f"a `open\n{CITE}` end")


class TestMaskCodeShape:
    """Masking preserves length and line structure."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "plain text\n",
            f"```\n{CITE}\n```\n",
            f"a `{CITE}` b\n\n~~~\nx\n",
            f"```\n{CITE}",
        ],
    )
    def test_length_and_newlines_are_preserved(self, text):
        masked = mask_code(text)
        assert len(masked) == len(text)
        assert [i for i, c in enumerate(masked) if c == "\n"] == [
            i for i, c in enumerate(text) if c == "\n"
        ]

    @pytest.mark.unit
    def test_text_without_code_is_unchanged(self):
        text = f"# Title\n\n{CITE} - context\n"
        assert mask_code(text) == text
