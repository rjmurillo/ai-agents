"""Tests for pre-mortem risk inventory validator script.

These tests verify the pre-mortem risk inventory validation functionality
used by the pre-mortem skill to validate risk inventory documents.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Import from the skill scripts location
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / ".claude" / "skills" / "pre-mortem" / "scripts")
)

from importlib import import_module

pre_mortem = import_module("pre-mortem")

Risk = pre_mortem.Risk
ValidationResult = pre_mortem.ValidationResult
parse_risk_entry = pre_mortem.parse_risk_entry
validate_inventory = pre_mortem.validate_inventory
print_result = pre_mortem.print_result
REQUIRED_SECTIONS = pre_mortem.REQUIRED_SECTIONS
VALID_CATEGORIES = pre_mortem.VALID_CATEGORIES
VALID_STATUSES = pre_mortem.VALID_STATUSES

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


class TestRiskDataclass:
    """Tests for Risk dataclass."""

    def test_creates_risk_with_required_fields(self) -> None:
        """Creates Risk with all required fields."""
        risk = Risk(
            id="R001",
            name="Test Risk",
            category="Technical",
            likelihood=3,
            impact=4,
            score=12,
            has_mitigation=True,
        )

        assert risk.id == "R001"
        assert risk.name == "Test Risk"
        assert risk.category == "Technical"
        assert risk.likelihood == 3
        assert risk.impact == 4
        assert risk.score == 12
        assert risk.has_mitigation is True
        assert risk.owner is None
        assert risk.status is None

    def test_creates_risk_with_optional_fields(self) -> None:
        """Creates Risk with optional owner and status."""
        risk = Risk(
            id="R002",
            name="Risk with Owner",
            category="Process",
            likelihood=2,
            impact=3,
            score=6,
            has_mitigation=False,
            owner="John Doe",
            status="Open",
        )

        assert risk.owner == "John Doe"
        assert risk.status == "Open"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_is_valid(self) -> None:
        """Empty result is valid by default."""
        result = ValidationResult(valid=True)

        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.statistics == {}

    def test_add_error_marks_invalid(self) -> None:
        """add_error marks result as invalid."""
        result = ValidationResult(valid=True)

        result.add_error("Test error")

        assert result.valid is False
        assert "Test error" in result.errors

    def test_add_warning_keeps_valid(self) -> None:
        """add_warning does not mark result as invalid."""
        result = ValidationResult(valid=True)

        result.add_warning("Test warning")

        assert result.valid is True
        assert "Test warning" in result.warnings

    def test_multiple_errors_accumulated(self) -> None:
        """Multiple errors are accumulated."""
        result = ValidationResult(valid=True)

        result.add_error("Error 1")
        result.add_error("Error 2")
        result.add_error("Error 3")

        assert len(result.errors) == 3
        assert result.valid is False


class TestConstants:
    """Tests for module constants."""

    def test_required_sections(self) -> None:
        """REQUIRED_SECTIONS contains expected values."""
        expected = [
            "Project Context",
            "Risk Summary",
            "Critical Risks",
            "High Risks",
            "Medium Risks",
            "Low Risks",
            "Action Items",
        ]
        assert REQUIRED_SECTIONS == expected

    def test_valid_categories(self) -> None:
        """VALID_CATEGORIES contains expected values."""
        expected = [
            "Technical",
            "People",
            "Process",
            "Organizational",
            "External",
            "Unknown",
        ]
        assert VALID_CATEGORIES == expected

    def test_valid_statuses(self) -> None:
        """VALID_STATUSES contains expected values."""
        expected = ["Open", "Mitigating", "Accepted", "Resolved"]
        assert VALID_STATUSES == expected


class TestParseRiskEntry:
    """Tests for parse_risk_entry function."""

    def test_parses_complete_risk(self) -> None:
        """Parses complete risk entry with all fields."""
        text = """### R001: Database Migration Failure
**Category:** Technical
**Likelihood:** 4
**Impact:** 5
**Score:** 20
**Owner:** Jane Smith
**Status:** Open
**Mitigation:** Use rollback strategy
"""
        risk = parse_risk_entry(text)

        assert risk is not None
        assert risk.id == "R001"
        assert risk.name == "Database Migration Failure"
        assert risk.category == "Technical"
        assert risk.likelihood == 4
        assert risk.impact == 5
        assert risk.score == 20
        assert risk.owner == "Jane Smith"
        assert risk.status == "Open"
        assert risk.has_mitigation is True

    def test_parses_minimal_risk(self) -> None:
        """Parses risk with only required fields."""
        text = """### R002: Simple Risk
**Category:** Process
**Likelihood:** 2
**Impact:** 3
"""
        risk = parse_risk_entry(text)

        assert risk is not None
        assert risk.id == "R002"
        assert risk.name == "Simple Risk"
        assert risk.category == "Process"
        assert risk.likelihood == 2
        assert risk.impact == 3
        assert risk.score == 6  # Calculated: 2 * 3
        assert risk.has_mitigation is False
        assert risk.owner is None
        assert risk.status is None

    def test_returns_none_for_no_header(self) -> None:
        """Returns None when no risk header found."""
        text = """Some random text
Without risk header
"""
        risk = parse_risk_entry(text)

        assert risk is None

    def test_handles_prevention_as_mitigation(self) -> None:
        """Recognizes Prevention as mitigation indicator."""
        text = """### R003: Preventable Risk
**Category:** People
**Likelihood:** 3
**Impact:** 2
**Prevention:** Train team members
"""
        risk = parse_risk_entry(text)

        assert risk is not None
        assert risk.has_mitigation is True

    def test_defaults_category_to_unknown(self) -> None:
        """Defaults category to Unknown when missing."""
        text = """### R004: No Category Risk
**Likelihood:** 2
**Impact:** 2
"""
        risk = parse_risk_entry(text)

        assert risk is not None
        assert risk.category == "Unknown"

    def test_defaults_values_to_zero_when_missing(self) -> None:
        """Defaults likelihood and impact to 0 when missing."""
        text = """### R005: Missing Values
"""
        risk = parse_risk_entry(text)

        assert risk is not None
        assert risk.likelihood == 0
        assert risk.impact == 0
        assert risk.score == 0


class TestValidateInventory:
    """Tests for validate_inventory function."""

    @pytest.fixture
    def valid_inventory(self) -> str:
        """Create a valid minimal inventory document."""
        return """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
This is the project context.

## Risk Summary
Summary of risks.

## Critical Risks

### R001: Critical Risk
**Category:** Technical
**Likelihood:** 5
**Impact:** 4
**Score:** 20
**Mitigation:** Have backup plan

## High Risks
No high risks.

## Medium Risks
No medium risks.

## Low Risks
No low risks.

## Action Items

| ID | Action | Owner | Due |
|-----|--------|-------|-----|
| A001 | Review risks | Team | Next week |
"""

    def test_validates_complete_inventory(self, valid_inventory: str) -> None:
        """Valid inventory passes validation."""
        result = validate_inventory(valid_inventory)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_detects_missing_section(self) -> None:
        """Detects missing required section."""
        content = """# Risk Inventory

**Project:** Test Project

## Project Context
Context here.

## Risk Summary
Summary here.

## Critical Risks
None.

## High Risks
None.

## Low Risks
None.
"""
        # Missing Medium Risks and Action Items
        result = validate_inventory(content)

        assert result.valid is False
        assert any("Medium Risks" in e for e in result.errors)
        assert any("Action Items" in e for e in result.errors)

    def test_detects_missing_project_context_fields(self) -> None:
        """Detects missing project name or objective."""
        content = """# Risk Inventory

## Project Context
Context without project name.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        assert result.valid is False
        assert any("Project context missing" in e for e in result.errors)

    def test_warns_missing_date(self) -> None:
        """Warns when date field is missing."""
        content = """# Risk Inventory

**Project:** Test Project

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        # Valid but with warning
        assert any("Missing date" in w for w in result.warnings)

    def test_detects_high_risk_without_mitigation(self) -> None:
        """Detects high-priority risk without mitigation plan."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks

### R001: Critical Risk No Mitigation
**Category:** Technical
**Likelihood:** 5
**Impact:** 5
**Score:** 25

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items

| ID | Action |
|-----|--------|
| A001 | Something |
"""
        result = validate_inventory(content)

        assert result.valid is False
        assert any("missing mitigation" in e for e in result.errors)

    def test_detects_invalid_likelihood(self) -> None:
        """Detects likelihood outside valid range."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks

### R001: Invalid Likelihood
**Category:** Technical
**Likelihood:** 7
**Impact:** 3
**Mitigation:** Something

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        assert result.valid is False
        assert any("invalid likelihood" in e for e in result.errors)

    def test_detects_invalid_impact(self) -> None:
        """Detects impact outside valid range."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks

### R001: Invalid Impact
**Category:** Technical
**Likelihood:** 3
**Impact:** 0
**Mitigation:** Something

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        assert result.valid is False
        assert any("invalid impact" in e for e in result.errors)

    def test_warns_score_mismatch(self) -> None:
        """Warns when score does not match likelihood * impact."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks

### R001: Score Mismatch
**Category:** Technical
**Likelihood:** 3
**Impact:** 2
**Score:** 10
**Mitigation:** Something

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        # Should have warning but still valid
        assert any("score mismatch" in w for w in result.warnings)

    def test_calculates_statistics(self, valid_inventory: str) -> None:
        """Calculates risk statistics correctly."""
        result = validate_inventory(valid_inventory)

        assert "total_risks" in result.statistics
        assert "critical_count" in result.statistics
        assert "high_count" in result.statistics
        assert "medium_count" in result.statistics
        assert "low_count" in result.statistics
        assert "average_score" in result.statistics
        assert "risks_with_mitigation" in result.statistics
        assert "risks_with_owner" in result.statistics

    def test_warns_no_action_items_for_high_risks(self) -> None:
        """Warns when high-priority risks exist but no action items."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks

### R001: High Risk
**Category:** Technical
**Likelihood:** 4
**Impact:** 3
**Score:** 12
**Mitigation:** Do something

## Medium Risks
None.

## Low Risks
None.

## Action Items
None defined yet.
"""
        result = validate_inventory(content)

        assert any("No action items" in w for w in result.warnings)

    def test_handles_empty_inventory(self) -> None:
        """Handles empty inventory document."""
        result = validate_inventory("")

        assert result.valid is False
        assert len(result.errors) > 0

    def test_handles_multiple_risks(self) -> None:
        """Handles multiple risk entries correctly."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks

### R001: Critical Risk 1
**Category:** Technical
**Likelihood:** 5
**Impact:** 4
**Score:** 20
**Mitigation:** Plan A

### R002: Critical Risk 2
**Category:** Process
**Likelihood:** 4
**Impact:** 4
**Score:** 16
**Mitigation:** Plan B

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items

| ID | Action |
|-----|--------|
| A001 | Action 1 |
"""
        result = validate_inventory(content)

        assert result.valid is True
        assert result.statistics["total_risks"] == 2
        assert result.statistics["critical_count"] == 2


class TestPrintResult:
    """Tests for print_result function."""

    def test_prints_valid_result(self, capsys: CaptureFixture[str]) -> None:
        """Prints valid result with VALID status."""
        result = ValidationResult(valid=True)
        result.statistics = {
            "total_risks": 5,
            "critical_count": 1,
            "high_count": 2,
            "medium_count": 1,
            "low_count": 1,
            "average_score": 8.0,
            "risks_with_mitigation": 4,
            "risks_with_owner": 3,
        }

        print_result(result)

        captured = capsys.readouterr()
        assert "VALID" in captured.out
        assert "Total Risks: 5" in captured.out
        assert "Average Score: 8.0" in captured.out

    def test_prints_invalid_result_with_errors(
        self, capsys: CaptureFixture[str]
    ) -> None:
        """Prints invalid result with error list."""
        result = ValidationResult(valid=False)
        result.errors = ["Error 1", "Error 2"]
        result.statistics = {}

        print_result(result)

        captured = capsys.readouterr()
        assert "INVALID" in captured.out
        assert "[ERROR]" in captured.out
        assert "Error 1" in captured.out
        assert "Error 2" in captured.out

    def test_prints_warnings(self, capsys: CaptureFixture[str]) -> None:
        """Prints warnings in output."""
        result = ValidationResult(valid=True)
        result.warnings = ["Warning 1"]
        result.statistics = {}

        print_result(result)

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "Warning 1" in captured.out


class TestMainFunction:
    """Tests for main() function."""

    @pytest.fixture
    def valid_inventory_file(self, tmp_path: Path) -> Path:
        """Create a valid inventory file."""
        content = """# Risk Inventory

**Project:** Test Project
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        inventory_file = tmp_path / "inventory.md"
        inventory_file.write_text(content)
        return inventory_file

    @pytest.fixture
    def invalid_inventory_file(self, tmp_path: Path) -> Path:
        """Create an invalid inventory file."""
        content = """# Incomplete Inventory
Missing all required sections.
"""
        inventory_file = tmp_path / "invalid.md"
        inventory_file.write_text(content)
        return inventory_file

    def test_main_valid_inventory(
        self,
        valid_inventory_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 0 for valid inventory."""
        monkeypatch.setattr(
            "sys.argv",
            ["pre-mortem.py", "--inventory-path", str(valid_inventory_file)],
        )

        result = pre_mortem.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "VALID" in captured.out

    def test_main_invalid_inventory(
        self,
        invalid_inventory_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 10 for invalid inventory."""
        monkeypatch.setattr(
            "sys.argv",
            ["pre-mortem.py", "--inventory-path", str(invalid_inventory_file)],
        )

        result = pre_mortem.main()

        assert result == 10
        captured = capsys.readouterr()
        assert "INVALID" in captured.out

    def test_main_missing_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 1 for missing file."""
        nonexistent = tmp_path / "nonexistent.md"
        monkeypatch.setattr(
            "sys.argv",
            ["pre-mortem.py", "--inventory-path", str(nonexistent)],
        )

        result = pre_mortem.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err or "not found" in captured.err

    def test_main_quiet_mode(
        self,
        valid_inventory_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with --quiet suppresses output."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "pre-mortem.py",
                "--inventory-path",
                str(valid_inventory_file),
                "--quiet",
            ],
        )

        result = pre_mortem.main()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_main_json_output(
        self,
        valid_inventory_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with --json outputs JSON format."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "pre-mortem.py",
                "--inventory-path",
                str(valid_inventory_file),
                "--json",
            ],
        )

        result = pre_mortem.main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "valid" in output
        assert "errors" in output
        assert "warnings" in output
        assert "statistics" in output
        assert output["valid"] is True


class TestScriptIntegration:
    """Integration tests for the script as a CLI tool."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the script."""
        return (
            project_root
            / ".claude"
            / "skills"
            / "pre-mortem"
            / "scripts"
            / "pre-mortem.py"
        )

    @pytest.fixture
    def valid_inventory_file(self, tmp_path: Path) -> Path:
        """Create a valid inventory file for integration tests."""
        content = """# Risk Inventory

**Project:** Integration Test
**Date:** 2026-01-18

## Project Context
Test context.

## Risk Summary
Test summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        inventory_file = tmp_path / "test-inventory.md"
        inventory_file.write_text(content)
        return inventory_file

    def test_help_flag(self, script_path: Path) -> None:
        """--help flag shows usage information."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "--inventory-path" in result.stdout
        assert "--quiet" in result.stdout
        assert "--json" in result.stdout

    def test_missing_required_argument(self, script_path: Path) -> None:
        """Missing --inventory-path returns error."""
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "inventory-path" in result.stderr

    def test_validates_file(
        self, script_path: Path, valid_inventory_file: Path
    ) -> None:
        """Script validates inventory file successfully."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--inventory-path",
                str(valid_inventory_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "VALID" in result.stdout

    def test_json_output_integration(
        self, script_path: Path, valid_inventory_file: Path
    ) -> None:
        """Script produces valid JSON output with --json flag."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--inventory-path",
                str(valid_inventory_file),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["valid"] is True

    def test_exit_code_10_for_invalid(self, script_path: Path, tmp_path: Path) -> None:
        """Script returns exit code 10 for invalid inventory."""
        invalid_file = tmp_path / "invalid.md"
        invalid_file.write_text("# Empty inventory")

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--inventory-path",
                str(invalid_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 10

    def test_exit_code_1_for_missing_file(
        self, script_path: Path, tmp_path: Path
    ) -> None:
        """Script returns exit code 1 for missing file."""
        nonexistent = tmp_path / "nonexistent.md"

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--inventory-path",
                str(nonexistent),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_risk_at_boundary_scores(self) -> None:
        """Tests risks at score boundaries."""
        content_template = """# Risk Inventory

**Project:** Test
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks

### R001: Boundary Risk
**Category:** Technical
**Likelihood:** {likelihood}
**Impact:** {impact}
**Score:** {score}
**Mitigation:** Plan

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items

| ID | Action |
|-----|--------|
| A001 | Action |
"""
        # Score 15 (boundary for critical)
        content = content_template.format(likelihood=3, impact=5, score=15)
        result = validate_inventory(content)
        assert result.statistics["critical_count"] == 1

        # Score 14 (boundary for high)
        content = content_template.format(likelihood=2, impact=7, score=14)
        result = validate_inventory(content)
        # Will have invalid impact error (7 > 5)
        assert result.valid is False

    def test_unicode_content(self) -> None:
        """Handles Unicode content in inventory."""
        content = """# Risk Inventory

**Project:** Test Project with Unicode: \u2603 \u2764 \U0001F600
**Date:** 2026-01-18
**Objective:** Test unicode handling

## Project Context
Context with unicode: \u00e9\u00e8\u00e0

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        # Should handle unicode without crashing
        assert result.valid is True

    def test_very_long_risk_names(self) -> None:
        """Handles very long risk names."""
        long_name = "A" * 500
        content = f"""# Risk Inventory

**Project:** Test
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
Summary.

## Critical Risks

### R001: {long_name}
**Category:** Technical
**Likelihood:** 5
**Impact:** 5
**Score:** 25
**Mitigation:** Plan

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items

| ID | Action |
|-----|--------|
| A001 | Action |
"""
        result = validate_inventory(content)

        assert result.valid is True
        assert result.statistics["total_risks"] == 1

    def test_special_characters_in_content(self) -> None:
        """Handles special regex characters in content."""
        content = """# Risk Inventory

**Project:** Test [Project] (v1.0) *special*
**Date:** 2026-01-18

## Project Context
Context with special chars: [], (), *, +, ?, ^, $, |

## Risk Summary
Summary.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        # Should handle special characters without crashing
        assert result.valid is True

    def test_case_insensitive_section_matching(self) -> None:
        """Section matching is case-insensitive."""
        content = """# Risk Inventory

**Project:** Test
**Date:** 2026-01-18

## project context
Context.

## RISK SUMMARY
Summary.

## Critical Risks
None.

## HIGH RISKS
None.

## medium risks
None.

## Low Risks
None.

## ACTION ITEMS
None.
"""
        result = validate_inventory(content)

        assert result.valid is True

    def test_empty_statistics_for_no_risks(self) -> None:
        """Statistics calculated correctly when no risks present."""
        content = """# Risk Inventory

**Project:** Test
**Date:** 2026-01-18

## Project Context
Context.

## Risk Summary
No risks identified.

## Critical Risks
None.

## High Risks
None.

## Medium Risks
None.

## Low Risks
None.

## Action Items
None.
"""
        result = validate_inventory(content)

        assert result.statistics["total_risks"] == 0
        assert result.statistics["average_score"] == 0
        assert result.statistics["risks_with_mitigation"] == 0
