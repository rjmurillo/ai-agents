"""Tests for SkillForge skill_modularity_audit module.

Validates skill modularity audit logic per Issue #1267.
Covers scoring, recommendations, frontmatter parsing, and CLI modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add SkillForge scripts directory to path for imports
_TEST_DIR = Path(__file__).resolve().parent
_SKILLFORGE_ROOT = _TEST_DIR.parent
_SCRIPT_DIR = _SKILLFORGE_ROOT / "scripts"
_PROJECT_ROOT = _TEST_DIR.parents[3]
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

from frontmatter import has_size_exception  # noqa: E402
from skill_modularity_audit import (  # noqa: E402
    IDEAL_MAX_LINES,
    MAX_H2_SECTIONS,
    SkillAuditResult,
    _count_headings,
    _generate_recommendations,
    _score_modularity,
    audit_all_skills,
    audit_skill,
    main,
)


class TestHasSizeException:
    """Tests for size exception detection in frontmatter."""

    def test_exception_declared(self) -> None:
        content = "---\nname: big-skill\nsize-exception: true\n---\nBody"
        assert has_size_exception(content) is True

    def test_no_exception(self) -> None:
        content = "---\nname: small-skill\n---\nBody"
        assert has_size_exception(content) is False

    def test_no_frontmatter(self) -> None:
        assert has_size_exception("No frontmatter") is False

    def test_unclosed_frontmatter(self) -> None:
        content = "---\nsize-exception: true\nNo closing"
        assert has_size_exception(content) is False


class TestCountHeadings:
    """Tests for heading counting."""

    def test_mixed_headings(self) -> None:
        content = "## One\n### Sub\n## Two\n### Sub2\n### Sub3\n"
        h2, h3 = _count_headings(content)
        assert h2 == 2
        assert h3 == 3

    def test_no_headings(self) -> None:
        h2, h3 = _count_headings("Just plain text")
        assert h2 == 0
        assert h3 == 0

    def test_h1_not_counted(self) -> None:
        content = "# Title\n## Section\n"
        h2, h3 = _count_headings(content)
        assert h2 == 1
        assert h3 == 0


class TestScoreModularity:
    """Tests for modularity scoring algorithm."""

    def test_small_focused_skill(self) -> None:
        score = _score_modularity(100, 5, False, False, False, False)
        assert score == 100

    def test_large_skill_penalized(self) -> None:
        score = _score_modularity(500, 5, False, False, False, False)
        assert score < 100
        assert score == 100 - min((500 - IDEAL_MAX_LINES) // 10, 40)

    def test_many_sections_penalized(self) -> None:
        score = _score_modularity(100, 15, False, False, False, False)
        expected = 100 - (15 - MAX_H2_SECTIONS) * 3
        assert score == expected

    def test_progressive_disclosure_bonus(self) -> None:
        base = _score_modularity(400, 8, False, False, False, False)
        with_scripts = _score_modularity(400, 8, True, False, False, False)
        with_all = _score_modularity(400, 8, True, True, True, True)
        assert with_scripts > base
        assert with_all > with_scripts

    def test_score_clamped_to_0_100(self) -> None:
        # Very large skill with many sections
        score = _score_modularity(1000, 30, False, False, False, False)
        assert score >= 0
        # Small skill with all bonuses
        score = _score_modularity(50, 3, True, True, True, True)
        assert score <= 100


class TestGenerateRecommendations:
    """Tests for recommendation generation."""

    def test_oversized_skill_gets_recommendations(self) -> None:
        result = SkillAuditResult(
            name="big-skill",
            file_path="test",
            line_count=600,
            h2_count=15,
            h3_count=5,
            has_scripts=False,
            has_references=False,
            has_templates=False,
            has_modules=False,
            has_size_exception=False,
            modularity_score=40,
            rating="oversized",
        )
        recs = _generate_recommendations(result)
        assert len(recs) >= 2
        assert any("500-line" in r for r in recs)
        assert any("scripts/" in r for r in recs)

    def test_small_skill_no_recommendations(self) -> None:
        result = SkillAuditResult(
            name="small-skill",
            file_path="test",
            line_count=100,
            h2_count=5,
            h3_count=3,
            has_scripts=True,
            has_references=True,
            has_templates=False,
            has_modules=False,
            has_size_exception=False,
            modularity_score=100,
            rating="good",
        )
        recs = _generate_recommendations(result)
        assert len(recs) == 0

    def test_size_exception_suppresses_oversized_rec(self) -> None:
        result = SkillAuditResult(
            name="excepted",
            file_path="test",
            line_count=600,
            h2_count=8,
            h3_count=3,
            has_scripts=True,
            has_references=True,
            has_templates=False,
            has_modules=False,
            has_size_exception=True,
            modularity_score=60,
            rating="warning",
        )
        recs = _generate_recommendations(result)
        assert not any("500-line" in r for r in recs)


class TestAuditSkill:
    """Tests for single skill audit."""

    def test_audit_small_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "small-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\nname: small-skill\n---\n## Process\nDo the thing.\n")
        result = audit_skill(skill_dir)
        assert result is not None
        assert result.rating == "good"
        assert result.modularity_score == 100

    def test_audit_oversized_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        sections = [f"## Section {i}" for i in range(15)]
        lines = ["---", "name: big-skill", "---"] + sections + ["line"] * 500
        skill_file.write_text("\n".join(lines))
        result = audit_skill(skill_dir)
        assert result is not None
        assert result.rating == "oversized"
        assert len(result.recommendations) > 0

    def test_audit_missing_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()
        assert audit_skill(skill_dir) is None

    def test_audit_with_subdirectories(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "modular-skill"
        skill_dir.mkdir()
        (skill_dir / "scripts").mkdir()
        (skill_dir / "references").mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\nname: modular\n---\n## Process\nSteps.\n")
        result = audit_skill(skill_dir)
        assert result is not None
        assert result.has_scripts is True
        assert result.has_references is True
        assert result.modularity_score >= 100  # bonus applied


class TestAuditAllSkills:
    """Tests for directory-level audit."""

    def test_audit_multiple_skills(self, tmp_path: Path) -> None:
        for name in ("alpha", "beta"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n## P\nContent.\n")
        results = audit_all_skills(tmp_path)
        assert len(results) == 2

    def test_audit_nonexistent_directory(self, tmp_path: Path) -> None:
        results = audit_all_skills(tmp_path / "nonexistent")
        assert results == []


class TestMain:
    """Tests for CLI entry point."""

    def test_main_success(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "ok-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: ok\n---\n## P\nOK.\n")
        assert main(["--path", str(tmp_path)]) == 0

    def test_main_ci_fails_on_oversized(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "huge"
        skill_dir.mkdir()
        lines = ["---", "name: huge", "---"] + ["line"] * 600
        (skill_dir / "SKILL.md").write_text("\n".join(lines))
        assert main(["--path", str(tmp_path), "--ci"]) == 1

    def test_main_json_output(self, tmp_path: Path, capsys: object) -> None:
        skill_dir = tmp_path / "json-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: json-test\n---\n## P\nOK.\n")
        assert main(["--path", str(tmp_path), "--json"]) == 0

    def test_main_missing_path(self) -> None:
        assert main(["--path", "/nonexistent/path"]) == 2

    def test_main_rejects_relative_path_traversal(self) -> None:
        assert main(["--path", "../../../etc"]) == 2

    def test_main_allows_absolute_path(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "abs-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: abs\n---\n## P\nOK.\n")
        assert main(["--path", str(tmp_path)]) == 0
