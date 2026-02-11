"""Tests for scripts.validation.traceability module.

Validates YAML front matter parsing, spec loading, traceability rules,
output formatting, path validation, and CLI behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.traceability import (
    AllSpecs,
    SpecInfo,
    TraceIssue,
    TraceResults,
    build_parser,
    format_console,
    format_json,
    format_markdown,
    load_all_specs,
    main,
    parse_yaml_front_matter,
    validate_traceability,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_spec_file(
    directory: Path,
    filename: str,
    spec_type: str,
    spec_id: str,
    status: str = "draft",
    related: list[str] | None = None,
) -> Path:
    """Create a spec markdown file with YAML front matter."""
    related_lines = ""
    if related:
        items = "\n".join(f"  - {r}" for r in related)
        related_lines = f"\nrelated:\n{items}"

    content = f"""---
type: {spec_type}
id: {spec_id}
status: {status}{related_lines}
---
# {spec_id}
"""
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# parse_yaml_front_matter
# ---------------------------------------------------------------------------


class TestParseYamlFrontMatter:
    """Tests for YAML front matter extraction."""

    def test_valid_front_matter(self, tmp_path: Path) -> None:
        f = _create_spec_file(
            tmp_path, "REQ-001.md", "requirement", "REQ-001",
            related=["DESIGN-001"],
        )
        spec = parse_yaml_front_matter(f)
        assert spec is not None
        assert spec.spec_type == "requirement"
        assert spec.spec_id == "REQ-001"
        assert spec.status == "draft"
        assert "DESIGN-001" in spec.related

    def test_no_front_matter(self, tmp_path: Path) -> None:
        f = tmp_path / "no-yaml.md"
        f.write_text("# Just a heading\nNo YAML here.", encoding="utf-8")
        assert parse_yaml_front_matter(f) is None

    def test_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.md"
        assert parse_yaml_front_matter(f) is None

    def test_multiple_related(self, tmp_path: Path) -> None:
        f = _create_spec_file(
            tmp_path, "DESIGN-001.md", "design", "DESIGN-001",
            related=["REQ-001", "REQ-002"],
        )
        spec = parse_yaml_front_matter(f)
        assert spec is not None
        assert len(spec.related) == 2
        assert "REQ-001" in spec.related
        assert "REQ-002" in spec.related

    def test_no_related_field(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.md"
        f.write_text(
            "---\ntype: requirement\nid: REQ-001\nstatus: draft\n---\n",
            encoding="utf-8",
        )
        spec = parse_yaml_front_matter(f)
        assert spec is not None
        assert spec.related == []

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        assert parse_yaml_front_matter(f) is None


# ---------------------------------------------------------------------------
# load_all_specs
# ---------------------------------------------------------------------------


class TestLoadAllSpecs:
    """Tests for spec loading from directory structure."""

    def test_loads_requirements(self, tmp_path: Path) -> None:
        req_dir = tmp_path / "requirements"
        req_dir.mkdir()
        _create_spec_file(req_dir, "REQ-001.md", "requirement", "REQ-001")

        specs = load_all_specs(tmp_path)
        assert "REQ-001" in specs.requirements
        assert "REQ-001" in specs.all

    def test_loads_designs(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "design"
        design_dir.mkdir()
        _create_spec_file(design_dir, "DESIGN-001.md", "design", "DESIGN-001")

        specs = load_all_specs(tmp_path)
        assert "DESIGN-001" in specs.designs

    def test_loads_tasks(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "tasks"
        task_dir.mkdir()
        _create_spec_file(task_dir, "TASK-001.md", "task", "TASK-001")

        specs = load_all_specs(tmp_path)
        assert "TASK-001" in specs.tasks

    def test_empty_directory(self, tmp_path: Path) -> None:
        specs = load_all_specs(tmp_path)
        assert len(specs.requirements) == 0
        assert len(specs.designs) == 0
        assert len(specs.tasks) == 0

    def test_skips_non_matching_files(self, tmp_path: Path) -> None:
        req_dir = tmp_path / "requirements"
        req_dir.mkdir()
        (req_dir / "README.md").write_text("not a spec", encoding="utf-8")

        specs = load_all_specs(tmp_path)
        assert len(specs.requirements) == 0


# ---------------------------------------------------------------------------
# validate_traceability - full chain
# ---------------------------------------------------------------------------


def _build_complete_chain(tmp_path: Path) -> AllSpecs:
    """Build a complete REQ -> DESIGN -> TASK chain."""
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    design_dir = tmp_path / "design"
    design_dir.mkdir()
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()

    _create_spec_file(req_dir, "REQ-001.md", "requirement", "REQ-001")
    _create_spec_file(
        design_dir, "DESIGN-001.md", "design", "DESIGN-001",
        related=["REQ-001"],
    )
    _create_spec_file(
        task_dir, "TASK-001.md", "task", "TASK-001",
        related=["DESIGN-001"],
    )

    return load_all_specs(tmp_path)


class TestValidateTraceability:
    """Tests for traceability validation rules."""

    def test_complete_chain_passes(self, tmp_path: Path) -> None:
        specs = _build_complete_chain(tmp_path)
        results = validate_traceability(specs)
        assert len(results.errors) == 0
        assert results.valid_chains == 1

    def test_rule1_orphaned_requirement(self) -> None:
        specs = AllSpecs()
        specs.requirements["REQ-001"] = SpecInfo(spec_id="REQ-001")

        results = validate_traceability(specs)
        warnings = [w for w in results.warnings if "Rule 1" in w.rule]
        assert len(warnings) == 1
        assert "orphaned requirement" in warnings[0].message

    def test_rule2_untraced_task(self) -> None:
        specs = AllSpecs()
        specs.tasks["TASK-001"] = SpecInfo(spec_id="TASK-001", related=[])

        results = validate_traceability(specs)
        errors = [e for e in results.errors if "Rule 2" in e.rule]
        assert len(errors) == 1
        assert "untraced task" in errors[0].message

    def test_rule3_design_missing_req(self) -> None:
        specs = AllSpecs()
        specs.designs["DESIGN-001"] = SpecInfo(spec_id="DESIGN-001", related=[])

        results = validate_traceability(specs)
        warnings = [w for w in results.warnings if "Rule 3" in w.rule]
        # Should have both "no REQ reference" and "no TASK referencing"
        assert len(warnings) == 2

    def test_rule4_broken_reference(self) -> None:
        specs = AllSpecs()
        specs.tasks["TASK-001"] = SpecInfo(
            spec_id="TASK-001", related=["DESIGN-999"]
        )

        results = validate_traceability(specs)
        errors = [e for e in results.errors if "Rule 4" in e.rule]
        assert len(errors) == 1
        assert "non-existent DESIGN" in errors[0].message

    def test_rule4_broken_design_to_req(self) -> None:
        specs = AllSpecs()
        specs.designs["DESIGN-001"] = SpecInfo(
            spec_id="DESIGN-001", related=["REQ-999"]
        )

        results = validate_traceability(specs)
        errors = [e for e in results.errors if "Rule 4" in e.rule]
        assert len(errors) == 1
        assert "non-existent REQ" in errors[0].message

    def test_rule5_status_consistency(self) -> None:
        specs = AllSpecs()
        specs.designs["DESIGN-001"] = SpecInfo(
            spec_id="DESIGN-001", status="draft", related=["REQ-001"]
        )
        specs.requirements["REQ-001"] = SpecInfo(spec_id="REQ-001")
        specs.tasks["TASK-001"] = SpecInfo(
            spec_id="TASK-001", status="complete", related=["DESIGN-001"]
        )

        results = validate_traceability(specs)
        info = [i for i in results.info if "Rule 5" in i.rule]
        assert len(info) == 1
        assert "complete but DESIGN" in info[0].message

    def test_stats_populated(self) -> None:
        specs = AllSpecs()
        specs.requirements["REQ-001"] = SpecInfo(spec_id="REQ-001")
        specs.designs["DESIGN-001"] = SpecInfo(spec_id="DESIGN-001")
        specs.tasks["TASK-001"] = SpecInfo(spec_id="TASK-001")

        results = validate_traceability(specs)
        assert results.requirements_count == 1
        assert results.designs_count == 1
        assert results.tasks_count == 1

    def test_empty_specs(self) -> None:
        specs = AllSpecs()
        results = validate_traceability(specs)
        assert len(results.errors) == 0
        assert len(results.warnings) == 0
        assert results.valid_chains == 0


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestFormatConsole:
    """Tests for console output."""

    def test_no_issues(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = TraceResults()
        format_console(results)
        output = capsys.readouterr().out
        assert "All traceability checks passed!" in output

    def test_errors_shown(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = TraceResults()
        results.errors.append(
            TraceIssue(rule="Rule 4", source="T1", target="D999", message="broken")
        )
        format_console(results)
        output = capsys.readouterr().out
        assert "ERRORS (1):" in output

    def test_warnings_shown(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = TraceResults()
        results.warnings.append(
            TraceIssue(rule="Rule 1", source="R1", target=None, message="orphaned")
        )
        format_console(results)
        output = capsys.readouterr().out
        assert "WARNINGS (1):" in output


class TestFormatMarkdown:
    """Tests for markdown output."""

    def test_contains_header(self) -> None:
        results = TraceResults()
        md = format_markdown(results)
        assert "# Traceability Validation Report" in md

    def test_contains_errors(self) -> None:
        results = TraceResults()
        results.errors.append(
            TraceIssue(rule="Rule 4", source="T1", target="D999", message="broken ref")
        )
        md = format_markdown(results)
        assert "## Errors" in md
        assert "broken ref" in md

    def test_summary_table(self) -> None:
        results = TraceResults(requirements_count=3, designs_count=2, tasks_count=5)
        md = format_markdown(results)
        assert "| Requirements | 3 |" in md


class TestFormatJson:
    """Tests for JSON output."""

    def test_valid_json(self) -> None:
        results = TraceResults(requirements_count=1, valid_chains=1)
        output = format_json(results)
        data = json.loads(output)
        assert data["stats"]["requirements"] == 1
        assert data["stats"]["validChains"] == 1

    def test_errors_in_output(self) -> None:
        results = TraceResults()
        results.errors.append(
            TraceIssue(rule="Rule 4", source="T1", target="D1", message="test")
        )
        output = format_json(results)
        data = json.loads(output)
        assert len(data["errors"]) == 1
        assert data["errors"][0]["rule"] == "Rule 4"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_default_specs_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.specs_path == ".agents/specs"

    def test_custom_specs_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--specs-path", "/custom/path"])
        assert args.specs_path == "/custom/path"

    def test_strict_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--strict"])
        assert args.strict is True

    def test_format_choices(self) -> None:
        parser = build_parser()
        for fmt in ["console", "markdown", "json"]:
            args = parser.parse_args(["--format", fmt])
            assert args.output_format == fmt


class TestMain:
    """Integration tests for main entry point."""

    def test_valid_empty_specs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        specs = tmp_path / "specs"
        specs.mkdir()
        result = main(["--specs-path", str(specs)])
        assert result == 0

    def test_complete_chain_passes(self, tmp_path: Path) -> None:
        req_dir = tmp_path / "requirements"
        req_dir.mkdir()
        design_dir = tmp_path / "design"
        design_dir.mkdir()
        task_dir = tmp_path / "tasks"
        task_dir.mkdir()

        _create_spec_file(req_dir, "REQ-001.md", "requirement", "REQ-001")
        _create_spec_file(
            design_dir, "DESIGN-001.md", "design", "DESIGN-001",
            related=["REQ-001"],
        )
        _create_spec_file(
            task_dir, "TASK-001.md", "task", "TASK-001",
            related=["DESIGN-001"],
        )

        result = main(["--specs-path", str(tmp_path)])
        assert result == 0

    def test_errors_return_one(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "tasks"
        task_dir.mkdir()
        _create_spec_file(
            task_dir, "TASK-001.md", "task", "TASK-001",
            related=["DESIGN-999"],
        )

        result = main(["--specs-path", str(tmp_path), "--ci"])
        assert result == 1

    def test_errors_without_ci_return_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        task_dir = tmp_path / "tasks"
        task_dir.mkdir()
        _create_spec_file(
            task_dir, "TASK-001.md", "task", "TASK-001",
            related=["DESIGN-999"],
        )

        result = main(["--specs-path", str(tmp_path)])
        assert result == 0

    def test_warnings_strict_ci_return_one(self, tmp_path: Path) -> None:
        req_dir = tmp_path / "requirements"
        req_dir.mkdir()
        _create_spec_file(req_dir, "REQ-001.md", "requirement", "REQ-001")

        result = main(["--specs-path", str(tmp_path), "--strict", "--ci"])
        assert result == 1

    def test_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        specs = tmp_path / "specs"
        specs.mkdir()
        result = main(["--specs-path", str(specs), "--format", "json"])
        assert result == 0

    def test_nonexistent_path_exits(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--specs-path", "/nonexistent/path/xyz"])
        assert exc_info.value.code == 2
