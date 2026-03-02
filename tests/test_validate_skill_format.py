"""Tests for validate_skill_format.py ADR-017 skill format validation."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_skill_format import SKILL_HEADER_RE, get_files_to_check, main


class TestSkillHeaderRegex:
    def test_matches_valid_header(self) -> None:
        assert SKILL_HEADER_RE.search("## Skill-Testing-001: Always test first")

    def test_does_not_match_invalid_header(self) -> None:
        assert not SKILL_HEADER_RE.search("## Not a skill header")

    def test_rejects_multi_word_domain(self) -> None:
        # Regex [A-Za-z]+ only matches single-word domains, not hyphenated
        assert not SKILL_HEADER_RE.search("## Skill-Agent-Workflow-003: Use handoffs")


class TestGetFilesToCheck:
    def test_returns_empty_for_missing_path(self) -> None:
        result = get_files_to_check("/nonexistent", ci=False, staged_only=False, changed_files=[])
        assert result == []

    def test_filters_index_files(self, tmp_path: Path) -> None:
        (tmp_path / "skills-testing-index.md").write_text("# Index", encoding="utf-8")
        (tmp_path / "memory-index.md").write_text("# Index", encoding="utf-8")
        (tmp_path / "good-skill.md").write_text("# Skill", encoding="utf-8")

        result = get_files_to_check(str(tmp_path), ci=False, staged_only=False, changed_files=[])
        names = [p.name for p in result]
        assert "good-skill.md" in names
        assert "skills-testing-index.md" not in names
        assert "memory-index.md" not in names


class TestMain:
    def test_no_files_returns_0(self) -> None:
        assert main(["--path", "/nonexistent"]) == 0

    def test_clean_files_pass(self, tmp_path: Path) -> None:
        (tmp_path / "testing-001-always-test.md").write_text(
            "# Testing\n\nSingle skill content.",
            encoding="utf-8",
        )
        assert main(["--path", str(tmp_path)]) == 0

    def test_bundled_file_warns_in_local_mode(self, tmp_path: Path) -> None:
        content = (
            "## Skill-Design-001: Use interfaces\nContent.\n\n"
            "## Skill-Design-002: Favor composition\nContent.\n"
        )
        (tmp_path / "bundled.md").write_text(content, encoding="utf-8")
        # Non-CI mode: returns 0 (warning only)
        assert main(["--path", str(tmp_path)]) == 0

    def test_bundled_file_fails_in_ci_mode(self, tmp_path: Path) -> None:
        content = (
            "## Skill-Design-001: Use interfaces\nContent.\n\n"
            "## Skill-Design-002: Favor composition\nContent.\n"
        )
        (tmp_path / "bundled.md").write_text(content, encoding="utf-8")
        assert main(["--path", str(tmp_path), "--ci"]) == 1

    def test_prefix_violation_fails_in_ci(self, tmp_path: Path) -> None:
        (tmp_path / "skill-bad-name.md").write_text("# Content", encoding="utf-8")
        assert main(["--path", str(tmp_path), "--ci"]) == 1
