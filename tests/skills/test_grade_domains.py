"""Tests for quality-grades grade_domains.py script."""

import json
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[2]
_quality_grades = _project_root / ".claude" / "skills" / "quality-grades" / "scripts"
if str(_quality_grades) not in sys.path:
    sys.path.insert(0, str(_quality_grades))

from grade_domains import (
    DomainGrade,
    Gap,
    LayerGrade,
    compute_trend,
    detect_domains,
    format_json,
    format_markdown,
    grade_domain,
    grade_layer,
    load_previous_grades,
    score_to_grade,
)


class TestScoreToGrade:
    """Boundary value tests for score_to_grade."""

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (100, "A"),
            (90, "A"),
            (89, "B"),
            (75, "B"),
            (74, "C"),
            (60, "C"),
            (59, "D"),
            (40, "D"),
            (39, "F"),
            (0, "F"),
        ],
    )
    def test_boundary_values(self, score: int, expected: str) -> None:
        assert score_to_grade(score) == expected


class TestComputeTrend:
    def test_new_domain(self) -> None:
        assert compute_trend(50.0, None) == "new"

    def test_improving(self) -> None:
        assert compute_trend(80.0, 70.0) == "improving"

    def test_degrading(self) -> None:
        assert compute_trend(60.0, 70.0) == "degrading"

    def test_stable(self) -> None:
        assert compute_trend(75.0, 73.0) == "stable"

    def test_stable_exact_boundary(self) -> None:
        assert compute_trend(75.0, 70.0) == "stable"


class TestDetectDomains:
    def test_empty_repo(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        result = detect_domains(tmp_path)
        assert result == []

    def test_detects_agent_files(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.md").write_text("# Security Agent")
        (agents_dir / "qa.md").write_text("# QA Agent")
        (agents_dir / "AGENTS.md").write_text("# Skip me")
        result = detect_domains(tmp_path)
        assert result == ["qa", "security"]

    def test_detects_skill_directories(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: memory\n---")
        result = detect_domains(tmp_path)
        assert result == ["memory"]

    def test_deduplicates_agents_and_skills(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.md").write_text("# Agent")
        skill_dir = tmp_path / ".claude" / "skills" / "security"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: security\n---")
        result = detect_domains(tmp_path)
        assert result == ["security"]


class TestGradeLayer:
    def test_agents_layer_full_score(self, tmp_path: Path) -> None:
        agent_file = tmp_path / ".claude" / "agents" / "test-domain.md"
        agent_file.parent.mkdir(parents=True)
        agent_file.write_text(
            "# Agent\n## Core Identity\n## Style Guide\n## Tools\n## Activation\n"
        )
        result = grade_layer(tmp_path, "test-domain", "agents")
        assert result.score == 100
        assert result.grade == "A"
        assert result.file_count == 1
        assert result.gaps == []

    def test_agents_layer_missing(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        result = grade_layer(tmp_path, "nonexistent", "agents")
        assert result.score == 0
        assert result.grade == "F"
        assert len(result.gaps) == 1
        assert result.gaps[0].severity == "significant"

    def test_skills_layer_with_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\n---\n## Triggers\n## Verification\n"
        )
        result = grade_layer(tmp_path, "my-skill", "skills")
        assert result.score >= 85
        assert result.grade in ("A", "B")

    def test_skills_layer_no_directory(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        result = grade_layer(tmp_path, "missing", "skills")
        assert result.score == 50
        assert len(result.gaps) == 1
        assert result.gaps[0].severity == "minor"

    def test_skills_layer_dir_without_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "broken"
        skill_dir.mkdir(parents=True)
        result = grade_layer(tmp_path, "broken", "skills")
        assert result.score == 20
        assert result.gaps[0].severity == "critical"

    def test_scripts_layer_with_documented_scripts(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / ".claude" / "skills" / "my-domain" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "run.py").write_text('"""Documented script."""\nprint("hi")')
        result = grade_layer(tmp_path, "my-domain", "scripts")
        assert result.score == 100
        assert result.file_count == 1

    def test_scripts_layer_no_scripts(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        result = grade_layer(tmp_path, "empty", "scripts")
        assert result.score == 50

    def test_tests_layer_with_tests(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_my_domain.py").write_text("def test_it(): pass")
        result = grade_layer(tmp_path, "my-domain", "tests")
        assert result.score >= 80
        assert result.file_count >= 1

    def test_tests_layer_no_tests(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        result = grade_layer(tmp_path, "absent", "tests")
        assert result.score == 30
        assert len(result.gaps) == 1

    def test_docs_layer_with_docs(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "security-guide.md").write_text("# Guide")
        result = grade_layer(tmp_path, "security", "docs")
        assert result.score >= 75
        assert result.file_count >= 1

    def test_docs_layer_no_docs(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        result = grade_layer(tmp_path, "absent", "docs")
        assert result.score == 40

    def test_workflows_layer_with_workflows(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "security-scan.yml").write_text("name: scan")
        result = grade_layer(tmp_path, "security", "workflows")
        assert result.score >= 80
        assert result.file_count == 1

    def test_workflows_layer_no_workflows(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        result = grade_layer(tmp_path, "absent", "workflows")
        assert result.score == 50

    def test_score_capped_at_100(self, tmp_path: Path) -> None:
        """Score cannot exceed 100 even with many bonus points."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        for i in range(10):
            (test_dir / f"test_bigdomain_{i}.py").write_text("def test_it(): pass")
        result = grade_layer(tmp_path, "bigdomain", "tests")
        assert result.score <= 100


class TestGradeDomain:
    def test_grades_all_layers(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "agents").mkdir(parents=True)
        result = grade_domain(tmp_path, "test")
        assert len(result.layers) == 6
        layer_names = [lg.layer for lg in result.layers]
        assert layer_names == ["agents", "skills", "scripts", "tests", "docs", "workflows"]

    def test_overall_grade_computed(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir(parents=True)
        result = grade_domain(tmp_path, "empty")
        assert result.overall_grade in ("A", "B", "C", "D", "F")
        assert 0 <= result.overall_score <= 100


class TestDomainGradeProperties:
    def test_no_layers_returns_f(self) -> None:
        dg = DomainGrade(domain="empty")
        assert dg.overall_grade == "F"
        assert dg.overall_score == 0

    def test_computes_average(self) -> None:
        dg = DomainGrade(
            domain="test",
            layers=[
                LayerGrade(layer="a", grade="A", score=90),
                LayerGrade(layer="b", grade="C", score=60),
            ],
        )
        assert dg.overall_score == 75.0
        assert dg.overall_grade == "B"


class TestLoadPreviousGrades:
    def test_file_not_exists(self, tmp_path: Path) -> None:
        result = load_previous_grades(tmp_path / "nonexistent.json")
        assert result is None

    def test_valid_json(self, tmp_path: Path) -> None:
        data = {"domains": [{"domain": "security", "overall_score": 85.0}]}
        path = tmp_path / "grades.json"
        path.write_text(json.dumps(data))
        result = load_previous_grades(path)
        assert result == {"security": 85.0}

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json{{{")
        result = load_previous_grades(path)
        assert result is None

    def test_missing_key(self, tmp_path: Path) -> None:
        path = tmp_path / "partial.json"
        path.write_text(json.dumps({"other": "data"}))
        result = load_previous_grades(path)
        assert result == {}


class TestFormatMarkdown:
    def test_contains_header(self) -> None:
        grades = [
            DomainGrade(
                domain="security",
                layers=[LayerGrade(layer="agents", grade="A", score=90)],
            )
        ]
        output = format_markdown(grades, {"security": "stable"})
        assert "# Quality Grades" in output
        assert "## Domain: security" in output
        assert "(stable)" in output
        assert "| agents | A | 90 |" in output

    def test_summary_section(self) -> None:
        gap = Gap(layer="tests", description="No tests", severity="critical")
        grades = [
            DomainGrade(
                domain="qa",
                layers=[LayerGrade(layer="tests", grade="F", score=30, gaps=[gap])],
            )
        ]
        output = format_markdown(grades, {})
        assert "Total gaps: 1" in output
        assert "Critical gaps: 1" in output


class TestFormatJson:
    def test_valid_json_output(self) -> None:
        grades = [
            DomainGrade(
                domain="memory",
                layers=[LayerGrade(layer="agents", grade="B", score=80)],
            )
        ]
        output = format_json(grades, {"memory": "improving"})
        data = json.loads(output)
        assert data["grading_agent"] == "quality-auditor"
        assert len(data["domains"]) == 1
        assert data["domains"][0]["domain"] == "memory"
        assert data["domains"][0]["trend"] == "improving"
        assert data["domains"][0]["layers"][0]["score"] == 80

    def test_gaps_serialized(self) -> None:
        gap = Gap(layer="tests", description="Missing tests", severity="critical")
        grades = [
            DomainGrade(
                domain="test",
                layers=[LayerGrade(layer="tests", grade="F", score=30, gaps=[gap])],
            )
        ]
        output = format_json(grades, {})
        data = json.loads(output)
        gaps = data["domains"][0]["layers"][0]["gaps"]
        assert len(gaps) == 1
        assert gaps[0]["description"] == "Missing tests"
        assert gaps[0]["severity"] == "critical"
