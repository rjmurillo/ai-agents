"""Tests for validate_session_json module.

These tests verify the session log validation functionality used for
protocol compliance. This is a pilot migration from Validate-SessionJson.ps1
per ADR-042.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scripts.validate_session_json import (
    BRANCH_PATTERN,
    COMMIT_SHA_PATTERN,
    REQUIRED_SESSION_FIELDS,
    ValidationResult,
    get_case_insensitive,
    has_case_insensitive,
    load_session_file,
    validate_protocol_compliance,
    validate_session_end,
    validate_session_log,
    validate_session_section,
    validate_session_start,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


class TestConstants:
    """Tests for module constants."""

    def test_required_session_fields(self) -> None:
        """REQUIRED_SESSION_FIELDS contains expected values."""
        expected = {"number", "date", "branch", "startingCommit", "objective"}
        assert REQUIRED_SESSION_FIELDS == expected

    def test_branch_pattern_matches_conventional(self) -> None:
        """BRANCH_PATTERN matches conventional branch names."""
        valid_branches = [
            "feat/new-feature",
            "fix/bug-123",
            "docs/update-readme",
            "chore/cleanup",
            "refactor/code-cleanup",
            "test/add-tests",
            "ci/update-workflow",
        ]
        for branch in valid_branches:
            assert BRANCH_PATTERN.match(branch), f"Expected to match: {branch}"

    def test_branch_pattern_rejects_invalid(self) -> None:
        """BRANCH_PATTERN rejects invalid branch names."""
        invalid_branches = [
            "main",
            "feature/something",
            "bugfix/something",
            "my-branch",
        ]
        for branch in invalid_branches:
            assert not BRANCH_PATTERN.match(branch), f"Expected to not match: {branch}"

    def test_commit_sha_pattern_matches_valid(self) -> None:
        """COMMIT_SHA_PATTERN matches valid SHA formats."""
        valid_shas = [
            "abcdef1",  # 7 chars
            "1234567890abcdef1234567890abcdef12345678",  # 40 chars
            "abc1234",
        ]
        for sha in valid_shas:
            assert COMMIT_SHA_PATTERN.match(sha), f"Expected to match: {sha}"

    def test_commit_sha_pattern_rejects_invalid(self) -> None:
        """COMMIT_SHA_PATTERN rejects invalid formats."""
        invalid_shas = [
            "abc",  # Too short
            "xyz123",  # Invalid chars
            "1234567890abcdef1234567890abcdef1234567890",  # 41 chars
        ]
        for sha in invalid_shas:
            assert not COMMIT_SHA_PATTERN.match(sha), f"Expected to not match: {sha}"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_is_valid(self) -> None:
        """Empty result is valid."""
        result = ValidationResult()

        assert result.is_valid
        assert result.errors == []
        assert result.warnings == []

    def test_with_errors_is_invalid(self) -> None:
        """Result with errors is invalid."""
        result = ValidationResult(errors=["Error 1"])

        assert not result.is_valid

    def test_with_warnings_only_is_valid(self) -> None:
        """Result with only warnings is still valid."""
        result = ValidationResult(warnings=["Warning 1"])

        assert result.is_valid


class TestCaseInsensitiveHelpers:
    """Tests for case-insensitive dictionary helpers."""

    def test_get_case_insensitive_exact_match(self) -> None:
        """get_case_insensitive finds exact match."""
        data = {"Key": "value"}

        assert get_case_insensitive(data, "Key") == "value"

    def test_get_case_insensitive_different_case(self) -> None:
        """get_case_insensitive finds different case match."""
        data = {"KEY": "value"}

        assert get_case_insensitive(data, "key") == "value"

    def test_get_case_insensitive_not_found(self) -> None:
        """get_case_insensitive returns None when not found."""
        data = {"other": "value"}

        assert get_case_insensitive(data, "key") is None

    def test_has_case_insensitive_found(self) -> None:
        """has_case_insensitive returns True when found."""
        data = {"Key": "value"}

        assert has_case_insensitive(data, "KEY")

    def test_has_case_insensitive_not_found(self) -> None:
        """has_case_insensitive returns False when not found."""
        data = {"other": "value"}

        assert not has_case_insensitive(data, "key")


class TestValidateSessionSection:
    """Tests for validate_session_section function."""

    def test_valid_session(self) -> None:
        """Valid session passes validation."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            "branch": "feat/test",
            "startingCommit": "abcdef1",
            "objective": "Test objective",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert result.is_valid
        assert len(result.warnings) == 0

    def test_missing_required_field(self) -> None:
        """Missing required field causes error."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            # Missing branch, startingCommit, objective
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert not result.is_valid
        assert "Missing: session.branch" in result.errors

    def test_invalid_branch_name_warning(self) -> None:
        """Invalid branch name causes warning."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            "branch": "my-feature",  # Invalid
            "startingCommit": "abcdef1",
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        # Still valid, but has warning
        assert result.is_valid
        assert any("conventional naming" in w for w in result.warnings)

    def test_invalid_commit_sha(self) -> None:
        """Invalid commit SHA causes error."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            "branch": "feat/test",
            "startingCommit": "invalid!",  # Invalid
            "objective": "Test",
        }
        result = ValidationResult()

        validate_session_section(session, result)

        assert not result.is_valid
        assert any("Invalid commit SHA" in e for e in result.errors)


class TestValidateSessionStart:
    """Tests for validate_session_start function."""

    def test_complete_must_items(self) -> None:
        """Complete MUST items pass validation."""
        session_start = {
            "serenaActivated": {"complete": True, "evidence": "Evidence", "level": "MUST"},
        }
        result = ValidationResult()

        validate_session_start(session_start, result)

        assert result.is_valid

    def test_incomplete_must_item(self) -> None:
        """Incomplete MUST item causes error."""
        session_start = {
            "serenaActivated": {"complete": False, "evidence": "", "level": "MUST"},
        }
        result = ValidationResult()

        validate_session_start(session_start, result)

        assert not result.is_valid
        assert "Incomplete MUST" in result.errors[0]

    def test_missing_evidence_warning(self) -> None:
        """Missing evidence on complete MUST causes warning."""
        session_start = {
            "serenaActivated": {"complete": True, "evidence": "", "level": "MUST"},
        }
        result = ValidationResult()

        validate_session_start(session_start, result)

        # Still valid, but has warning
        assert result.is_valid
        assert any("Missing evidence" in w for w in result.warnings)


class TestValidateSessionEnd:
    """Tests for validate_session_end function."""

    def test_valid_session_end(self) -> None:
        """Valid session end passes validation."""
        session_end = {
            "checklistComplete": {"complete": True, "evidence": "Done", "level": "MUST"},
        }
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert result.is_valid

    def test_must_not_violation(self) -> None:
        """MUST NOT violation causes error."""
        session_end = {
            "handoffNotUpdated": {"complete": True, "level": "MUST NOT"},  # Violated!
        }
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert not result.is_valid
        assert any("MUST NOT violated" in e for e in result.errors)


class TestValidateProtocolCompliance:
    """Tests for validate_protocol_compliance function."""

    def test_missing_session_start(self) -> None:
        """Missing sessionStart causes error."""
        protocol = {"sessionEnd": {}}
        result = ValidationResult()

        validate_protocol_compliance(protocol, result)

        assert not result.is_valid
        assert "Missing: protocolCompliance.sessionStart" in result.errors

    def test_missing_session_end(self) -> None:
        """Missing sessionEnd causes error."""
        protocol = {"sessionStart": {}}
        result = ValidationResult()

        validate_protocol_compliance(protocol, result)

        assert not result.is_valid
        assert "Missing: protocolCompliance.sessionEnd" in result.errors

    def test_both_sections_present(self) -> None:
        """Both sections present passes section validation."""
        protocol = {
            "sessionStart": {},
            "sessionEnd": {},
        }
        result = ValidationResult()

        validate_protocol_compliance(protocol, result)

        # No section-level errors
        assert "Missing: protocolCompliance.sessionStart" not in result.errors
        assert "Missing: protocolCompliance.sessionEnd" not in result.errors


class TestValidateSessionLog:
    """Tests for validate_session_log function."""

    def test_valid_minimal_log(self) -> None:
        """Valid minimal log passes validation."""
        data = {
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test",
            },
            "protocolCompliance": {
                "sessionStart": {},
                "sessionEnd": {},
            },
        }

        result = validate_session_log(data)

        assert result.is_valid

    def test_missing_session_section(self) -> None:
        """Missing session section causes error."""
        data = {
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid
        assert "Missing: session" in result.errors

    def test_missing_protocol_section(self) -> None:
        """Missing protocolCompliance section causes error."""
        data = {
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test",
            },
        }

        result = validate_session_log(data)

        assert not result.is_valid
        assert "Missing: protocolCompliance" in result.errors


class TestLoadSessionFile:
    """Tests for load_session_file function."""

    def test_loads_valid_json(self, tmp_path: Path) -> None:
        """Loads valid JSON file successfully."""
        session_file = tmp_path / "session.json"
        session_file.write_text('{"test": "value"}')

        data, error = load_session_file(session_file)

        assert error is None
        assert data == {"test": "value"}

    def test_error_for_missing_file(self, tmp_path: Path) -> None:
        """Returns error for missing file."""
        session_file = tmp_path / "nonexistent.json"

        data, error = load_session_file(session_file)

        assert data is None
        assert "not found" in error

    def test_error_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns error for invalid JSON."""
        session_file = tmp_path / "invalid.json"
        session_file.write_text('{"invalid": }')

        data, error = load_session_file(session_file)

        assert data is None
        assert "Invalid JSON" in error
        assert "line" in error
        assert "Common fixes" in error


class TestMainFunction:
    """Tests for main() function via monkeypatching."""

    @pytest.fixture
    def valid_session_file(self, tmp_path: Path) -> Path:
        """Create a valid session log file."""
        data = {
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test objective",
            },
            "protocolCompliance": {
                "sessionStart": {},
                "sessionEnd": {},
            },
        }
        session_file = tmp_path / "valid-session.json"
        session_file.write_text(json.dumps(data))
        return session_file

    @pytest.fixture
    def invalid_session_file(self, tmp_path: Path) -> Path:
        """Create an invalid session log file."""
        data = {
            # Missing session section
            "protocolCompliance": {},
        }
        session_file = tmp_path / "invalid-session.json"
        session_file.write_text(json.dumps(data))
        return session_file

    def test_main_valid_session(
        self,
        valid_session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 0 for valid session."""
        from scripts import validate_session_json

        # Allow temp directory paths for testing
        monkeypatch.setattr(
            validate_session_json, "_PROJECT_ROOT", valid_session_file.parent
        )
        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(valid_session_file)],
        )

        result = validate_session_json.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out

    def test_main_invalid_session(
        self,
        invalid_session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 1 for invalid session."""
        from scripts import validate_session_json

        # Allow temp directory paths for testing
        monkeypatch.setattr(
            validate_session_json, "_PROJECT_ROOT", invalid_session_file.parent
        )
        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(invalid_session_file)],
        )

        result = validate_session_json.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out

    def test_main_pre_commit_mode(
        self,
        invalid_session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with --pre-commit uses compact output."""
        from scripts import validate_session_json

        # Allow temp directory paths for testing
        monkeypatch.setattr(
            validate_session_json, "_PROJECT_ROOT", invalid_session_file.parent
        )
        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(invalid_session_file), "--pre-commit"],
        )

        result = validate_session_json.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        # Pre-commit mode should not show the full header
        assert "===" not in captured.out

    def test_main_missing_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() returns 1 for missing file."""
        from scripts import validate_session_json

        monkeypatch.setattr(
            "sys.argv",
            ["validate_session_json.py", str(tmp_path / "nonexistent.json")],
        )

        result = validate_session_json.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err


class TestScriptIntegration:
    """Integration tests for the script as a CLI tool."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the script."""
        return project_root / "scripts" / "validate_session_json.py"

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
        assert "session_path" in result.stdout
        assert "--pre-commit" in result.stdout

    def test_validates_real_session(self, script_path: Path, project_root: Path) -> None:
        """Script validates real session files."""
        # Find a real session file
        sessions_dir = project_root / ".agents" / "sessions"
        session_files = list(sessions_dir.glob("*.json"))

        if not session_files:
            pytest.skip("No session files found")

        result = subprocess.run(
            [sys.executable, str(script_path), str(session_files[0])],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should complete (pass or fail, but not crash)
        assert result.returncode in (0, 1)


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_session_object(self) -> None:
        """Empty session object fails validation."""
        data = {
            "session": {},
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid
        # Should have multiple missing field errors
        assert len(result.errors) >= 5

    def test_null_values_in_session(self) -> None:
        """Null values treated as missing."""
        data = {
            "session": {
                "number": None,
                "date": None,
                "branch": None,
                "startingCommit": None,
                "objective": None,
            },
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid

    def test_extra_fields_allowed(self) -> None:
        """Extra fields in session do not cause errors."""
        data = {
            "schema": "session-protocol-v1.4",
            "session": {
                "number": 1,
                "date": "2026-01-18",
                "branch": "feat/test",
                "startingCommit": "abcdef1",
                "objective": "Test",
                "extraField": "allowed",
            },
            "protocolCompliance": {
                "sessionStart": {},
                "sessionEnd": {},
            },
            "workLog": [],
            "decisions": [],
            "outcome": {},
        }

        result = validate_session_log(data)

        assert result.is_valid
