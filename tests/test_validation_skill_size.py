"""Tests for scripts.validation.skill_size module.

Validates SKILL.md files against size limits per Issue #676.
Covers size checking, exception handling, CLI modes, and edge cases.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation.skill_size import (
    SKILL_SIZE_LIMIT,
    SKILL_SIZE_WARNING,
    check_skill_size,
    has_size_exception,
    main,
)

# ---------------------------------------------------------------------------
# has_size_exception
# ---------------------------------------------------------------------------


class TestHasSizeException:
    """Tests for size exception detection in frontmatter."""

    def test_exception_declared(self) -> None:
        content = "---\nname: big-skill\nsize-exception: true\n---\nBody"
        assert has_size_exception(content) is True

    def test_no_exception(self) -> None:
        content = "---\nname: small-skill\n---\nBody"
        assert has_size_exception(content) is False

    def test_exception_false(self) -> None:
        content = "---\nname: skill\nsize-exception: false\n---\nBody"
        assert has_size_exception(content) is False

    def test_no_frontmatter(self) -> None:
        content = "No frontmatter here"
        assert has_size_exception(content) is False

    def test_unclosed_frontmatter(self) -> None:
        content = "---\nname: skill\nsize-exception: true\nNo closing delimiter"
        assert has_size_exception(content) is False


# ---------------------------------------------------------------------------
# check_skill_size
# ---------------------------------------------------------------------------


class TestCheckSkillSize:
    """Tests for individual file size checking."""

    def test_small_file_passes(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "line\n" * 50)

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is False
        assert result.line_count == 53

    def test_warning_threshold(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "line\n" * SKILL_SIZE_WARNING)

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is True

    def test_exceeds_limit(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "line\n" * SKILL_SIZE_LIMIT)

        result = check_skill_size(skill)

        assert result.passed is False
        assert len(result.errors) == 1
        assert "exceeds" in result.errors[0]
        assert "progressive disclosure" in result.errors[0]

    def test_exceeds_limit_with_exception(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\nsize-exception: true\n---\n"
            + "line\n" * SKILL_SIZE_LIMIT
        )

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is True
        assert result.has_exception is True

    def test_empty_file_passes(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("")

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.line_count == 0

    def test_exactly_at_limit(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        lines = SKILL_SIZE_LIMIT - 3  # 3 lines for frontmatter
        skill.write_text("---\nname: test\n---\n" + "line\n" * lines)

        result = check_skill_size(skill)

        assert result.passed is True


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for CLI entry point."""

    def test_no_files_returns_zero(self, tmp_path: Path) -> None:
        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_valid_files_pass(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nSmall skill")

        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_oversized_fails_in_ci(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "line\n" * 600
        )

        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 1

    def test_oversized_passes_locally(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.delenv("CI", raising=False)
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "line\n" * 600
        )

        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_custom_limit(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "line\n" * 150
        )

        exit_code = main(["--path", str(tmp_path), "--ci", "--limit", "100"])
        assert exit_code == 1

    def test_exception_bypasses_failure(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\nsize-exception: true\n---\n" + "line\n" * 600
        )

        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 0
