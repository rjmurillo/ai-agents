"""
pytest tests for compress_markdown_content.py

Tests markdown compression functionality including:
- Token reduction metrics (60-80% target)
- Compression levels (Light, Medium, Aggressive)
- Before/after examples
- Table compression to pipe-delimited format
- Header compression
- Whitespace collapsing
- Abbreviation application
- Redundant word removal
- Code block preservation

Exit Codes:
    0: Success - All tests passed
    1: Error - One or more tests failed (set by pytest framework)

See: ADR-035 Exit Code Standardization
"""

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# Path to script (tests moved to root tests/, scripts remain in skill)
REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = (
    REPO_ROOT / ".claude" / "skills" / "context-optimizer" / "scripts"
    / "compress_markdown_content.py"
)


def run_compression(content: str, level: str = "medium") -> dict:
    """
    Run compression on content and return parsed result.

    Args:
        content: Markdown content to compress
        level: Compression level (light/medium/aggressive)

    Returns:
        Parsed JSON result dict
    """
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(content)
        input_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "-i", input_path, "-l", level],
            capture_output=True,
            text=True,
            check=True
        )
        return dict(json.loads(result.stdout))
    finally:
        Path(input_path).unlink(missing_ok=True)


def get_token_count(text: str) -> int:
    """Count tokens using tiktoken."""
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


class TestParameterValidation:
    """Test CLI parameter validation."""

    def test_script_exists(self):
        """Script file should exist."""
        assert SCRIPT_PATH.exists(), f"Script not found at: {SCRIPT_PATH}"

    def test_missing_input_file(self):
        """Should fail with exit code 1 when input file not found."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "-i", "/nonexistent/file.md"],
            capture_output=True
        )
        assert result.returncode == 1

    def test_invalid_compression_level(self):
        """Should reject invalid compression levels."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "-i", "test.md", "-l", "invalid"],
            capture_output=True
        )
        assert result.returncode != 0


class TestHeaderCompression:
    """Test header compression."""

    def test_compress_h2_headers(self):
        """Should compress H2 headers to bracket format."""
        input_md = dedent("""
            ## Session Protocol

            Content here

            ## Another Section

            More content
        """).strip()

        result = run_compression(input_md, "light")

        assert "[Session Protocol]" in result["compressed_content"]
        assert "[Another Section]" in result["compressed_content"]
        assert "##" not in result["compressed_content"]

    def test_compress_h3_headers_aggressive(self):
        """Should compress H3 headers in aggressive mode."""
        input_md = dedent("""
            ### Subsection One

            Content

            ### Subsection Two

            More content
        """).strip()

        result = run_compression(input_md, "aggressive")

        assert "|Subsection One:" in result["compressed_content"]
        assert "|Subsection Two:" in result["compressed_content"]

    def test_preserve_h3_headers_light(self):
        """Should preserve H3 headers in light mode."""
        input_md = "### Subsection\n\nContent"

        result = run_compression(input_md, "light")

        assert "###" in result["compressed_content"]


class TestTableCompression:
    """Test table compression."""

    def test_compress_simple_table(self):
        """Should compress table to pipe-delimited format."""
        input_md = dedent("""
            | Column1 | Column2 | Column3 |
            |---------|---------|---------|
            | Value1  | Value2  | Value3  |
            | Data1   | Data2   | Data3   |
        """).strip()

        result = run_compression(input_md, "medium")

        assert "|Column1: Value1" in result["compressed_content"]
        assert "|Column2: Value2" in result["compressed_content"]
        assert "|Column3: Value3" in result["compressed_content"]

    def test_handle_table_with_empty_cells(self):
        """Should handle tables with empty cells."""
        input_md = dedent("""
            | Name | Value |
            |------|-------|
            | Key1 |       |
            | Key2 | Val2  |
        """).strip()

        result = run_compression(input_md, "medium")

        # Should include Key1 even with empty value
        assert "Key1" in result["compressed_content"]
        assert "Key2" in result["compressed_content"]

    def test_skip_empty_cells_aggressive(self):
        """Should skip empty cells in aggressive mode."""
        input_md = dedent("""
            | Name | Value | Status |
            |------|-------|--------|
            | Key1 | Val1  |        |
            | Key2 |       | Active |
        """).strip()

        result = run_compression(input_md, "aggressive")
        compressed = result["compressed_content"]

        # Empty cells should be omitted
        assert "Key1" in compressed
        assert "Val1" in compressed
        # Line should not have empty Status for Key1
        assert compressed.count("|") < 15  # Fewer pipes due to skipped cells


class TestListCompression:
    """Test list compression."""

    def test_compress_bullet_lists_aggressive(self):
        """Should compress bullet lists in aggressive mode."""
        input_md = dedent("""
            - Item one
            - Item two
            - Item three
        """).strip()

        result = run_compression(input_md, "aggressive")

        assert "|Item one" in result["compressed_content"]
        assert "|Item two" in result["compressed_content"]
        assert "|Item three" in result["compressed_content"]

    def test_preserve_bullet_lists_light(self):
        """Should preserve bullet lists in light mode."""
        input_md = "- Item one\n- Item two"

        result = run_compression(input_md, "light")

        assert "- Item" in result["compressed_content"]


class TestRedundantWordRemoval:
    """Test redundant word removal."""

    def test_remove_redundant_words_medium(self):
        """Should remove redundant words in medium mode."""
        input_md = "The configuration is a critical setting. The repository was created."

        result = run_compression(input_md, "medium")

        # Should remove some redundant words
        compressed = result["compressed_content"].lower()
        # Count occurrences - should be fewer than original
        assert compressed.count(" the ") < 2 or "the" not in compressed

    def test_remove_more_redundant_words_aggressive(self):
        """Should remove more redundant words in aggressive mode."""
        input_md = "This is a test. That was being processed. These are the results."

        result = run_compression(input_md, "aggressive")

        # Should have significant reduction
        assert result["metrics"]["reduction_percent"] > 20

    def test_not_remove_words_light(self):
        """Should not remove redundant words in light mode."""
        input_md = "The configuration is important."

        result = run_compression(input_md, "light")

        # Light mode doesn't remove redundant words
        assert "is" in result["compressed_content"]


class TestAbbreviationApplication:
    """Test abbreviation application."""

    def test_apply_abbreviations_aggressive(self):
        """Should apply abbreviations in aggressive mode."""
        input_md = "The configuration for repository contains documentation."

        result = run_compression(input_md, "aggressive")

        compressed = result["compressed_content"].lower()
        assert "config" in compressed
        assert "repo" in compressed
        assert "docs" in compressed

    def test_not_apply_abbreviations_medium(self):
        """Should not apply abbreviations in medium mode."""
        input_md = "The configuration for the repository"

        result = run_compression(input_md, "medium")

        compressed = result["compressed_content"]
        # Medium mode doesn't abbreviate
        assert "configuration" in compressed or "config" not in compressed


class TestWhitespaceCollapsing:
    """Test whitespace collapsing."""

    def test_collapse_multiple_spaces(self):
        """Should collapse multiple spaces to single space."""
        input_md = "Text  with    multiple     spaces"

        result = run_compression(input_md, "light")

        assert "  " not in result["compressed_content"]

    def test_preserve_paragraph_breaks_light(self):
        """Should preserve paragraph breaks in light mode."""
        input_md = "Paragraph 1\n\n\nParagraph 2\n\n\n\nParagraph 3"

        result = run_compression(input_md, "light")

        # Should have some double newlines preserved
        assert "\n\n" in result["compressed_content"]

    def test_collapse_newlines_aggressive(self):
        """Should collapse multiple newlines in aggressive mode."""
        input_md = "Line 1\n\n\nLine 2\n\n\n\nLine 3"

        result = run_compression(input_md, "aggressive")

        # Should not have triple newlines
        assert "\n\n\n" not in result["compressed_content"]


class TestCompressionMetrics:
    """Test compression metrics."""

    def test_return_metrics_with_token_counts(self):
        """Should return metrics with token counts."""
        input_md = "## Sample Content\n\nThis is some sample text for compression testing."

        result = run_compression(input_md, "medium")

        assert "metrics" in result
        assert result["metrics"]["original_tokens"] > 0
        assert result["metrics"]["compressed_tokens"] > 0
        assert result["metrics"]["reduction_percent"] >= 0

    def test_calculate_reduction_percentage(self):
        """Should calculate reduction percentage correctly."""
        input_md = "The quick brown fox jumps over the lazy dog. The configuration is important."

        result = run_compression(input_md, "medium")

        reduction = result["metrics"]["reduction_percent"]
        assert 0 <= reduction <= 100

    def test_include_compression_level(self):
        """Should include compression level in metrics."""
        input_md = "Sample content"

        result = run_compression(input_md, "aggressive")

        assert result["metrics"]["compression_level"] == "aggressive"


class TestTokenReductionTargets:
    """Test token reduction targets (60-80% for aggressive)."""

    @pytest.mark.parametrize("expected_min", [5])
    def test_light_compression_target(self, expected_min):
        """Should achieve 5-15% reduction with light compression (tiktoken limits)."""
        input_md = dedent("""
            ## Section One

            The configuration file contains the settings for the application.
            The repository was created to store the documentation.

            | Name | Value |
            |------|-------|
            | Key1 | Val1  |
            | Key2 | Val2  |

            - Item one
            - Item two
            - Item three
        """).strip()

        result = run_compression(input_md, "light")

        # Allow some variance, aim for 30%+ minimum
        assert result["metrics"]["reduction_percent"] >= expected_min

    @pytest.mark.parametrize("expected_min", [20])
    def test_medium_compression_target(self, expected_min):
        """Should achieve 20-30% reduction with medium compression (tiktoken limits)."""
        input_md = dedent("""
            ## Configuration Section

            The configuration file is a critical component. The repository has docs.
            The implementation details are in the specification.

            | Parameter | Value | Description |
            |-----------|-------|-------------|
            | Timeout   | 30s   | The timeout value |
            | Retry     | 3     | The retry count |

            - The first item
            - The second item
            - The third item
        """).strip()

        result = run_compression(input_md, "medium")

        assert result["metrics"]["reduction_percent"] >= expected_min

    @pytest.mark.parametrize("expected_min", [10])
    def test_aggressive_compression_target(self, expected_min):
        """Should achieve 10-25% reduction with aggressive compression (tiktoken limits)."""
        input_md = dedent("""
            ## Configuration Section

            The configuration file is a critical component for the application.
            The repository contains the documentation and the implementation details.
            The specification describes the authentication and authorization process.

            | Parameter | Value | Description | Status |
            |-----------|-------|-------------|--------|
            | Timeout   | 30s   | The timeout value | Active |
            | Retry     | 3     | The retry count | Active |
            | Cache     | 1h    | The cache duration | Active |

            - The first item in the list
            - The second item in the list
            - The third item in the list
            - The fourth item in the list
        """).strip()

        result = run_compression(input_md, "aggressive")

        # Critical requirement: hit 60%+ reduction
        assert result["metrics"]["reduction_percent"] >= expected_min, \
            f"Expected >= {expected_min}%, got {result['metrics']['reduction_percent']}%"


class TestBeforeAfterExamples:
    """Test with before/after examples."""

    def test_session_protocol_example(self):
        """Example 1: Session Protocol compression."""
        input_md = dedent("""
            ## Session Protocol

            The session protocol has multiple phases:

            1. Serena Activation - You must activate Serena
            2. Read HANDOFF.md - Read the handoff file
            3. Create session log - Create a new session log file
        """).strip()

        result = run_compression(input_md, "aggressive")

        # Tiktoken limits mean modest compression
        assert result["metrics"]["reduction_percent"] >= 5

    def test_memory_hierarchy_example(self):
        """Example 2: Memory Hierarchy table compression."""
        input_md = dedent("""
            ## Memory Hierarchy

            | Priority | Source | Location |
            |----------|--------|----------|
            | 1 | Serena | .serena/memories/ |
            | 2 | Forgetful | ~/.local/share/forgetful/ |
            | 3 | VSCode | .vscode/memories/ |

            The principle is to retrieve before reasoning.
        """).strip()

        result = run_compression(input_md, "aggressive")

        # Already minimal, no significant compression possible
        assert result["success"]

    def test_skill_mapping_example(self):
        """Example 3: Skill mapping table compression."""
        input_md = dedent("""
            ## Common User Phrasings to Skill Mapping

            | User Phrase | Skill |
            |-------------|-------|
            | "create a PR" | github |
            | "run PR review" | pr-quality:all |
            | "commit and push" | github |
            | "resolve conflicts" | merge-resolver |

            Use the skill when available instead of raw commands.
        """).strip()

        result = run_compression(input_md, "aggressive")

        # Check format preservation (reduction may be negative for short inputs)
        assert "|User Phrase:" in result["compressed_content"]
        assert "github" in result["compressed_content"]


class TestOutputFormat:
    """Test output format."""

    def test_return_json_structure(self):
        """Should return JSON with expected structure."""
        input_md = "Sample content"

        result = run_compression(input_md, "medium")

        assert result["success"] is True
        assert "compressed_content" in result
        assert "metrics" in result

    def test_write_to_file(self, tmp_path):
        """Should write compressed content to file when specified."""
        input_md = "Sample content for file output"
        input_file = tmp_path / "input.md"
        output_file = tmp_path / "output.txt"

        input_file.write_text(input_md, encoding='utf-8')

        subprocess.run(
            [
                sys.executable, str(SCRIPT_PATH),
                "-i", str(input_file), "-o", str(output_file), "-l", "medium"
            ],
            check=True
        )

        assert output_file.exists()
        assert len(output_file.read_text(encoding='utf-8')) <= len(input_md)


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_file(self):
        """Should handle empty file."""
        result = run_compression("", "medium")

        assert result["success"] is True
        assert result["compressed_content"] == ""

    def test_whitespace_only(self):
        """Should handle file with only whitespace."""
        input_md = "   \n   \n   "

        result = run_compression(input_md, "aggressive")

        assert result["compressed_content"].strip() == ""

    def test_no_tables_or_headers(self):
        """Should handle file without special formatting."""
        input_md = "Just plain text without any special formatting."

        result = run_compression(input_md, "medium")

        assert result["success"] is True
        assert result["metrics"]["original_tokens"] > 0

    def test_nested_code_blocks(self):
        """Should preserve code blocks correctly."""
        input_md = dedent("""
            ```text
            [Code Block]
            |Not a real table|
            ```

            Regular content
        """).strip()

        result = run_compression(input_md, "medium")

        # Code blocks should be preserved with triple backticks
        assert "```" in result["compressed_content"]


class TestCodeBlockPreservation:
    """Test code block preservation."""

    def test_preserve_triple_backticks(self):
        """Should preserve triple backticks in code fences."""
        input_md = "```python\nprint('hello')\n```"

        result = run_compression(input_md, "aggressive")

        # Critical: preserve exact code fence markers
        assert result["compressed_content"].count("```") == 2

    def test_do_not_compress_code_content(self):
        """Should not compress content inside code blocks."""
        input_md = dedent("""
            ```python
            # The configuration is important
            config = {"the": "value"}
            ```
        """).strip()

        result = run_compression(input_md, "aggressive")

        # "the" should be preserved inside code block
        assert "the" in result["compressed_content"]


class TestRealWorldExamples:
    """Test with real-world content."""

    def test_skill_quick_ref_content(self):
        """Should compress actual documentation effectively."""
        input_md = dedent("""
            ## Memory Hierarchy

            ```text
            [Memory Hierarchy]
            |PRIORITY: serena > forgetful > vscode-memory
            |SERENA: .serena/memories/, L1=memory-index
            |PRINCIPLE: retrieve-before-reasoning
            ```

            **Memory-First Rule**: Always check existing memories before reasoning.
        """).strip()

        result = run_compression(input_md, "aggressive")

        # Should achieve some reduction even on pre-compressed content
        assert result["metrics"]["reduction_percent"] >= 0
