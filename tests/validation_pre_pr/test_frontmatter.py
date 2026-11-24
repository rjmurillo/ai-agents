"""Frontmatter validation tests for pre-PR architecture checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validation.pre_pr import validate_design_review_frontmatter


class TestValidateDesignReviewFrontmatter:
    """Tests for DESIGN-REVIEW frontmatter validation."""

    def _write_review(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper to create a DESIGN-REVIEW file."""
        review_dir = tmp_path / ".project-toolkit" / "architecture"
        review_dir.mkdir(parents=True, exist_ok=True)
        filepath = review_dir / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_no_directory_returns_true(self, tmp_path: Path) -> None:
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_no_review_files_returns_true(self, tmp_path: Path) -> None:
        (tmp_path / ".project-toolkit" / "architecture").mkdir(parents=True)
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

    def test_blocking_null_does_not_count_as_blocking(self, tmp_path: Path, capsys: Any) -> None:
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
