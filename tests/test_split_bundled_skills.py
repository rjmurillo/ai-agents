"""Tests for split_bundled_skills.py skill file splitting."""

from __future__ import annotations

from pathlib import Path

from scripts.split_bundled_skills import main, process_bundled_file


class TestProcessBundledFile:
    def test_no_skills_found(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("# Just a heading\n\nSome content.", encoding="utf-8")
        assert process_bundled_file(f, tmp_path, dry_run=True) == 0

    def test_extracts_single_skill(self, tmp_path: Path) -> None:
        content = (
            "# Skills\n\n"
            "## Skill-Testing-001: Always run tests first\n\n"
            "Some skill content here.\n"
        )
        f = tmp_path / "skills-testing.md"
        f.write_text(content, encoding="utf-8")

        count = process_bundled_file(f, tmp_path, dry_run=False)
        assert count == 1

        output_files = list(tmp_path.glob("testing-001-*.md"))
        assert len(output_files) == 1

    def test_extracts_multiple_skills(self, tmp_path: Path) -> None:
        content = (
            "## Skill-Design-001: Use interfaces\n\nContent 1.\n\n"
            "## Skill-Design-002: Favor composition\n\nContent 2.\n"
        )
        f = tmp_path / "skills-design.md"
        f.write_text(content, encoding="utf-8")

        count = process_bundled_file(f, tmp_path, dry_run=False)
        assert count == 2

    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        content = "## Skill-Qa-001: Test everything\n\nContent.\n"
        f = tmp_path / "skills-qa.md"
        f.write_text(content, encoding="utf-8")

        count = process_bundled_file(f, tmp_path, dry_run=True)
        assert count == 1
        output_files = list(tmp_path.glob("qa-001-*.md"))
        assert len(output_files) == 0


class TestMain:
    def test_handles_missing_bundled_files(self, tmp_path: Path) -> None:
        result = main(["--bundled-files-dir", str(tmp_path), "--dry-run"])
        assert result == 0
