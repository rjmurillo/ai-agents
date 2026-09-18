"""Tests for complete context-output manifest validation."""

# taste-lint: ignore file-size
# These tests share generated fixtures across one manifest contract.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)

from extract_and_index import Section, check_generated_files, extract_and_index, summarize_section
from test_extract_and_index import SAMPLE_DOC


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestCheckGeneratedFiles:
    def _generate_output(self, tmp_path, content=SAMPLE_DOC):
        detail_dir = tmp_path / "details"
        index_path = tmp_path / "index.md"
        result = extract_and_index(content, detail_dir, ".details", repo_root=tmp_path)
        index_path.write_text(result.index_content, encoding="utf-8")
        return detail_dir, index_path

    def test_accepts_current_generated_output(self, tmp_path):
        detail_dir, index_path = self._generate_output(tmp_path)

        assert (
            check_generated_files(
                SAMPLE_DOC,
                detail_dir,
                index_path,
                ".details",
                repo_root=tmp_path,
            )
            == []
        )

    def test_reports_mismatched_index_reference(self, tmp_path):
        """AC: index references must point to the generated detail files."""
        detail_dir, index_path = self._generate_output(tmp_path)
        index_path.write_text(
            index_path.read_text(encoding="utf-8").replace(
                ".details/architecture.md",
                ".details/missing.md",
            ),
            encoding="utf-8",
        )

        issues = check_generated_files(
            SAMPLE_DOC,
            detail_dir,
            index_path,
            ".details",
            repo_root=tmp_path,
        )

        assert any("reference mismatch" in issue.lower() for issue in issues)

    def test_reports_missing_index(self, tmp_path):
        detail_dir, index_path = self._generate_output(tmp_path)
        index_path.unlink()

        issues = check_generated_files(
            SAMPLE_DOC, detail_dir, index_path, ".details", repo_root=tmp_path
        )

        assert any("missing index file" in issue.lower() for issue in issues)

    def test_reports_missing_detail_directory(self, tmp_path):
        issues = check_generated_files(
            SAMPLE_DOC,
            tmp_path / "missing-details",
            tmp_path / "index.md",
            ".details",
            repo_root=tmp_path,
        )

        assert any("missing detail file" in issue.lower() for issue in issues)

    def test_reports_detail_path_that_is_not_a_directory(self, tmp_path):
        detail_dir = tmp_path / "details"
        detail_dir.write_text("not a directory\n", encoding="utf-8")

        issues = check_generated_files(
            SAMPLE_DOC,
            detail_dir,
            tmp_path / "index.md",
            ".details",
            repo_root=tmp_path,
        )

        assert any("not a directory" in issue.lower() for issue in issues)

    def test_reports_detail_path_that_is_not_a_file(self, tmp_path):
        detail_dir, index_path = self._generate_output(tmp_path)
        detail_file = next(detail_dir.iterdir())
        detail_file.unlink()
        detail_file.mkdir()

        issues = check_generated_files(
            SAMPLE_DOC, detail_dir, index_path, ".details", repo_root=tmp_path
        )

        assert any("not a file" in issue.lower() for issue in issues)

    def test_duplicate_headings_have_matching_references(self, tmp_path):
        content = "# Config\n\nFirst\n\n## Config\n\nSecond"
        detail_dir, index_path = self._generate_output(tmp_path, content)

        issues = check_generated_files(
            content, detail_dir, index_path, ".details", repo_root=tmp_path
        )

        assert issues == []
        index = index_path.read_text(encoding="utf-8")
        assert "(see: .details/config.md)" in index
        assert "(see: .details/config-1.md)" in index

    def test_summarize_skips_table_separator(self):
        section = Section(
            heading="Table", level=2, content="|---|---|\nMeaning.", slug="table"
        )

        assert summarize_section(section) == "Meaning."

    def test_check_does_not_rewrite_generated_files(self, tmp_path):
        detail_dir, index_path = self._generate_output(tmp_path)
        before = {path: path.read_bytes() for path in [index_path, *detail_dir.iterdir()]}

        check_generated_files(SAMPLE_DOC, detail_dir, index_path, ".details", repo_root=tmp_path)

        after = {path: path.read_bytes() for path in [index_path, *detail_dir.iterdir()]}
        assert after == before
