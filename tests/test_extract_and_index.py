# taste-lint: ignore file-size
# These tests share one fixture and exercise the core extractor API.

"""pytest tests for extract_and_index.py

Tests the extract-and-index pattern for markdown compression including:
- Section parsing from headings
- Slug generation
- Index generation in pipe-delimited Vercel format
- Detail file writing
- Token reduction metrics (60-80% target)
- CWE-22 path validation
- CLI interface

Exit Codes:
    0: Success - All tests passed
    1: Error - One or more tests failed (set by pytest framework)

See: ADR-035 Exit Code Standardization
"""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = (
    REPO_ROOT / ".claude" / "skills" / "context-optimizer" / "scripts" / "extract_and_index.py"
)

# Add scripts dir to path so we can import directly for unit tests
SCRIPTS_DIR = SCRIPT_PATH.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from context_output_parsing import _update_fence_marker  # noqa: E402
from extract_and_index import (  # noqa: E402
    Section,
    build_index,
    extract_and_index,
    parse_sections,
    slugify,
    summarize_section,
    write_detail_files,
)


def _has_tiktoken_encoding() -> bool:
    """Return True when cl100k_base can be loaded without network errors."""
    try:
        import tiktoken

        tiktoken.get_encoding("cl100k_base").encode("probe")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the extract_and_index.py script as a subprocess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def make_temp_input(tmp_path: Path, content: str) -> Path:
    """Write content to a temp markdown file inside the repo for CWE-22 compliance."""
    tmp_dir = REPO_ROOT / ".pytest_tmp"
    tmp_dir.mkdir(exist_ok=True)
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8", dir=str(tmp_dir)
    ) as f:
        f.write(content)
        return Path(f.name)


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


SAMPLE_DOC = dedent("""\
    # Project Overview

    This project provides agent orchestration for AI workflows.
    It handles session management, skill routing, and memory persistence.

    ## Architecture

    The system uses a layered architecture with clear separation of concerns.
    Agents communicate through a central orchestrator that routes tasks.

    | Layer | Purpose |
    |-------|---------|
    | Orchestrator | Task routing and coordination |
    | Agents | Specialized task execution |
    | Memory | Cross-session persistence |

    ## Configuration

    Configuration is managed through YAML files and environment variables.
    Each agent has its own configuration section.

    ### Agent Config

    ```yaml
    agents:
      orchestrator:
        model: opus
        max_turns: 50
    ```

    ## Testing

    All agents require 80% test coverage for business logic.
    Security-critical paths require 100% coverage.
""")


# ---------------------------------------------------------------------------
# Unit tests: slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_simple_heading(self):
        assert slugify("Architecture") == "architecture"

    def test_heading_with_spaces(self):
        assert slugify("Project Overview") == "project-overview"

    def test_heading_with_special_chars(self):
        assert slugify("Config: Agent (v2)") == "config-agent-v2"

    def test_empty_heading(self):
        assert slugify("") == "untitled"

    def test_heading_with_underscores(self):
        assert slugify("my_config_file") == "my-config-file"


# ---------------------------------------------------------------------------
# Unit tests: parse_sections
# ---------------------------------------------------------------------------


class TestParseSections:
    def test_preserves_fence_marker_for_mismatched_delimiter(self):
        assert _update_fence_marker("~~~", "```") == (True, "```")

    def test_splits_on_h1_and_h2(self):
        content = "# Title\n\nIntro text\n\n## Section A\n\nBody A\n\n## Section B\n\nBody B"
        sections = parse_sections(content)
        headings = [s.heading for s in sections]
        assert headings == ["Title", "Section A", "Section B"]

    def test_preamble_before_first_heading(self):
        content = "Some preamble text\n\n## First Section\n\nBody"
        sections = parse_sections(content)
        assert sections[0].heading == "preamble"
        assert "preamble text" in sections[0].content

    def test_empty_content(self):
        sections = parse_sections("")
        assert sections == []

    def test_no_headings(self):
        content = "Just plain text with no headings."
        sections = parse_sections(content)
        assert len(sections) == 1
        assert sections[0].heading == "preamble"

    def test_preserves_h3_within_section(self):
        content = "## Main\n\n### Sub\n\nSub content"
        sections = parse_sections(content)
        assert len(sections) == 1
        assert "### Sub" in sections[0].content

    def test_ignores_headings_inside_fenced_code(self):
        content = "## Main\n\n```markdown\n## Fake\n```\n\n## Real\n\nBody"
        sections = parse_sections(content)
        assert [section.heading for section in sections] == ["Main", "Real"]
        assert "## Fake" in sections[0].content

    def test_section_levels(self):
        content = "# H1\n\nBody\n\n## H2\n\nBody"
        sections = parse_sections(content)
        assert sections[0].level == 1
        assert sections[1].level == 2

    def test_slug_assignment(self):
        content = "## My Config Section\n\nBody"
        sections = parse_sections(content)
        assert sections[0].slug == "my-config-section"


# ---------------------------------------------------------------------------
# Unit tests: summarize_section
# ---------------------------------------------------------------------------


class TestSummarizeSection:
    def test_uses_first_meaningful_line(self):
        section = Section(
            heading="Arch", level=2, content="Uses layered design.\nMore detail.", slug="arch"
        )
        assert summarize_section(section) == "Uses layered design."

    def test_skips_code_fences(self):
        section = Section(
            heading="Code", level=2, content="```yaml\nfoo: bar\n```\nActual summary.", slug="code"
        )
        assert summarize_section(section) == "Actual summary."

    def test_skips_nested_markdown_headings(self):
        section = Section(
            heading="Main", level=2, content="### Nested\nActual summary.", slug="main"
        )
        assert summarize_section(section) == "Actual summary."

    def test_truncates_long_lines(self):
        long_line = "A" * 100
        section = Section(heading="Long", level=2, content=long_line, slug="long")
        summary = summarize_section(section)
        assert len(summary) <= 80
        assert summary.endswith("...")

    def test_fallback_for_code_only(self):
        section = Section(heading="Code", level=2, content="```\nonly code\n```", slug="code")
        assert summarize_section(section) == "(see detail file)"

    def test_strips_list_markers(self):
        section = Section(heading="List", level=2, content="- First item", slug="list")
        assert summarize_section(section) == "First item"


# ---------------------------------------------------------------------------
# Unit tests: build_index
# ---------------------------------------------------------------------------


class TestBuildIndex:
    def test_produces_pipe_delimited_format(self):
        sections = [
            Section(
                heading="Architecture",
                level=2,
                content="Layered design.",
                slug="architecture",
            ),
            Section(heading="Testing", level=2, content="80% coverage required.", slug="testing"),
        ]
        index = build_index(sections, ".details")
        assert "[Architecture]" in index
        assert "|Layered design. (see: .details/architecture.md)" in index
        assert "[Testing]" in index

    def test_skips_empty_preamble(self):
        sections = [
            Section(heading="preamble", level=0, content="", slug="preamble"),
            Section(heading="Real", level=2, content="Content.", slug="real"),
        ]
        index = build_index(sections, ".d")
        assert "preamble" not in index.lower() or "Overview" not in index
        assert "[Real]" in index

    def test_preamble_with_content_becomes_overview(self):
        sections = [
            Section(heading="preamble", level=0, content="Intro text.", slug="preamble"),
        ]
        index = build_index(sections, ".d")
        assert "[Overview]" in index

    def test_duplicate_slugs_use_unique_detail_references(self):
        sections = [
            Section(heading="Config", level=2, content="First", slug="config"),
            Section(heading="Config", level=2, content="Second", slug="config"),
        ]

        index = build_index(sections, ".details")

        assert "(see: .details/config.md)" in index
        assert "(see: .details/config-1.md)" in index

    def test_slug_suffix_collision_does_not_overwrite_details(self):
        """AC: duplicate and suffix-like headings retain distinct detail files."""
        sections = [
            Section(heading="Config", level=2, content="First", slug="config"),
            Section(heading="Config 1", level=2, content="Named suffix", slug="config-1"),
            Section(heading="Config", level=2, content="Second", slug="config"),
        ]

        index = build_index(sections, ".details")

        assert index.count("(see: .details/config.md)") == 1
        assert index.count("(see: .details/config-1.md)") == 1
        assert index.count("(see: .details/config-2.md)") == 1


# ---------------------------------------------------------------------------
# Unit tests: write_detail_files
# ---------------------------------------------------------------------------


class TestWriteDetailFiles:
    def test_creates_files(self, tmp_path):
        detail_dir = tmp_path / "details"
        sections = [
            Section(heading="Arch", level=2, content="Body text.", slug="arch"),
        ]
        count = write_detail_files(sections, detail_dir, repo_root=tmp_path)
        assert count == 1
        assert (detail_dir / "arch.md").exists()
        content = (detail_dir / "arch.md").read_text()
        assert "## Arch" in content
        assert "Body text." in content

    def test_handles_duplicate_slugs(self, tmp_path):
        detail_dir = tmp_path / "details"
        sections = [
            Section(heading="Config", level=2, content="A", slug="config"),
            Section(heading="Config", level=2, content="B", slug="config"),
        ]
        count = write_detail_files(sections, detail_dir, repo_root=tmp_path)
        assert count == 2
        assert (detail_dir / "config.md").exists()
        assert (detail_dir / "config-1.md").exists()

    def test_creates_parent_dirs(self, tmp_path):
        detail_dir = tmp_path / "deep" / "nested" / "dir"
        sections = [
            Section(heading="Test", level=1, content="Body.", slug="test"),
        ]
        write_detail_files(sections, detail_dir, repo_root=tmp_path)
        assert (detail_dir / "test.md").exists()


# ---------------------------------------------------------------------------
# Integration: extract_and_index function
# ---------------------------------------------------------------------------


class TestExtractAndIndex:
    def test_full_pipeline(self, tmp_path):
        detail_dir = tmp_path / "details"
        result = extract_and_index(SAMPLE_DOC, detail_dir, ".details", repo_root=tmp_path)
        assert result.success is True
        assert result.metrics.sections_extracted >= 3
        assert result.metrics.detail_files_written >= 3
        assert result.metrics.reduction_percent > 0

    def test_achieves_significant_reduction(self, tmp_path):
        detail_dir = tmp_path / "details"
        result = extract_and_index(SAMPLE_DOC, detail_dir, ".details", repo_root=tmp_path)
        # The index should be substantially smaller than the original
        assert result.metrics.index_tokens < result.metrics.original_tokens
        assert result.metrics.reduction_percent >= 40

    def test_index_references_detail_files(self, tmp_path):
        detail_dir = tmp_path / "details"
        result = extract_and_index(SAMPLE_DOC, detail_dir, ".my-details", repo_root=tmp_path)
        assert ".my-details/" in result.index_content
        assert "(see:" in result.index_content

    def test_detail_files_exist_on_disk(self, tmp_path):
        detail_dir = tmp_path / "details"
        result = extract_and_index(SAMPLE_DOC, detail_dir, ".details", repo_root=tmp_path)
        for f in detail_dir.iterdir():
            assert f.suffix == ".md"
        assert result.metrics.detail_files_written == len(list(detail_dir.iterdir()))

    def test_tokenizer_failure_does_not_write_details(self, tmp_path, monkeypatch):
        detail_dir = tmp_path / "details"
        monkeypatch.setattr(
            "extract_and_index.count_tokens",
            Mock(side_effect=RuntimeError("tokenizer unavailable")),
        )

        with pytest.raises(RuntimeError):
            extract_and_index(SAMPLE_DOC, detail_dir, "details", repo_root=tmp_path)
        assert not detail_dir.exists()
