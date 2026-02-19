"""Tests for context-optimizer word removal content preservation (#1119).

Verifies that remove_redundant_words preserves inline code, URLs,
YAML frontmatter, and code blocks while removing filler words from prose.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)
from compress_markdown_content import CompressionLevel, remove_redundant_words


class TestWordRemovalPreservesContent:
    """Verify protected content is not corrupted by word removal."""

    def test_inline_code_preserved(self) -> None:
        """Backtick-wrapped inline code is not modified."""
        content = "Use the `the_variable` in a loop"
        result = remove_redundant_words(content, CompressionLevel.AGGRESSIVE)
        assert "`the_variable`" in result

    def test_url_preserved(self) -> None:
        """URLs are not corrupted by word removal."""
        content = "See the docs at https://example.com/the/path/is/here"
        result = remove_redundant_words(content, CompressionLevel.AGGRESSIVE)
        assert "https://example.com/the/path/is/here" in result

    def test_yaml_frontmatter_preserved(self) -> None:
        """YAML frontmatter between --- markers is not modified."""
        content = "---\ntitle: The Great Article\ndescription: A guide\n---\nThe body text"
        result = remove_redundant_words(content, CompressionLevel.AGGRESSIVE)
        assert "title: The Great Article" in result
        assert "description: A guide" in result

    def test_prose_words_removed(self) -> None:
        """Regular prose has filler words removed at aggressive level."""
        content = "The user should use the function to do the thing"
        result = remove_redundant_words(content, CompressionLevel.AGGRESSIVE)
        # "The" and "the" should be removed from prose
        assert result.count("the ") < content.count("the ")

    def test_light_level_no_removal(self) -> None:
        """Light compression level does not remove any words."""
        content = "The user should use the function"
        result = remove_redundant_words(content, CompressionLevel.LIGHT)
        assert result == content

    def test_code_block_fence_lines_preserved(self) -> None:
        """Lines with triple backtick code fences are not modified."""
        content = "```python\nthe_var = True\n```\nThe end"
        result = remove_redundant_words(content, CompressionLevel.AGGRESSIVE)
        assert "```python" in result

    def test_mixed_content_selective_removal(self) -> None:
        """In mixed content, only prose lines get word removal."""
        content = (
            "The function is great\n"
            "Use `the_helper()` for the task\n"
            "See https://the-docs.com/api\n"
            "The result was good"
        )
        result = remove_redundant_words(content, CompressionLevel.MEDIUM)
        # Inline code line preserved
        assert "`the_helper()`" in result
        # URL line preserved
        assert "https://the-docs.com/api" in result
        # Prose lines had words removed (check "The" was removed)
        lines = result.split("\n")
        # First and last lines are prose - should have reduced "the"
        assert not lines[0].startswith("The ")

    def test_http_url_preserved(self) -> None:
        """HTTP (non-HTTPS) URLs are also preserved."""
        content = "The server is at http://the-server.local/api"
        result = remove_redundant_words(content, CompressionLevel.AGGRESSIVE)
        assert "http://the-server.local/api" in result
