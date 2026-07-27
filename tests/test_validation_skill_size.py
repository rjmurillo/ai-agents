"""Tests for scripts.validation.skill_size module.

Validates SKILL.md files against size limits per Issue #676.
Covers size checking, exception handling, CLI modes, and edge cases.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation.skill_size import (
    SKILL_BYTE_LIMIT,
    SKILL_BYTE_TARGET,
    SKILL_BYTE_WARNING,
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
# check_skill_size: byte dimension (Issue #3421)
# ---------------------------------------------------------------------------


class TestCheckSkillSizeBytes:
    """Tests for the byte-size dimension, independent of the line dimension."""

    def test_byte_thresholds_are_ordered(self) -> None:
        # The ratchet invariant: warn < documented target <= enforced ceiling.
        assert SKILL_BYTE_WARNING < SKILL_BYTE_TARGET
        assert SKILL_BYTE_TARGET <= SKILL_BYTE_LIMIT

    def test_small_file_no_byte_warning(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\nSmall body", encoding="utf-8")

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is False
        assert result.byte_count == len(skill.read_bytes())

    def test_byte_warning_threshold(self, tmp_path: Path) -> None:
        # Over the 12 KiB soft ceiling but under the enforced limit and under
        # the 500-line limit: warns on bytes alone.
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\n---\n" + ("x" * 200 + "\n") * 70, encoding="utf-8"
        )

        result = check_skill_size(skill)

        assert result.byte_count > SKILL_BYTE_WARNING
        assert result.byte_count <= SKILL_BYTE_LIMIT
        assert result.line_count <= SKILL_SIZE_LIMIT
        assert result.passed is True
        assert result.warning is True

    def test_exceeds_byte_limit_under_line_limit(self, tmp_path: Path) -> None:
        # The case the line check misses: a table-heavy body sits well under
        # 500 lines yet blows the byte ceiling. It must FAIL on bytes.
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\n---\n" + ("x" * 600 + "\n") * 50, encoding="utf-8"
        )

        result = check_skill_size(skill)

        assert result.line_count <= SKILL_SIZE_LIMIT
        assert result.byte_count > SKILL_BYTE_LIMIT
        assert result.passed is False
        assert len(result.errors) == 1
        assert "bytes" in result.errors[0]
        assert "progressive disclosure" in result.errors[0]

    def test_exceeds_byte_limit_with_exception(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\nname: test\nsize-exception: true\n---\n" + ("x" * 600 + "\n") * 50,
            encoding="utf-8",
        )

        result = check_skill_size(skill)

        assert result.passed is True
        assert result.warning is True
        assert result.has_exception is True

    def test_byte_count_is_raw_bytes_not_chars(self, tmp_path: Path) -> None:
        # Multi-byte UTF-8 must count as raw bytes (matching `wc -c`), not code
        # points, so the measure cannot be dodged with wide characters.
        skill = tmp_path / "SKILL.md"
        body = "---\nname: test\n---\n" + "é" * 100  # 'é' is 2 bytes in UTF-8
        skill.write_text(body, encoding="utf-8")

        result = check_skill_size(skill)

        assert result.byte_count == len(body.encode("utf-8"))
        assert result.byte_count > len(body)

    def test_custom_byte_limit_triggers_failure(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\n" + "x" * 500, encoding="utf-8")

        result = check_skill_size(skill, byte_limit=100, byte_warn=50)

        assert result.passed is False
        assert any("bytes" in e for e in result.errors)




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

    def test_custom_byte_limit_fails_in_ci(self, tmp_path: Path) -> None:
        # A body that is fine on lines but over a tightened byte limit fails CI.
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\n---\n" + "x" * 500, encoding="utf-8"
        )

        exit_code = main(
            ["--path", str(tmp_path), "--ci", "--byte-limit", "100", "--byte-warn", "50"]
        )
        assert exit_code == 1

    def test_byte_exception_bypasses_failure_in_ci(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\nsize-exception: true\n---\n" + "x" * 500,
            encoding="utf-8",
        )

        exit_code = main(
            ["--path", str(tmp_path), "--ci", "--byte-limit", "100", "--byte-warn", "50"]
        )
        assert exit_code == 0
