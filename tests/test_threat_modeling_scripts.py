"""Tests for threat-modeling skill scripts.

These tests verify the threat model generation, mitigation roadmap creation,
and validation functionality for the threat-modeling skill.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Import the modules under test
sys.path.insert(0, str(Path(__file__).parents[1] / ".claude" / "skills" / "threat-modeling" / "scripts"))

from generate_mitigation_roadmap import (
    RISK_ORDER,
    Threat,
    categorize_by_risk,
    extract_scope,
    format_threat_section,
    format_threat_table,
    generate_roadmap,
    parse_threat_matrix,
    validate_path_no_traversal as roadmap_validate_path,
)
from generate_threat_matrix import (
    STRIDE_CATEGORIES,
    generate_stride_sections,
    generate_threat_matrix,
    validate_path_no_traversal as matrix_validate_path,
)
from validate_threat_model import (
    REQUIRED_SECTIONS,
    RISK_LEVELS,
    STRIDE_CATEGORIES as VALIDATE_STRIDE_CATEGORIES,
    ValidationResult,
    check_components,
    check_mitigations,
    check_required_sections,
    check_threat_matrix,
    validate_threat_model,
    validate_path_no_traversal as validate_model_validate_path,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


# =============================================================================
# Tests for generate_threat_matrix.py
# =============================================================================


class TestGenerateThreatMatrixConstants:
    """Tests for constants in generate_threat_matrix module."""

    def test_stride_categories_count(self) -> None:
        """STRIDE_CATEGORIES contains exactly 6 categories."""
        assert len(STRIDE_CATEGORIES) == 6

    def test_stride_categories_structure(self) -> None:
        """Each STRIDE category has code, name, and description."""
        for item in STRIDE_CATEGORIES:
            assert len(item) == 3
            code, name, description = item
            assert len(code) == 1
            assert isinstance(name, str)
            assert isinstance(description, str)

    def test_stride_codes_are_unique(self) -> None:
        """STRIDE category codes are unique."""
        codes = [item[0] for item in STRIDE_CATEGORIES]
        assert len(codes) == len(set(codes))

    def test_stride_codes_spell_stride(self) -> None:
        """STRIDE category codes spell STRIDE."""
        codes = "".join(item[0] for item in STRIDE_CATEGORIES)
        assert codes == "STRIDE"


class TestGenerateStrideSections:
    """Tests for generate_stride_sections function."""

    def test_generates_all_sections(self) -> None:
        """Generates sections for all STRIDE categories."""
        result = generate_stride_sections()

        for code, name, _ in STRIDE_CATEGORIES:
            assert f"### {code} - {name}" in result

    def test_includes_definition(self) -> None:
        """Each section includes definition."""
        result = generate_stride_sections()

        assert "**Definition**:" in result

    def test_includes_questions(self) -> None:
        """Each section includes questions placeholder."""
        result = generate_stride_sections()

        assert "**Questions to Ask**:" in result

    def test_includes_threats_table(self) -> None:
        """Each section includes threats table."""
        result = generate_stride_sections()

        assert "| ID | Element | Threat | Risk |" in result


class TestGenerateThreatMatrix:
    """Tests for generate_threat_matrix function."""

    def test_creates_output_file(self, tmp_path: Path) -> None:
        """Creates output file at specified path."""
        output_path = tmp_path / "threat-model.md"

        result = generate_threat_matrix("Test Scope", output_path)

        assert result == 0
        assert output_path.exists()

    def test_output_contains_scope(self, tmp_path: Path) -> None:
        """Output contains the provided scope."""
        output_path = tmp_path / "threat-model.md"

        generate_threat_matrix("Authentication Service", output_path)

        content = output_path.read_text()
        assert "# Threat Model: Authentication Service" in content
        assert "**Subject**: Authentication Service" in content

    def test_output_contains_stride_sections(self, tmp_path: Path) -> None:
        """Output contains all STRIDE sections."""
        output_path = tmp_path / "threat-model.md"

        generate_threat_matrix("Test", output_path)

        content = output_path.read_text()
        for code, name, _ in STRIDE_CATEGORIES:
            assert f"### {code} - {name}" in content

    def test_output_contains_threat_matrix_table(self, tmp_path: Path) -> None:
        """Output contains threat matrix table header."""
        output_path = tmp_path / "threat-model.md"

        generate_threat_matrix("Test", output_path)

        content = output_path.read_text()
        assert "| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |" in content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Creates parent directories if they do not exist."""
        output_path = tmp_path / "nested" / "path" / "threat-model.md"

        result = generate_threat_matrix("Test", output_path)

        assert result == 0
        assert output_path.exists()

    def test_prints_summary(self, tmp_path: Path, capsys: CaptureFixture[str]) -> None:
        """Prints summary after generation."""
        output_path = tmp_path / "threat-model.md"

        generate_threat_matrix("Test Scope", output_path)

        captured = capsys.readouterr()
        assert "Generated threat matrix" in captured.out
        assert "Scope: Test Scope" in captured.out
        assert "STRIDE categories: 6" in captured.out


class TestGenerateThreatMatrixCLI:
    """Integration tests for generate_threat_matrix CLI."""

    @pytest.fixture
    def script_path(self) -> Path:
        """Return path to the script."""
        return Path(__file__).parents[1] / ".claude" / "skills" / "threat-modeling" / "scripts" / "generate_threat_matrix.py"

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
        assert "--scope" in result.stdout
        assert "--output" in result.stdout

    def test_missing_required_args(self, script_path: Path) -> None:
        """Missing required args causes error."""
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode != 0
        assert "required" in result.stderr.lower()

    def test_successful_generation(self, script_path: Path, tmp_path: Path) -> None:
        """Successful generation returns exit code 0."""
        output_path = tmp_path / "output.md"

        result = subprocess.run(
            [sys.executable, str(script_path), "--scope", "Test", "--output", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert output_path.exists()


# =============================================================================
# Tests for generate_mitigation_roadmap.py
# =============================================================================


class TestGenerateMitigationRoadmapConstants:
    """Tests for constants in generate_mitigation_roadmap module."""

    def test_risk_order_contains_all_levels(self) -> None:
        """RISK_ORDER contains all risk levels."""
        expected = {"Critical", "High", "Medium", "Low"}
        assert set(RISK_ORDER.keys()) == expected

    def test_risk_order_sorted_correctly(self) -> None:
        """RISK_ORDER has Critical at 0 and Low at 3."""
        assert RISK_ORDER["Critical"] == 0
        assert RISK_ORDER["High"] == 1
        assert RISK_ORDER["Medium"] == 2
        assert RISK_ORDER["Low"] == 3


class TestThreatDataclass:
    """Tests for Threat dataclass."""

    def test_creates_threat(self) -> None:
        """Creates Threat with all fields."""
        threat = Threat(
            id="T001",
            element="Auth Service",
            stride="S",
            description="Spoofing attack",
            likelihood="H",
            impact="H",
            risk="Critical",
        )

        assert threat.id == "T001"
        assert threat.element == "Auth Service"
        assert threat.stride == "S"
        assert threat.description == "Spoofing attack"
        assert threat.status == "Planned"  # Default value

    def test_default_status(self) -> None:
        """Default status is Planned."""
        threat = Threat(
            id="T001",
            element="Test",
            stride="T",
            description="Test",
            likelihood="M",
            impact="M",
            risk="Medium",
        )

        assert threat.status == "Planned"

    def test_custom_status(self) -> None:
        """Custom status overrides default."""
        threat = Threat(
            id="T001",
            element="Test",
            stride="T",
            description="Test",
            likelihood="M",
            impact="M",
            risk="Medium",
            status="In Progress",
        )

        assert threat.status == "In Progress"


class TestParseThreatMatrix:
    """Tests for parse_threat_matrix function."""

    def test_parses_valid_table(self) -> None:
        """Parses valid threat matrix table."""
        content = """
## Threat Matrix

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk | Mitigation Status |
|----|---------|--------|--------|------------|--------|------|-------------------|
| T001 | Auth | S | Spoofing | H | H | Critical | Planned |
| T002 | Data | I | Leak | M | H | High | In Progress |
"""
        result = parse_threat_matrix(content)

        assert len(result) == 2
        assert result[0].id == "T001"
        assert result[0].stride == "S"
        assert result[0].risk == "Critical"
        assert result[1].id == "T002"

    def test_returns_empty_for_no_table(self) -> None:
        """Returns empty list when no table found."""
        content = "# No table here"

        result = parse_threat_matrix(content)

        assert result == []

    def test_skips_separator_rows(self) -> None:
        """Skips table separator rows."""
        content = """
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Test | T | Test threat | M | M | Medium |
"""
        result = parse_threat_matrix(content)

        assert len(result) == 1

    def test_skips_incomplete_rows(self) -> None:
        """Skips rows with fewer than 7 cells."""
        content = """
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Test |
| T002 | Complete | S | Test | H | H | High |
"""
        result = parse_threat_matrix(content)

        assert len(result) == 1
        assert result[0].id == "T002"


class TestCategorizeByRisk:
    """Tests for categorize_by_risk function."""

    def test_categorizes_threats(self) -> None:
        """Categorizes threats by risk level."""
        threats = [
            Threat(id="T001", element="A", stride="S", description="X", likelihood="H", impact="H", risk="Critical"),
            Threat(id="T002", element="B", stride="T", description="Y", likelihood="H", impact="M", risk="High"),
            Threat(id="T003", element="C", stride="R", description="Z", likelihood="M", impact="M", risk="Medium"),
            Threat(id="T004", element="D", stride="I", description="W", likelihood="L", impact="L", risk="Low"),
        ]

        result = categorize_by_risk(threats)

        assert len(result["Critical"]) == 1
        assert len(result["High"]) == 1
        assert len(result["Medium"]) == 1
        assert len(result["Low"]) == 1

    def test_normalizes_risk_levels(self) -> None:
        """Normalizes case-insensitive risk levels."""
        threats = [
            Threat(id="T001", element="A", stride="S", description="X", likelihood="H", impact="H", risk="CRITICAL"),
            Threat(id="T002", element="B", stride="T", description="Y", likelihood="M", impact="M", risk="medium"),
        ]

        result = categorize_by_risk(threats)

        assert len(result["Critical"]) == 1
        assert len(result["Medium"]) == 1

    def test_defaults_unknown_to_medium(self) -> None:
        """Defaults unknown risk levels to Medium."""
        threats = [
            Threat(id="T001", element="A", stride="S", description="X", likelihood="M", impact="M", risk="Unknown"),
        ]

        result = categorize_by_risk(threats)

        assert len(result["Medium"]) == 1

    def test_returns_empty_categories_for_no_threats(self) -> None:
        """Returns empty categories when no threats provided."""
        result = categorize_by_risk([])

        assert result == {"Critical": [], "High": [], "Medium": [], "Low": []}


class TestFormatThreatSection:
    """Tests for format_threat_section function."""

    def test_formats_threats(self) -> None:
        """Formats threats for roadmap section."""
        threats = [
            Threat(id="T001", element="Auth", stride="S", description="Spoofing", likelihood="H", impact="H", risk="Critical"),
        ]

        result = format_threat_section(threats)

        assert "### T001: Spoofing" in result
        assert "**Element**: Auth" in result
        assert "**STRIDE**: S" in result

    def test_returns_placeholder_for_no_threats(self) -> None:
        """Returns placeholder for empty threat list."""
        result = format_threat_section([])

        assert "_No threats at this level_" in result


class TestFormatThreatTable:
    """Tests for format_threat_table function."""

    def test_formats_table(self) -> None:
        """Formats all threats as summary table."""
        threats = [
            Threat(id="T001", element="A", stride="S", description="Test", likelihood="H", impact="H", risk="Critical"),
        ]

        result = format_threat_table(threats)

        assert "| ID | STRIDE | Risk | Description | Status |" in result
        assert "| T001 | S | Critical | Test | Planned |" in result

    def test_sorts_by_risk(self) -> None:
        """Sorts threats by risk level."""
        threats = [
            Threat(id="T001", element="A", stride="S", description="Low", likelihood="L", impact="L", risk="Low"),
            Threat(id="T002", element="B", stride="T", description="Critical", likelihood="H", impact="H", risk="Critical"),
        ]

        result = format_threat_table(threats)

        # Critical should appear before Low
        critical_pos = result.find("T002")
        low_pos = result.find("T001")
        assert critical_pos < low_pos


class TestExtractScope:
    """Tests for extract_scope function."""

    def test_extracts_from_title(self) -> None:
        """Extracts scope from threat model title."""
        content = "# Threat Model: Auth Service\n"

        result = extract_scope(content)

        assert result == "Auth Service"

    def test_extracts_from_subject(self) -> None:
        """Extracts scope from subject field."""
        content = """
## Scope

- **Subject**: Payment Gateway
"""
        result = extract_scope(content)

        assert result == "Payment Gateway"

    def test_returns_default_for_unknown(self) -> None:
        """Returns default when scope not found."""
        content = "# Some Document"

        result = extract_scope(content)

        assert result == "Unknown Scope"


class TestGenerateRoadmap:
    """Tests for generate_roadmap function."""

    @pytest.fixture
    def valid_threat_model(self, tmp_path: Path) -> Path:
        """Create a valid threat model file."""
        content = """# Threat Model: Test Service

## Threat Matrix

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk | Mitigation Status |
|----|---------|--------|--------|------------|--------|------|-------------------|
| T001 | Auth | S | Spoofing | H | H | Critical | Planned |
| T002 | Data | I | Leak | M | M | Medium | Planned |
"""
        threat_model = tmp_path / "threat-model.md"
        threat_model.write_text(content)
        return threat_model

    def test_generates_roadmap(self, valid_threat_model: Path, tmp_path: Path) -> None:
        """Generates roadmap from threat model."""
        output_path = tmp_path / "roadmap.md"

        result = generate_roadmap(valid_threat_model, output_path)

        assert result == 0
        assert output_path.exists()

    def test_roadmap_contains_summary(self, valid_threat_model: Path, tmp_path: Path) -> None:
        """Roadmap contains executive summary."""
        output_path = tmp_path / "roadmap.md"

        generate_roadmap(valid_threat_model, output_path)

        content = output_path.read_text()
        assert "## Executive Summary" in content
        assert "Total Threats" in content

    def test_roadmap_contains_priority_sections(self, valid_threat_model: Path, tmp_path: Path) -> None:
        """Roadmap contains priority sections."""
        output_path = tmp_path / "roadmap.md"

        generate_roadmap(valid_threat_model, output_path)

        content = output_path.read_text()
        assert "## Priority 1: Critical Risks" in content
        assert "## Priority 2: High Risks" in content
        assert "## Priority 3: Medium Risks" in content
        assert "## Priority 4: Low Risks" in content

    def test_returns_error_for_missing_file(self, tmp_path: Path) -> None:
        """Returns error code for missing input file."""
        output_path = tmp_path / "roadmap.md"

        result = generate_roadmap(tmp_path / "nonexistent.md", output_path)

        assert result == 1

    def test_handles_empty_threat_matrix(self, tmp_path: Path, capsys: CaptureFixture[str]) -> None:
        """Handles threat model with no threats."""
        content = "# Threat Model: Empty\n\nNo threat matrix here."
        input_path = tmp_path / "empty.md"
        input_path.write_text(content)
        output_path = tmp_path / "roadmap.md"

        result = generate_roadmap(input_path, output_path)

        assert result == 0
        captured = capsys.readouterr()
        assert "Warning: No threats found" in captured.err


class TestGenerateMitigationRoadmapCLI:
    """Integration tests for generate_mitigation_roadmap CLI."""

    @pytest.fixture
    def script_path(self) -> Path:
        """Return path to the script."""
        return Path(__file__).parents[1] / ".claude" / "skills" / "threat-modeling" / "scripts" / "generate_mitigation_roadmap.py"

    @pytest.fixture
    def valid_threat_model(self, tmp_path: Path) -> Path:
        """Create a valid threat model file."""
        content = """# Threat Model: Test

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Test | S | Test threat | H | H | Critical |
"""
        threat_model = tmp_path / "threats.md"
        threat_model.write_text(content)
        return threat_model

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
        assert "--input" in result.stdout
        assert "--output" in result.stdout

    def test_successful_generation(self, script_path: Path, valid_threat_model: Path, tmp_path: Path) -> None:
        """Successful generation returns exit code 0."""
        output_path = tmp_path / "roadmap.md"

        result = subprocess.run(
            [sys.executable, str(script_path), "--input", str(valid_threat_model), "--output", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert output_path.exists()


# =============================================================================
# Tests for validate_threat_model.py
# =============================================================================


class TestValidateThreatModelConstants:
    """Tests for constants in validate_threat_model module."""

    def test_required_sections_count(self) -> None:
        """REQUIRED_SECTIONS contains expected count."""
        assert len(REQUIRED_SECTIONS) == 5

    def test_stride_categories_match(self) -> None:
        """STRIDE_CATEGORIES contains expected codes."""
        assert VALIDATE_STRIDE_CATEGORIES == {"S", "T", "R", "I", "D", "E"}

    def test_risk_levels(self) -> None:
        """RISK_LEVELS contains expected values."""
        assert RISK_LEVELS == {"Critical", "High", "Medium", "Low"}


class TestValidationResultDataclass:
    """Tests for ValidationResult dataclass."""

    def test_default_is_passed(self) -> None:
        """Default result is passed."""
        result = ValidationResult(passed=True, message="Test")

        assert result.passed
        assert result.severity == "error"  # Default severity

    def test_custom_severity(self) -> None:
        """Custom severity is preserved."""
        result = ValidationResult(passed=True, message="Test", severity="warning")

        assert result.severity == "warning"


class TestCheckRequiredSections:
    """Tests for check_required_sections function."""

    def test_passes_for_all_sections(self) -> None:
        """Passes when all required sections present."""
        content = """
## Scope
## Architecture Overview
## STRIDE Analysis
## Threat Matrix
## Mitigations
"""
        results = check_required_sections(content)

        passed = [r for r in results if r.passed]
        assert len(passed) == 5

    def test_fails_for_missing_section(self) -> None:
        """Fails when required section missing."""
        content = """
## Scope
## Architecture Overview
"""
        results = check_required_sections(content)

        failed = [r for r in results if not r.passed]
        assert len(failed) > 0
        assert any("STRIDE" in r.message for r in failed)

    def test_handles_numbered_sections(self) -> None:
        """Handles numbered section headers."""
        content = """
## 1. Scope
## 2. Architecture Overview
## 3. STRIDE Analysis
## 4. Threat Matrix
## 5. Mitigations
"""
        results = check_required_sections(content)

        passed = [r for r in results if r.passed]
        assert len(passed) == 5


class TestCheckThreatMatrix:
    """Tests for check_threat_matrix function."""

    def test_passes_for_valid_matrix(self) -> None:
        """Passes for valid threat matrix."""
        content = """
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Auth | S | Spoofing | H | H | Critical |
| T002 | Data | T | Tampering | M | H | High |
"""
        results = check_threat_matrix(content)

        errors = [r for r in results if not r.passed and r.severity == "error"]
        assert len(errors) == 0

    def test_fails_for_missing_table(self) -> None:
        """Fails when threat matrix table missing."""
        content = "# No table here"

        results = check_threat_matrix(content)

        errors = [r for r in results if not r.passed]
        assert len(errors) > 0
        assert any("not found" in r.message for r in errors)

    def test_fails_for_invalid_stride(self) -> None:
        """Fails for invalid STRIDE category."""
        content = """
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Auth | X | Invalid | H | H | Critical |
"""
        results = check_threat_matrix(content)

        errors = [r for r in results if not r.passed and r.severity == "error"]
        assert any("Invalid STRIDE" in r.message for r in errors)

    def test_fails_for_invalid_risk(self) -> None:
        """Fails for invalid risk level."""
        content = """
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Auth | S | Test | H | H | InvalidRisk |
"""
        results = check_threat_matrix(content)

        errors = [r for r in results if not r.passed and r.severity == "error"]
        assert any("Invalid risk level" in r.message for r in errors)

    def test_warns_for_missing_stride_coverage(self) -> None:
        """Warns when not all STRIDE categories covered."""
        content = """
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Auth | S | Spoofing | H | H | Critical |
"""
        results = check_threat_matrix(content)

        warnings = [r for r in results if r.severity == "warning"]
        assert any("not addressed" in r.message for r in warnings)


class TestCheckMitigations:
    """Tests for check_mitigations function."""

    def test_passes_when_mitigations_documented(self) -> None:
        """Passes when Critical/High threats have mitigations."""
        content = """
| T001 | Auth | S | Spoofing | H | H | Critical |

## Mitigations

### T001 Mitigation

Use MFA to prevent spoofing.
"""
        results = check_mitigations(content)

        passed = [r for r in results if r.passed and "documented" in r.message]
        assert len(passed) >= 1

    def test_fails_when_mitigation_missing(self) -> None:
        """Fails when Critical/High threat has no mitigation."""
        content = """
| T001 | Auth | S | Spoofing | H | H | Critical |

## Mitigations

No specific mitigations documented.
"""
        results = check_mitigations(content)

        errors = [r for r in results if not r.passed]
        assert any("No mitigation found" in r.message for r in errors)

    def test_passes_for_no_critical_high_threats(self) -> None:
        """Passes when no Critical/High threats exist."""
        content = """
| T001 | Auth | S | Spoofing | L | L | Low |

## Mitigations
"""
        results = check_mitigations(content)

        # Should have info message about no Critical/High threats
        info = [r for r in results if "No Critical/High" in r.message]
        assert len(info) >= 1


class TestCheckComponents:
    """Tests for check_components function."""

    def test_passes_with_components(self) -> None:
        """Passes when components table has entries."""
        content = """
| ID | Name | Type | Description |
|----|------|------|-------------|
| C001 | Auth Service | Process | Handles authentication |
"""
        results = check_components(content)

        passed = [r for r in results if r.passed and "Found" in r.message]
        assert len(passed) >= 1

    def test_warns_for_missing_components_table(self) -> None:
        """Warns when components table missing."""
        content = "# No components table"

        results = check_components(content)

        warnings = [r for r in results if r.severity == "warning"]
        assert any("not found" in r.message for r in warnings)


class TestValidateThreatModel:
    """Tests for validate_threat_model function."""

    @pytest.fixture
    def valid_threat_model(self, tmp_path: Path) -> Path:
        """Create a valid threat model file."""
        content = """# Threat Model: Test Service

## Scope

Test scope content.

## Architecture Overview

Architecture content.

## STRIDE Analysis

STRIDE content.

## Threat Matrix

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Auth | S | Spoofing | H | H | Critical |

## Mitigations

### T001 Mitigation

Use MFA.

| ID | Name | Type | Description |
|----|------|------|-------------|
| C001 | Auth | Process | Auth service |
"""
        threat_model = tmp_path / "valid.md"
        threat_model.write_text(content)
        return threat_model

    def test_passes_for_valid_model(self, valid_threat_model: Path) -> None:
        """Passes for valid threat model."""
        passed, results = validate_threat_model(valid_threat_model)

        assert passed

    def test_fails_for_missing_file(self, tmp_path: Path) -> None:
        """Fails for missing file."""
        passed, results = validate_threat_model(tmp_path / "nonexistent.md")

        assert not passed
        assert any("not found" in r.message for r in results)

    def test_fails_for_incomplete_model(self, tmp_path: Path) -> None:
        """Fails for incomplete threat model."""
        content = "# Incomplete Model\n\nNo required sections."
        incomplete = tmp_path / "incomplete.md"
        incomplete.write_text(content)

        passed, results = validate_threat_model(incomplete)

        assert not passed


class TestValidateThreatModelCLI:
    """Integration tests for validate_threat_model CLI."""

    @pytest.fixture
    def script_path(self) -> Path:
        """Return path to the script."""
        return Path(__file__).parents[1] / ".claude" / "skills" / "threat-modeling" / "scripts" / "validate_threat_model.py"

    @pytest.fixture
    def valid_threat_model(self, tmp_path: Path) -> Path:
        """Create a valid threat model file."""
        content = """# Threat Model: Test

## Scope
Test

## Architecture
Test

## STRIDE Analysis
Test

## Threat Matrix

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Test | S | Test | H | H | Critical |

## Mitigations

T001: Use MFA

| ID | Name | Type | Description |
|----|------|------|-------------|
| C001 | Test | Process | Test |
"""
        threat_model = tmp_path / "valid.md"
        threat_model.write_text(content)
        return threat_model

    @pytest.fixture
    def invalid_threat_model(self, tmp_path: Path) -> Path:
        """Create an invalid threat model file."""
        content = "# Invalid Model\n\nNo sections."
        threat_model = tmp_path / "invalid.md"
        threat_model.write_text(content)
        return threat_model

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
        assert "--json" in result.stdout

    def test_valid_model_returns_0(self, script_path: Path, valid_threat_model: Path) -> None:
        """Valid model returns exit code 0."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(valid_threat_model)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "PASSED" in result.stdout

    def test_invalid_model_returns_10(self, script_path: Path, invalid_threat_model: Path) -> None:
        """Invalid model returns exit code 10."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(invalid_threat_model)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 10
        assert "FAILED" in result.stdout

    def test_json_output_mode(self, script_path: Path, valid_threat_model: Path) -> None:
        """--json flag outputs JSON format."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(valid_threat_model), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "passed" in output
        assert "results" in output
        assert output["passed"] is True

    def test_json_output_for_invalid(self, script_path: Path, invalid_threat_model: Path) -> None:
        """--json flag outputs JSON for invalid model."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(invalid_threat_model), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 10
        output = json.loads(result.stdout)
        assert output["passed"] is False

    def test_missing_file_returns_10(self, script_path: Path, tmp_path: Path) -> None:
        """Missing file returns exit code 10."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(tmp_path / "nonexistent.md")],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 10


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestEdgeCases:
    """Edge case tests for all threat modeling scripts."""

    def test_empty_file(self, tmp_path: Path) -> None:
        """Handles empty file gracefully."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        passed, results = validate_threat_model(empty_file)

        assert not passed

    def test_unicode_content(self, tmp_path: Path) -> None:
        """Handles unicode content."""
        content = """# Threat Model: Test

## Scope
Unicode: \u00e9\u00e8\u00ea

## Architecture
Unicode content

## STRIDE Analysis
Test

## Threat Matrix

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Test | S | Test \u00e9 | H | H | Critical |

## Mitigations

T001: Mitigation
"""
        unicode_file = tmp_path / "unicode.md"
        unicode_file.write_text(content)

        passed, results = validate_threat_model(unicode_file)

        # Should complete without error
        assert isinstance(passed, bool)

    def test_very_long_threat_description(self, tmp_path: Path) -> None:
        """Handles very long threat descriptions."""
        long_desc = "A" * 1000
        content = f"""
| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Test | S | {long_desc} | H | H | Critical |
"""
        threats = parse_threat_matrix(content)

        assert len(threats) == 1
        assert len(threats[0].description) == 1000

    def test_special_characters_in_scope(self, tmp_path: Path) -> None:
        """Handles special characters in scope."""
        output_path = tmp_path / "special.md"

        result = generate_threat_matrix("Auth & Auth < > Service", output_path)

        assert result == 0
        content = output_path.read_text()
        assert "Auth & Auth < > Service" in content


# =============================================================================
# Security Tests for Path Traversal (CWE-22)
# =============================================================================


class TestPathTraversalSecurity:
    """Tests for CWE-22 path traversal protection across all threat-modeling scripts."""

    # Tests for generate_mitigation_roadmap.py
    def test_roadmap_validate_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Path traversal attempt raises PermissionError for roadmap script."""
        malicious_path = tmp_path / ".." / ".." / "etc" / "passwd"

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            roadmap_validate_path(malicious_path, "test path")

    def test_roadmap_validate_path_relative_escape_rejected(self) -> None:
        """Relative path that escapes cwd is rejected for roadmap script."""
        malicious_path = Path("../../etc/passwd")

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            roadmap_validate_path(malicious_path, "test path")

    def test_roadmap_validate_path_absolute_without_traversal_allowed(self) -> None:
        """Absolute path without traversal is allowed for pytest compatibility."""
        # Absolute paths without '..' are allowed (needed for pytest's tmp_path)
        absolute_path = Path("/tmp/test_file")
        # Should not raise - returns resolved path
        result = roadmap_validate_path(absolute_path, "test path")
        assert result == absolute_path.resolve()

    def test_roadmap_validate_path_valid_inside_cwd(self) -> None:
        """Valid path inside cwd is accepted for roadmap script."""
        valid_path = Path(".")
        result = roadmap_validate_path(valid_path, "test path")
        assert result is not None

    # Tests for generate_threat_matrix.py
    def test_matrix_validate_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Path traversal attempt raises PermissionError for matrix script."""
        malicious_path = tmp_path / ".." / ".." / "etc" / "passwd"

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            matrix_validate_path(malicious_path, "test path")

    def test_matrix_validate_path_relative_escape_rejected(self) -> None:
        """Relative path that escapes cwd is rejected for matrix script."""
        malicious_path = Path("../../etc/passwd")

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            matrix_validate_path(malicious_path, "test path")

    def test_matrix_validate_path_valid_inside_cwd(self) -> None:
        """Valid path inside cwd is accepted for matrix script."""
        valid_path = Path(".")
        result = matrix_validate_path(valid_path, "test path")
        assert result is not None

    # Tests for validate_threat_model.py
    def test_validate_model_validate_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Path traversal attempt raises PermissionError for validation script."""
        malicious_path = tmp_path / ".." / ".." / "etc" / "passwd"

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            validate_model_validate_path(malicious_path, "test path")

    def test_validate_model_validate_path_relative_escape_rejected(self) -> None:
        """Relative path that escapes cwd is rejected for validation script."""
        malicious_path = Path("../../etc/passwd")

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            validate_model_validate_path(malicious_path, "test path")

    def test_validate_model_validate_path_valid_inside_cwd(self) -> None:
        """Valid path inside cwd is accepted for validation script."""
        valid_path = Path(".")
        result = validate_model_validate_path(valid_path, "test path")
        assert result is not None

    # Integration tests for public functions
    def test_generate_threat_matrix_rejects_traversal(self) -> None:
        """generate_threat_matrix rejects path traversal attempts."""
        malicious_path = Path("../../etc/passwd")

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            generate_threat_matrix("Test Scope", malicious_path)

    def test_validate_threat_model_rejects_traversal(self) -> None:
        """validate_threat_model rejects path traversal attempts."""
        malicious_path = Path("../../etc/passwd")

        passed, results = validate_threat_model(malicious_path)

        # Should return False with an error about path traversal
        assert passed is False
        assert len(results) == 1
        assert "traversal" in results[0].message.lower() or "outside" in results[0].message.lower()

    def test_generate_roadmap_input_rejects_traversal(self, tmp_path: Path) -> None:
        """generate_roadmap rejects path traversal for input file."""
        malicious_input = Path("../../etc/passwd")
        output_path = tmp_path / "output.md"

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            generate_roadmap(malicious_input, output_path)

    def test_generate_roadmap_output_rejects_traversal(self, tmp_path: Path) -> None:
        """generate_roadmap rejects path traversal for output file."""
        # Create a valid input file first
        input_file = tmp_path / "threat-model.md"
        input_file.write_text("""# Threat Model

## Scope
Test system

| ID | Element | STRIDE | Threat | Likelihood | Impact | Risk |
|----|---------|--------|--------|------------|--------|------|
| T001 | Auth | S | Spoofing | H | H | Critical |
""")
        malicious_output = Path("../../etc/passwd")

        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            generate_roadmap(input_file, malicious_output)
