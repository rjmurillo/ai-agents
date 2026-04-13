"""Tests for test_result_helpers module.

Migrated from TestResultHelpers.Tests.ps1 per ADR-042.
Tests the create_skipped_test_result function for generating JUnit XML
files when tests are skipped in CI workflows.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.test_result_helpers import create_skipped_test_result


class TestFileCreation:
    """Tests for file creation behavior."""

    def test_creates_file_at_specified_path(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        result = create_skipped_test_result(output)

        assert result is not None
        assert output.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        output = tmp_path / "nested" / "subdir" / "results.xml"

        create_skipped_test_result(output)

        assert output.exists()

    def test_returns_path_object(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        result = create_skipped_test_result(output)

        assert isinstance(result, Path)
        assert result.name == "results.xml"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"
        output.write_text("existing content", encoding="utf-8")

        create_skipped_test_result(output)

        content = output.read_text(encoding="utf-8")
        assert "existing content" not in content
        assert "testsuites" in content


class TestXmlContent:
    """Tests for XML content correctness."""

    def test_produces_valid_xml(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output)

        content = output.read_text(encoding="utf-8")
        ET.fromstring(content)  # Raises ParseError if invalid

    def test_contains_correct_xml_declaration(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output)

        content = output.read_text(encoding="utf-8")
        assert content.startswith('<?xml version="1.0" encoding="utf-8"?>')

    def test_testsuites_has_zero_counts(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output)

        tree = ET.parse(output)
        root = tree.getroot()
        assert root.tag == "testsuites"
        assert root.get("tests") == "0"
        assert root.get("failures") == "0"
        assert root.get("errors") == "0"
        assert root.get("time") == "0"

    def test_testsuite_has_zero_counts(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output)

        tree = ET.parse(output)
        testsuite = tree.find("testsuite")
        assert testsuite is not None
        assert testsuite.get("tests") == "0"
        assert testsuite.get("failures") == "0"
        assert testsuite.get("errors") == "0"
        assert testsuite.get("time") == "0"

    def test_uses_default_test_suite_name(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output)

        tree = ET.parse(output)
        testsuite = tree.find("testsuite")
        assert testsuite is not None
        assert testsuite.get("name") == "Tests (Skipped)"

    def test_uses_custom_test_suite_name(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output, test_suite_name="Pester Tests (Skipped)")

        tree = ET.parse(output)
        testsuite = tree.find("testsuite")
        assert testsuite is not None
        assert testsuite.get("name") == "Pester Tests (Skipped)"

    def test_uses_default_skip_reason(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output)

        content = output.read_text(encoding="utf-8")
        assert "No testable files changed - tests skipped" in content

    def test_uses_custom_skip_reason(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output, skip_reason="Custom skip reason")

        content = output.read_text(encoding="utf-8")
        assert "Custom skip reason" in content

    def test_escapes_double_hyphen_in_skip_reason(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"

        create_skipped_test_result(output, skip_reason="Test--reason--with--hyphens")

        content = output.read_text(encoding="utf-8")
        assert "Test- -reason- -with- -hyphens" in content
        assert "Test--reason" not in content
        # Verify still valid XML
        ET.fromstring(content)


class TestParameterValidation:
    """Tests for input validation."""

    def test_raises_on_empty_output_path(self) -> None:
        with pytest.raises(ValueError, match="output_path must not be empty or None"):
            create_skipped_test_result("")

    def test_raises_on_empty_test_suite_name(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"
        with pytest.raises(ValueError, match="test_suite_name must not be empty"):
            create_skipped_test_result(output, test_suite_name="")

    def test_raises_on_empty_skip_reason(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"
        with pytest.raises(ValueError, match="skip_reason must not be empty"):
            create_skipped_test_result(output, skip_reason="")


class TestPathSecurity:
    """Security tests for CWE-22 path traversal prevention."""

    def test_rejects_relative_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Relative path traversal"):
            create_skipped_test_result("../../etc/evil.xml")

    def test_allows_absolute_path(self, tmp_path: Path) -> None:
        output = tmp_path / "results.xml"
        result = create_skipped_test_result(str(output.resolve()))
        assert result.exists()

    def test_allows_relative_path_without_traversal(self, tmp_path: Path) -> None:
        output = tmp_path / "subdir" / "results.xml"
        result = create_skipped_test_result(output)
        assert result.exists()


class TestRealWorldPatterns:
    """Tests matching real CI workflow usage patterns."""

    def test_pester_skip_format(self, tmp_path: Path) -> None:
        output = tmp_path / "pester-results.xml"

        create_skipped_test_result(
            output,
            test_suite_name="Pester Tests (Skipped)",
            skip_reason="No testable files changed - tests skipped",
        )

        content = output.read_text(encoding="utf-8")
        assert 'name="Pester Tests (Skipped)"' in content
        assert "No testable files changed - tests skipped" in content

    def test_psscriptanalyzer_skip_format(self, tmp_path: Path) -> None:
        output = tmp_path / "psscriptanalyzer-results.xml"

        create_skipped_test_result(
            output,
            test_suite_name="PSScriptAnalyzer (Skipped)",
            skip_reason="No PowerShell files changed - analysis skipped",
        )

        content = output.read_text(encoding="utf-8")
        assert 'name="PSScriptAnalyzer (Skipped)"' in content
        assert "No PowerShell files changed - analysis skipped" in content
