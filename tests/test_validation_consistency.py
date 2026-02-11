"""Tests for scripts.validation.consistency module.

Validates naming conventions, scope alignment, requirement coverage,
cross-references, task completion, and output formatting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.consistency import (
    FeatureArtifacts,
    ValidationResult,
    build_parser,
    check_cross_references,
    check_naming_convention,
    check_naming_conventions,
    check_requirement_coverage,
    check_scope_alignment,
    check_task_completion,
    find_feature_artifacts,
    format_console_output,
    format_json_output,
    format_markdown_output,
    get_all_features,
    main,
    validate_feature,
)

# ---------------------------------------------------------------------------
# Naming convention checks
# ---------------------------------------------------------------------------


class TestCheckNamingConvention:
    """Tests for file naming validation."""

    def test_valid_epic(self, tmp_path: Path) -> None:
        f = tmp_path / "EPIC-001-auth.md"
        assert check_naming_convention(f, "epic") is True

    def test_invalid_epic_lowercase(self, tmp_path: Path) -> None:
        f = tmp_path / "epic-001-auth.md"
        assert check_naming_convention(f, "epic") is False

    def test_valid_prd(self, tmp_path: Path) -> None:
        f = tmp_path / "prd-user-auth.md"
        assert check_naming_convention(f, "prd") is True

    def test_invalid_prd_uppercase(self, tmp_path: Path) -> None:
        f = tmp_path / "PRD-user-auth.md"
        assert check_naming_convention(f, "prd") is False

    def test_valid_tasks(self, tmp_path: Path) -> None:
        f = tmp_path / "tasks-user-auth.md"
        assert check_naming_convention(f, "tasks") is True

    def test_valid_adr(self, tmp_path: Path) -> None:
        f = tmp_path / "ADR-042-python-first.md"
        assert check_naming_convention(f, "adr") is True

    def test_unknown_pattern_returns_true(self, tmp_path: Path) -> None:
        f = tmp_path / "anything.md"
        assert check_naming_convention(f, "unknown") is True


# ---------------------------------------------------------------------------
# Feature artifact discovery
# ---------------------------------------------------------------------------


class TestFindFeatureArtifacts:
    """Tests for artifact discovery."""

    def test_finds_prd(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        prd = planning / "prd-auth.md"
        prd.write_text("# PRD", encoding="utf-8")

        artifacts = find_feature_artifacts("auth", tmp_path)
        assert artifacts.prd == prd

    def test_finds_tasks(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        tasks = planning / "tasks-auth.md"
        tasks.write_text("# Tasks", encoding="utf-8")

        artifacts = find_feature_artifacts("auth", tmp_path)
        assert artifacts.tasks == tasks

    def test_finds_epic(self, tmp_path: Path) -> None:
        roadmap = tmp_path / ".agents" / "roadmap"
        roadmap.mkdir(parents=True)
        epic = roadmap / "EPIC-001-auth.md"
        epic.write_text("# Epic", encoding="utf-8")

        artifacts = find_feature_artifacts("auth", tmp_path)
        assert artifacts.epic == epic

    def test_missing_directories(self, tmp_path: Path) -> None:
        artifacts = find_feature_artifacts("auth", tmp_path)
        assert artifacts.epic is None
        assert artifacts.prd is None
        assert artifacts.tasks is None
        assert artifacts.plan is None


# ---------------------------------------------------------------------------
# Get all features
# ---------------------------------------------------------------------------


class TestGetAllFeatures:
    """Tests for feature discovery."""

    def test_discovers_from_prds(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "prd-auth.md").write_text("# Auth", encoding="utf-8")
        (planning / "prd-payments.md").write_text("# Payments", encoding="utf-8")

        features = get_all_features(tmp_path)
        assert "auth" in features
        assert "payments" in features

    def test_discovers_from_tasks(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "tasks-search.md").write_text("# Search", encoding="utf-8")

        features = get_all_features(tmp_path)
        assert "search" in features

    def test_deduplicates(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        (planning / "prd-auth.md").write_text("# PRD", encoding="utf-8")
        (planning / "tasks-auth.md").write_text("# Tasks", encoding="utf-8")

        features = get_all_features(tmp_path)
        assert features.count("auth") == 1

    def test_empty_when_no_planning_dir(self, tmp_path: Path) -> None:
        assert get_all_features(tmp_path) == []


# ---------------------------------------------------------------------------
# Scope alignment
# ---------------------------------------------------------------------------


class TestCheckScopeAlignment:
    """Tests for scope alignment between Epic and PRD."""

    def test_missing_epic_is_not_failure(self, tmp_path: Path) -> None:
        result = check_scope_alignment(None, None)
        assert result.passed is True
        assert "Epic file not found" in result.issues

    def test_missing_prd_is_failure(self, tmp_path: Path) -> None:
        epic = tmp_path / "EPIC-001.md"
        epic.write_text("# Epic", encoding="utf-8")

        result = check_scope_alignment(epic, None)
        assert result.passed is False

    def test_prd_references_epic(self, tmp_path: Path) -> None:
        epic = tmp_path / "EPIC-001-auth.md"
        epic.write_text("### Success Criteria\n- [x] item", encoding="utf-8")
        prd = tmp_path / "prd-auth.md"
        prd.write_text("Ref: EPIC-001\n## Requirements\n- [x] req1", encoding="utf-8")

        result = check_scope_alignment(epic, prd)
        assert result.passed is True

    def test_prd_fewer_requirements_than_criteria(self, tmp_path: Path) -> None:
        epic = tmp_path / "EPIC-001-auth.md"
        epic.write_text(
            "### Success Criteria\n- [x] c1\n- [ ] c2\n- [ ] c3",
            encoding="utf-8",
        )
        prd = tmp_path / "prd-auth.md"
        prd.write_text(
            "Ref: EPIC-001\n## Requirements\n- [x] r1",
            encoding="utf-8",
        )

        result = check_scope_alignment(epic, prd)
        assert any("fewer requirements" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Requirement coverage
# ---------------------------------------------------------------------------


class TestCheckRequirementCoverage:
    """Tests for requirement-to-task coverage."""

    def test_skip_when_no_prd(self) -> None:
        result = check_requirement_coverage(None, None)
        assert result.passed is True

    def test_missing_tasks_file(self, tmp_path: Path) -> None:
        prd = tmp_path / "prd.md"
        prd.write_text("- [x] req1", encoding="utf-8")

        result = check_requirement_coverage(prd, None)
        assert result.passed is False

    def test_sufficient_tasks(self, tmp_path: Path) -> None:
        prd = tmp_path / "prd.md"
        prd.write_text("- [x] req1\n- [ ] req2", encoding="utf-8")
        tasks = tmp_path / "tasks.md"
        tasks.write_text("- [x] task1\n- [ ] task2\n- [ ] task3", encoding="utf-8")

        result = check_requirement_coverage(prd, tasks)
        assert result.passed is True

    def test_fewer_tasks_than_requirements(self, tmp_path: Path) -> None:
        prd = tmp_path / "prd.md"
        prd.write_text("- [x] req1\n- [ ] req2\n- [ ] req3", encoding="utf-8")
        tasks = tmp_path / "tasks.md"
        tasks.write_text("- [x] task1", encoding="utf-8")

        result = check_requirement_coverage(prd, tasks)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Cross-references
# ---------------------------------------------------------------------------


class TestCheckCrossReferences:
    """Tests for cross-reference validation."""

    def test_skip_when_no_file(self) -> None:
        result = check_cross_references(None, Path("."))
        assert result.passed is True

    def test_valid_references(self, tmp_path: Path) -> None:
        target = tmp_path / "target.md"
        target.write_text("# Target", encoding="utf-8")
        source = tmp_path / "source.md"
        source.write_text("[link](target.md)", encoding="utf-8")

        result = check_cross_references(source, tmp_path)
        assert result.passed is True

    def test_broken_reference(self, tmp_path: Path) -> None:
        source = tmp_path / "source.md"
        source.write_text("[link](nonexistent.md)", encoding="utf-8")

        result = check_cross_references(source, tmp_path)
        assert result.passed is False
        assert any("Broken reference" in i for i in result.issues)

    def test_urls_skipped(self, tmp_path: Path) -> None:
        source = tmp_path / "source.md"
        source.write_text("[link](https://example.com)", encoding="utf-8")

        result = check_cross_references(source, tmp_path)
        assert result.passed is True

    def test_anchors_skipped(self, tmp_path: Path) -> None:
        source = tmp_path / "source.md"
        source.write_text("[link](#heading)", encoding="utf-8")

        result = check_cross_references(source, tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Task completion
# ---------------------------------------------------------------------------


class TestCheckTaskCompletion:
    """Tests for task completion validation (Checkpoint 2)."""

    def test_skip_when_no_file(self) -> None:
        result = check_task_completion(None)
        assert result.passed is True

    def test_all_p0_complete(self, tmp_path: Path) -> None:
        tasks = tmp_path / "tasks.md"
        tasks.write_text(
            "### P0\n- [x] critical task 1\n- [x] critical task 2",
            encoding="utf-8",
        )

        result = check_task_completion(tasks)
        assert result.passed is True

    def test_incomplete_p0_fails(self, tmp_path: Path) -> None:
        tasks = tmp_path / "tasks.md"
        tasks.write_text(
            "### P0\n- [x] done task\n- [ ] incomplete task",
            encoding="utf-8",
        )

        result = check_task_completion(tasks)
        assert result.passed is False
        assert any("P0 tasks incomplete" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Naming conventions (aggregate)
# ---------------------------------------------------------------------------


class TestCheckNamingConventions:
    """Tests for aggregate naming convention checks."""

    def test_all_valid(self, tmp_path: Path) -> None:
        epic = tmp_path / "EPIC-001-auth.md"
        epic.write_text("", encoding="utf-8")
        prd = tmp_path / "prd-auth.md"
        prd.write_text("", encoding="utf-8")

        artifacts = FeatureArtifacts(epic=epic, prd=prd)
        result = check_naming_conventions(artifacts)
        assert result.passed is True

    def test_invalid_naming(self, tmp_path: Path) -> None:
        bad_epic = tmp_path / "epic-lowercase.md"
        bad_epic.write_text("", encoding="utf-8")

        artifacts = FeatureArtifacts(epic=bad_epic)
        result = check_naming_conventions(artifacts)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Feature validation
# ---------------------------------------------------------------------------


class TestValidateFeature:
    """Tests for full feature validation."""

    def test_no_artifacts_found(self, tmp_path: Path) -> None:
        result = validate_feature("nonexistent", tmp_path, checkpoint=1)
        assert result.feature == "nonexistent"

    def test_checkpoint_2_includes_task_completion(self, tmp_path: Path) -> None:
        planning = tmp_path / ".agents" / "planning"
        planning.mkdir(parents=True)
        tasks = planning / "tasks-auth.md"
        tasks.write_text("### P0\n- [ ] incomplete", encoding="utf-8")

        result = validate_feature("auth", tmp_path, checkpoint=2)
        assert "TaskCompletion" in result.results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestFormatConsoleOutput:
    """Tests for console output formatting."""

    def test_returns_zero_on_pass(self) -> None:
        v = ValidationResult(feature="test", passed=True)
        fail_count = format_console_output([v])
        assert fail_count == 0

    def test_returns_count_on_failures(self) -> None:
        v = ValidationResult(feature="test", passed=False)
        fail_count = format_console_output([v])
        assert fail_count == 1


class TestFormatMarkdownOutput:
    """Tests for markdown output formatting."""

    def test_contains_header(self) -> None:
        v = ValidationResult(feature="test", passed=True)
        md = format_markdown_output([v], checkpoint=1)
        assert "# Consistency Validation Report" in md

    def test_contains_feature(self) -> None:
        v = ValidationResult(feature="auth", passed=True)
        md = format_markdown_output([v], checkpoint=1)
        assert "auth" in md


class TestFormatJsonOutput:
    """Tests for JSON output formatting."""

    def test_valid_json(self) -> None:
        import json

        v = ValidationResult(feature="test", passed=True)
        output = format_json_output([v], checkpoint=1)
        data = json.loads(output)
        assert data["summary"]["total"] == 1
        assert data["summary"]["passed"] == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_feature_argument(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--feature", "auth"])
        assert args.feature == "auth"

    def test_all_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--all"])
        assert args.validate_all is True

    def test_checkpoint_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--feature", "test"])
        assert args.checkpoint == 1

    def test_format_choices(self) -> None:
        parser = build_parser()
        for fmt in ["console", "markdown", "json"]:
            args = parser.parse_args(["--feature", "test", "--format", fmt])
            assert args.output_format == fmt


class TestMain:
    """Integration tests for main entry point."""

    def test_feature_with_no_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main(["--feature", "nonexistent", "--path", str(tmp_path)])
        assert result == 0

    def test_all_with_no_features(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main(["--all", "--path", str(tmp_path)])
        assert result == 0

    def test_json_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main([
            "--feature", "test",
            "--path", str(tmp_path),
            "--format", "json",
        ])
        assert result == 0

    def test_markdown_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main([
            "--feature", "test",
            "--path", str(tmp_path),
            "--format", "markdown",
        ])
        assert result == 0

    def test_invalid_path_returns_two(self, tmp_path: Path) -> None:
        result = main([
            "--feature", "test",
            "--path", str(tmp_path / "nonexistent"),
        ])
        assert result == 2
