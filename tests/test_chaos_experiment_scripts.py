"""Tests for chaos-experiment skill scripts.

These tests verify the chaos experiment document generation and validation
functionality used by the chaos-experiment skill.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add the skill scripts directory to path for imports
SKILL_SCRIPTS_PATH = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "chaos-experiment" / "scripts"
)
sys.path.insert(0, str(SKILL_SCRIPTS_PATH))

# ruff: noqa: E402
from generate_experiment import (
    Result,
    generate_document,
    generate_experiment_id,
    load_template,
    save_document,
)
from validate_experiment import (
    INCOMPLETE_PATTERNS,
    RECOMMENDED_SECTIONS,
    REQUIRED_SECTIONS,
    ValidationResult,
    calculate_score,
    check_hypothesis_quality,
    check_incomplete_markers,
    check_metrics_defined,
    check_rollback_procedure,
    check_section_presence,
    load_document,
    validate_experiment,
)


class TestGenerateExperimentId:
    """Tests for generate_experiment_id function."""

    def test_basic_name_slugification(self) -> None:
        """Name is converted to lowercase slug."""
        result = generate_experiment_id("API Gateway")

        assert "api-gateway" in result
        assert result.startswith("chaos-")

    def test_date_prefix_included(self) -> None:
        """Generated ID includes current date."""
        result = generate_experiment_id("Test")
        today = datetime.now().strftime("%Y%m%d")

        assert today in result

    def test_special_characters_removed(self) -> None:
        """Special characters are converted to hyphens."""
        result = generate_experiment_id("Test@#$%Name!!!")

        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "!" not in result

    def test_consecutive_hyphens_collapsed(self) -> None:
        """Consecutive special characters produce single hyphen."""
        result = generate_experiment_id("Test   Name")

        assert "---" not in result
        assert "--" not in result

    def test_truncation_at_30_chars(self) -> None:
        """Long names are truncated in the slug portion."""
        long_name = "A" * 100
        result = generate_experiment_id(long_name)

        # Slug portion should be at most 30 chars
        # Format: chaos-YYYYMMDD-slug
        parts = result.split("-", 2)
        slug = parts[2] if len(parts) > 2 else ""
        assert len(slug) <= 30


class TestLoadTemplate:
    """Tests for load_template function."""

    def test_template_loads_successfully(self) -> None:
        """Template file is loaded without error."""
        content = load_template()

        assert "{{EXPERIMENT_NAME}}" in content
        assert "## Metadata" in content
        assert "## Hypothesis" in content

    def test_template_contains_required_sections(self) -> None:
        """Template contains all required sections."""
        content = load_template()

        for section_name, pattern in REQUIRED_SECTIONS:
            assert pattern.strip("^$").replace("\\", "") in content, (
                f"Template missing section: {section_name}"
            )


class TestGenerateDocument:
    """Tests for generate_document function."""

    def test_basic_generation(self) -> None:
        """Document is generated with provided name."""
        content = generate_document(name="API Gateway Resilience")

        assert "API Gateway Resilience" in content
        assert "{{EXPERIMENT_NAME}}" not in content

    def test_all_parameters_replaced(self) -> None:
        """All provided parameters are substituted in document."""
        content = generate_document(
            name="Test Experiment",
            system="Payment Service",
            owner="Jane Doe",
            region="us-west-2",
            target_date="2026-02-01",
        )

        assert "Test Experiment" in content
        assert "Payment Service" in content
        assert "Jane Doe" in content
        assert "us-west-2" in content
        assert "2026-02-01" in content

    def test_default_tbd_values(self) -> None:
        """Default TBD values are used when parameters not provided."""
        content = generate_document(name="Test")

        # System, owner, region default to TBD
        assert "TBD" in content

    def test_date_created_is_today(self) -> None:
        """Date created is set to today."""
        content = generate_document(name="Test")
        today = datetime.now().strftime("%Y-%m-%d")

        assert today in content

    def test_experiment_id_generated(self) -> None:
        """Experiment ID is generated and included."""
        content = generate_document(name="Test")
        today = datetime.now().strftime("%Y%m%d")

        assert f"chaos-{today}" in content


class TestSaveDocument:
    """Tests for save_document function."""

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """Output directory is created if it does not exist."""
        output_dir = tmp_path / "new" / "nested" / "dir"
        content = "# Test Document"

        save_document(content, output_dir, "Test")

        assert output_dir.exists()

    def test_file_created_with_correct_name(self, tmp_path: Path) -> None:
        """File is created with date-prefixed name."""
        content = "# Test Document"
        today = datetime.now().strftime("%Y-%m-%d")

        output_path = save_document(content, tmp_path, "API Gateway")

        assert output_path.exists()
        assert output_path.name.startswith(today)
        assert "api-gateway" in output_path.name.lower()
        assert output_path.suffix == ".md"

    def test_content_written_correctly(self, tmp_path: Path) -> None:
        """Document content is written to file."""
        content = "# Test Content\n\nThis is a test."

        output_path = save_document(content, tmp_path, "Test")
        written_content = output_path.read_text(encoding="utf-8")

        assert written_content == content

    def test_long_name_truncated_in_filename(self, tmp_path: Path) -> None:
        """Long experiment names are truncated in filename."""
        content = "# Test"
        long_name = "A" * 100

        output_path = save_document(content, tmp_path, long_name)

        # Filename slug portion should be truncated
        name_without_date = output_path.stem.split("-", 3)[-1]
        assert len(name_without_date) <= 50


class TestResult:
    """Tests for Result dataclass."""

    def test_success_result(self) -> None:
        """Success result has correct attributes."""
        result = Result(success=True, message="Done")

        assert result.success is True
        assert result.message == "Done"
        assert result.data is None
        assert result.errors is None

    def test_failure_result_with_errors(self) -> None:
        """Failure result includes errors."""
        result = Result(
            success=False,
            message="Failed",
            errors=["Error 1", "Error 2"],
        )

        assert result.success is False
        assert len(result.errors) == 2

    def test_result_with_data(self) -> None:
        """Result can include data dictionary."""
        result = Result(
            success=True,
            message="Done",
            data={"path": "/test/file.md", "name": "Test"},
        )

        assert result.data["path"] == "/test/file.md"


# =============================================================================
# Validation Script Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_is_successful(self) -> None:
        """Empty result is successful."""
        result = ValidationResult(success=True, message="OK")

        assert result.success is True
        assert result.errors == []
        assert result.warnings == []
        assert result.score == 0

    def test_result_with_score(self) -> None:
        """Result can have score."""
        result = ValidationResult(
            success=True,
            message="Passed",
            score=85,
        )

        assert result.score == 85


class TestCheckSectionPresence:
    """Tests for check_section_presence function."""

    def test_all_sections_present(self) -> None:
        """All sections found returns empty missing list."""
        content = """
        ## Metadata
        Content here

        ## System Under Test
        More content
        """
        sections = [("Metadata", r"## Metadata"), ("System", r"## System Under Test")]

        present, missing = check_section_presence(content, sections)

        assert len(present) == 2
        assert len(missing) == 0

    def test_missing_section_detected(self) -> None:
        """Missing section is reported."""
        content = """
        ## Metadata
        Content here
        """
        sections = [("Metadata", r"## Metadata"), ("Hypothesis", r"## Hypothesis")]

        present, missing = check_section_presence(content, sections)

        assert "Metadata" in present
        assert "Hypothesis" in missing

    def test_case_insensitive_matching(self) -> None:
        """Section matching is case insensitive."""
        content = """
        ## METADATA
        Content
        """
        sections = [("Metadata", r"## Metadata")]

        present, missing = check_section_presence(content, sections)

        assert "Metadata" in present


class TestCheckIncompleteMarkers:
    """Tests for check_incomplete_markers function."""

    def test_no_markers_returns_empty(self) -> None:
        """Clean content returns no issues."""
        content = """
        ## Metadata
        Complete content with no placeholders.
        """

        issues = check_incomplete_markers(content)

        assert len(issues) == 0

    def test_template_placeholder_detected(self) -> None:
        """Template placeholders are detected."""
        content = "Name: {{EXPERIMENT_NAME}}"

        issues = check_incomplete_markers(content)

        assert any("Template placeholder" in issue for issue in issues)

    def test_tbd_marker_detected(self) -> None:
        """TBD markers are detected."""
        content = "Owner: TBD"

        issues = check_incomplete_markers(content)

        assert any("TBD marker" in issue for issue in issues)

    def test_todo_marker_detected(self) -> None:
        """TODO markers are detected."""
        content = "TODO: Fill in this section"

        issues = check_incomplete_markers(content)

        assert any("TODO marker" in issue for issue in issues)

    def test_fill_in_marker_detected(self) -> None:
        """Fill-in markers are detected."""
        content = "Value: [FILL IN]"

        issues = check_incomplete_markers(content)

        assert any("Fill-in marker" in issue for issue in issues)

    def test_multiple_occurrences_counted(self) -> None:
        """Multiple occurrences of same marker are counted."""
        content = "TBD and TBD and TBD"

        issues = check_incomplete_markers(content)

        # Should mention count
        assert any("3 occurrence" in issue for issue in issues)


class TestCheckHypothesisQuality:
    """Tests for check_hypothesis_quality function."""

    def test_complete_hypothesis(self) -> None:
        """Well-formed hypothesis passes."""
        content = """
        ## Hypothesis

        Given the system is in steady state,
        When we inject a network failure,
        Then the system should recover,
        Because circuit breakers are in place.
        """

        is_complete, warnings = check_hypothesis_quality(content)

        assert is_complete is True
        assert len(warnings) == 0

    def test_missing_given_clause(self) -> None:
        """Missing Given clause is flagged."""
        content = """
        ## Hypothesis

        When we inject failure, Then system recovers, Because of retry logic.
        """

        is_complete, warnings = check_hypothesis_quality(content)

        assert is_complete is False
        assert any("Given" in w for w in warnings)

    def test_missing_when_clause(self) -> None:
        """Missing When clause is flagged."""
        content = """
        ## Hypothesis

        Given system in steady state, Then it recovers, Because of retries.
        """

        is_complete, warnings = check_hypothesis_quality(content)

        assert is_complete is False
        assert any("When" in w for w in warnings)

    def test_missing_then_clause(self) -> None:
        """Missing Then clause is flagged."""
        content = """
        ## Hypothesis

        Given system in steady state, When we inject failure, Because of retries.
        """

        is_complete, warnings = check_hypothesis_quality(content)

        assert is_complete is False
        assert any("Then" in w for w in warnings)

    def test_missing_because_clause(self) -> None:
        """Missing Because clause is flagged."""
        content = """
        ## Hypothesis

        Given system in steady state, When we inject failure, Then it recovers.
        """

        is_complete, warnings = check_hypothesis_quality(content)

        assert is_complete is False
        assert any("Because" in w for w in warnings)

    def test_no_hypothesis_section(self) -> None:
        """Missing section returns failure."""
        content = """
        ## Other Section
        Content
        """

        is_complete, warnings = check_hypothesis_quality(content)

        assert is_complete is False
        assert any("not found" in w for w in warnings)


class TestCheckRollbackProcedure:
    """Tests for check_rollback_procedure function."""

    def test_complete_rollback_procedure(self) -> None:
        """Well-formed rollback procedure passes."""
        content = """
        ## Rollback Procedure

        ### Manual Rollback

        ```bash
        kubectl delete pod troubled-pod
        ```

        ### Verification

        Verify that the pod has been deleted.
        """

        is_complete, warnings = check_rollback_procedure(content)

        assert is_complete is True
        assert len(warnings) == 0

    def test_missing_code_blocks(self) -> None:
        """Missing commands are flagged."""
        content = """
        ## Rollback Procedure

        Run the rollback script. Verify the rollback.
        """

        is_complete, warnings = check_rollback_procedure(content)

        assert is_complete is False
        assert any("commands" in w for w in warnings)

    def test_missing_verification_steps(self) -> None:
        """Missing verification is flagged."""
        content = """
        ## Rollback Procedure

        ```bash
        kubectl delete pod troubled-pod
        ```
        """

        is_complete, warnings = check_rollback_procedure(content)

        assert is_complete is False
        assert any("verification" in w.lower() for w in warnings)

    def test_no_rollback_section(self) -> None:
        """Missing section returns failure."""
        content = """
        ## Other Section
        Content
        """

        is_complete, warnings = check_rollback_procedure(content)

        assert is_complete is False
        assert any("not found" in w for w in warnings)


class TestCheckMetricsDefined:
    """Tests for check_metrics_defined function."""

    def test_complete_metrics(self) -> None:
        """Well-formed baseline metrics pass."""
        content = """
        ## Steady State Baseline

        | Metric | Value | Green Threshold |
        |--------|-------|-----------------|
        | P99 Latency | 50ms | < 100ms |
        """

        is_complete, warnings = check_metrics_defined(content)

        assert is_complete is True
        assert len(warnings) == 0

    def test_missing_metrics_table(self) -> None:
        """Missing table is flagged."""
        content = """
        ## Steady State Baseline

        The system has good latency and low error rates.
        """

        is_complete, warnings = check_metrics_defined(content)

        assert is_complete is False
        assert any("table" in w for w in warnings)

    def test_missing_thresholds(self) -> None:
        """Missing thresholds are flagged."""
        content = """
        ## Steady State Baseline

        | Metric | Value |
        |--------|-------|
        | P99 Latency | 50ms |
        """

        is_complete, warnings = check_metrics_defined(content)

        assert is_complete is False
        assert any("threshold" in w.lower() for w in warnings)

    def test_no_baseline_section(self) -> None:
        """Missing section returns failure."""
        content = """
        ## Other Section
        Content
        """

        is_complete, warnings = check_metrics_defined(content)

        assert is_complete is False
        assert any("not found" in w for w in warnings)


class TestCalculateScore:
    """Tests for calculate_score function."""

    def test_perfect_score(self) -> None:
        """All items complete gives score near 100."""
        score = calculate_score(
            required_present=6,
            required_total=6,
            recommended_present=4,
            recommended_total=4,
            incomplete_count=0,
            hypothesis_complete=True,
            rollback_complete=True,
            metrics_complete=True,
        )

        assert score == 100

    def test_zero_score_all_missing(self) -> None:
        """Everything missing gives low score."""
        score = calculate_score(
            required_present=0,
            required_total=6,
            recommended_present=0,
            recommended_total=4,
            incomplete_count=20,
            hypothesis_complete=False,
            rollback_complete=False,
            metrics_complete=False,
        )

        assert score == 0

    def test_partial_score(self) -> None:
        """Partial completion gives proportional score."""
        score = calculate_score(
            required_present=3,
            required_total=6,
            recommended_present=2,
            recommended_total=4,
            incomplete_count=5,
            hypothesis_complete=True,
            rollback_complete=False,
            metrics_complete=False,
        )

        assert 20 < score < 60

    def test_incomplete_markers_reduce_score(self) -> None:
        """More incomplete markers reduce score."""
        score_clean = calculate_score(
            required_present=6,
            required_total=6,
            recommended_present=4,
            recommended_total=4,
            incomplete_count=0,
            hypothesis_complete=True,
            rollback_complete=True,
            metrics_complete=True,
        )

        score_dirty = calculate_score(
            required_present=6,
            required_total=6,
            recommended_present=4,
            recommended_total=4,
            incomplete_count=10,
            hypothesis_complete=True,
            rollback_complete=True,
            metrics_complete=True,
        )

        assert score_clean > score_dirty


class TestLoadDocument:
    """Tests for load_document function."""

    def test_loads_valid_markdown(self, tmp_path: Path) -> None:
        """Valid markdown file is loaded."""
        doc_path = tmp_path / "experiment.md"
        doc_path.write_text("# Test Document\n\nContent here.")

        content = load_document(doc_path)

        assert "# Test Document" in content

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        doc_path = tmp_path / "nonexistent.md"

        with pytest.raises(FileNotFoundError, match="not found"):
            load_document(doc_path)

    def test_wrong_extension_rejected(self, tmp_path: Path) -> None:
        """Non-markdown file raises ValueError."""
        doc_path = tmp_path / "experiment.txt"
        doc_path.write_text("Content")

        with pytest.raises(ValueError, match="Expected .md"):
            load_document(doc_path)


class TestValidateExperiment:
    """Tests for validate_experiment function."""

    @pytest.fixture
    def complete_experiment(self, tmp_path: Path) -> Path:
        """Create a complete experiment document."""
        content = """
# Chaos Experiment: API Gateway Resilience

## Metadata

| Field | Value |
|-------|-------|
| **Experiment ID** | chaos-20260118-api-gateway |
| **Owner** | Jane Doe |

## System Under Test

### Target System

- **Service/Component**: API Gateway
- **Environment**: staging

## Business Justification

### Objective

Test resilience of API Gateway under network partition.

## Steady State Baseline

### Metrics Collected

| Metric | Value | Green Threshold |
|--------|-------|-----------------|
| P99 Latency | 50ms | < 100ms |

## Hypothesis

Given the API Gateway in steady state with baseline metrics,
When we inject a network partition,
Then the system should gracefully degrade within 5 seconds,
Because circuit breakers will trip and fallback to cached responses.

## Injection Plan

### Failure Type

- **Category**: Network
- **Specific Failure**: Network partition

## Rollback Procedure

### Manual Rollback

```bash
kubectl delete pod troubled-pod
```

### Verification

Verify the rollback is complete.

## Approvals

| Role | Status |
|------|--------|
| Owner | APPROVED |

## Execution Log

Started execution at 10:00.

## Results

### Verdict

VALIDATED
"""
        doc_path = tmp_path / "complete.md"
        doc_path.write_text(content)
        return doc_path

    @pytest.fixture
    def minimal_experiment(self, tmp_path: Path) -> Path:
        """Create a minimal (incomplete) experiment document."""
        content = """
# Chaos Experiment: Test

## Metadata

Content TBD

## System Under Test

Content TBD
"""
        doc_path = tmp_path / "minimal.md"
        doc_path.write_text(content)
        return doc_path

    def test_complete_experiment_passes(self, complete_experiment: Path) -> None:
        """Complete experiment passes validation."""
        result = validate_experiment(complete_experiment)

        assert result.success is True
        assert result.score >= 80

    def test_incomplete_experiment_fails(self, minimal_experiment: Path) -> None:
        """Incomplete experiment fails validation."""
        result = validate_experiment(minimal_experiment)

        assert result.success is False
        assert len(result.errors) > 0

    def test_strict_mode_fails_on_tbd(self, minimal_experiment: Path) -> None:
        """Strict mode treats TBD as error."""
        result = validate_experiment(minimal_experiment, strict=True)

        assert result.success is False
        # In strict mode, TBD markers are errors
        assert any("TBD" in e for e in result.errors)

    def test_non_strict_mode_warns_on_tbd(self, minimal_experiment: Path) -> None:
        """Non-strict mode treats TBD as warning."""
        result = validate_experiment(minimal_experiment, strict=False)

        # TBD markers should be in warnings, not errors
        assert any("TBD" in w for w in result.warnings)

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file returns failure result."""
        result = validate_experiment(tmp_path / "missing.md")

        assert result.success is False
        assert result.score == 0
        assert any("not found" in e for e in result.errors)

    def test_score_reflects_completeness(
        self, complete_experiment: Path, minimal_experiment: Path
    ) -> None:
        """More complete documents score higher."""
        complete_result = validate_experiment(complete_experiment)
        minimal_result = validate_experiment(minimal_experiment)

        assert complete_result.score > minimal_result.score


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestGenerateExperimentCLI:
    """Integration tests for generate_experiment.py CLI."""

    @pytest.fixture
    def script_path(self) -> Path:
        """Return path to the script."""
        return SKILL_SCRIPTS_PATH / "generate_experiment.py"

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
        assert "--name" in result.stdout
        assert "--system" in result.stdout

    def test_missing_required_name_fails(self, script_path: Path) -> None:
        """Missing required --name argument fails."""
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode != 0
        assert "--name" in result.stderr

    def test_dry_run_prints_content(self, script_path: Path) -> None:
        """--dry-run prints content without saving."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--name",
                "Test Experiment",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Test Experiment" in result.stdout
        assert "## Metadata" in result.stdout

    def test_json_output(self, script_path: Path, tmp_path: Path) -> None:
        """--json flag produces JSON output."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--name",
                "Test Experiment",
                "--output",
                str(tmp_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert "path" in output["data"]

    def test_creates_file_with_parameters(self, script_path: Path, tmp_path: Path) -> None:
        """Script creates file with all parameters."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--name",
                "API Gateway Test",
                "--system",
                "Payment Service",
                "--owner",
                "Jane",
                "--output",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

        # Find the created file
        created_files = list(tmp_path.glob("*.md"))
        assert len(created_files) == 1

        content = created_files[0].read_text()
        assert "API Gateway Test" in content
        assert "Payment Service" in content
        assert "Jane" in content


class TestValidateExperimentCLI:
    """Integration tests for validate_experiment.py CLI."""

    @pytest.fixture
    def script_path(self) -> Path:
        """Return path to the script."""
        return SKILL_SCRIPTS_PATH / "validate_experiment.py"

    @pytest.fixture
    def valid_experiment(self, tmp_path: Path) -> Path:
        """Create a valid experiment document."""
        content = """
# Chaos Experiment: Test

## Metadata

| Field | Value |
|-------|-------|
| ID | chaos-123 |

## System Under Test

API Gateway

## Steady State Baseline

| Metric | Value | Green Threshold |
|--------|-------|-----------------|
| Latency | 50ms | < 100ms |

## Hypothesis

Given steady state, When failure, Then recovery, Because resilience.

## Injection Plan

Network partition injection.

## Rollback Procedure

```bash
kubectl rollback
```

Verify rollback complete.

## Business Justification

Validate resilience.

## Approvals

Approved by team.

## Execution Log

Log entries.

## Results

Validated.
"""
        doc_path = tmp_path / "valid.md"
        doc_path.write_text(content)
        return doc_path

    @pytest.fixture
    def invalid_experiment(self, tmp_path: Path) -> Path:
        """Create an invalid experiment document."""
        content = """
# Chaos Experiment: Test

Only a title, missing all required sections.
"""
        doc_path = tmp_path / "invalid.md"
        doc_path.write_text(content)
        return doc_path

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
        assert "path" in result.stdout
        assert "--strict" in result.stdout

    def test_valid_experiment_returns_0(self, script_path: Path, valid_experiment: Path) -> None:
        """Valid experiment returns exit code 0."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(valid_experiment)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_invalid_experiment_returns_10(
        self, script_path: Path, invalid_experiment: Path
    ) -> None:
        """Invalid experiment returns exit code 10."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(invalid_experiment)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 10
        assert "FAIL" in result.stdout

    def test_missing_file_returns_1(self, script_path: Path, tmp_path: Path) -> None:
        """Missing file returns exit code 1."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(tmp_path / "missing.md")],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Exit code should be 1 for general failure (file not found)
        assert result.returncode in (1, 10)
        assert "FAIL" in result.stdout or "not found" in result.stdout

    def test_json_output(self, script_path: Path, valid_experiment: Path) -> None:
        """--json flag produces JSON output."""
        result = subprocess.run(
            [sys.executable, str(script_path), str(valid_experiment), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert "score" in output
        assert "errors" in output
        assert "warnings" in output

    def test_strict_mode(self, script_path: Path, tmp_path: Path) -> None:
        """--strict mode treats incomplete markers as errors."""
        # Create document with TBD markers
        content = """
# Chaos Experiment: Test

## Metadata
Owner: TBD

## System Under Test
System: TBD

## Steady State Baseline
TBD

## Hypothesis
TBD

## Injection Plan
TBD

## Rollback Procedure
TBD
"""
        doc_path = tmp_path / "tbd.md"
        doc_path.write_text(content)

        result = subprocess.run(
            [sys.executable, str(script_path), str(doc_path), "--strict"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Strict mode should fail on TBD markers
        assert result.returncode == 10


class TestConstants:
    """Tests for module constants."""

    def test_required_sections_count(self) -> None:
        """REQUIRED_SECTIONS contains expected number of sections."""
        assert len(REQUIRED_SECTIONS) == 6

    def test_required_sections_names(self) -> None:
        """REQUIRED_SECTIONS contains expected section names."""
        names = [name for name, _ in REQUIRED_SECTIONS]

        assert "Metadata" in names
        assert "System Under Test" in names
        assert "Steady State Baseline" in names
        assert "Hypothesis" in names
        assert "Injection Plan" in names
        assert "Rollback Procedure" in names

    def test_recommended_sections_count(self) -> None:
        """RECOMMENDED_SECTIONS contains expected number of sections."""
        assert len(RECOMMENDED_SECTIONS) == 4

    def test_incomplete_patterns_count(self) -> None:
        """INCOMPLETE_PATTERNS contains expected number of patterns."""
        assert len(INCOMPLETE_PATTERNS) == 4


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_document(self, tmp_path: Path) -> None:
        """Empty document fails gracefully."""
        doc_path = tmp_path / "empty.md"
        doc_path.write_text("")

        result = validate_experiment(doc_path)

        assert result.success is False
        assert len(result.errors) > 0

    def test_unicode_content(self, tmp_path: Path) -> None:
        """Unicode content is handled correctly."""
        content = """
# Chaos Experiment: Unicode Test

## Metadata

Owner: Jean-Pierre Caf\u00e9

## System Under Test

\u30b5\u30fc\u30d3\u30b9 (Service)

## Steady State Baseline

Metric: 50ms

## Hypothesis

Given the system, When failure, Then recovery, Because resilience.

## Injection Plan

Inject \u5931\u8d25 (failure).

## Rollback Procedure

```bash
rollback
```

Verify complete.
"""
        doc_path = tmp_path / "unicode.md"
        doc_path.write_text(content, encoding="utf-8")

        result = validate_experiment(doc_path)

        # Should not crash on unicode
        assert result is not None
        assert isinstance(result.success, bool)

    def test_very_long_document(self, tmp_path: Path) -> None:
        """Very long document is handled without timeout."""
        base_content = """
# Chaos Experiment: Long Test

## Metadata
ID: test

## System Under Test
System

## Steady State Baseline
Metric: 50ms

## Hypothesis
Given, When, Then, Because.

## Injection Plan
Plan

## Rollback Procedure
```bash
cmd
```
Verify.
"""
        # Add lots of content
        long_content = base_content + ("\n\nParagraph. " * 10000)
        doc_path = tmp_path / "long.md"
        doc_path.write_text(long_content)

        result = validate_experiment(doc_path)

        # Should complete without timeout
        assert result is not None
