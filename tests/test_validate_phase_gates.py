"""Tests for validate_phase_gates module.

Tests verify SPARC development phase gate validation for session logs.
See .agents/governance/sparc-methodology.md for phase definitions.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_phase_gates import (
    PHASE_ORDER,
    VALID_ENTRY_PHASES,
    VALID_GATE_STATUSES,
    VALID_PHASES,
    validate_phase_data,
    validate_session_file,
)


class TestConstants:
    """Tests for module constants."""

    def test_valid_phases_count(self) -> None:
        """Five SPARC phases defined."""
        assert len(VALID_PHASES) == 5

    def test_phase_order_matches_valid_phases(self) -> None:
        """PHASE_ORDER contains exactly the valid phases."""
        assert set(PHASE_ORDER) == VALID_PHASES

    def test_phase_order_sequence(self) -> None:
        """Phases follow SPARC order."""
        expected = [
            "specification",
            "pseudocode",
            "architecture",
            "refinement",
            "completion",
        ]
        assert PHASE_ORDER == expected

    def test_valid_entry_phases(self) -> None:
        """Entry phases are a subset of valid phases."""
        assert VALID_ENTRY_PHASES <= VALID_PHASES

    def test_valid_gate_statuses(self) -> None:
        """Gate statuses include expected values."""
        assert "passed" in VALID_GATE_STATUSES
        assert "failed" in VALID_GATE_STATUSES
        assert "in_progress" in VALID_GATE_STATUSES
        assert "skipped" in VALID_GATE_STATUSES


class TestValidatePhaseData:
    """Tests for validate_phase_data function."""

    def test_valid_minimal(self) -> None:
        """Minimal valid phase data: current phase only."""
        result = validate_phase_data({"current": "specification"})
        assert result.is_valid

    def test_valid_with_history(self) -> None:
        """Valid phase data with history."""
        data = {
            "current": "refinement",
            "history": [
                {"phase": "specification", "gate": "passed"},
                {"phase": "pseudocode", "gate": "passed"},
                {"phase": "architecture", "gate": "passed"},
                {"phase": "refinement", "gate": "in_progress"},
            ],
        }
        result = validate_phase_data(data)
        assert result.is_valid

    def test_missing_current(self) -> None:
        """Missing current phase produces error."""
        result = validate_phase_data({})
        assert not result.is_valid
        assert any("current is required" in e for e in result.errors)

    def test_invalid_current_phase(self) -> None:
        """Invalid current phase name produces error."""
        result = validate_phase_data({"current": "invalid_phase"})
        assert not result.is_valid
        assert any("Invalid phase" in e for e in result.errors)

    def test_invalid_history_type(self) -> None:
        """Non-array history produces error."""
        result = validate_phase_data({"current": "specification", "history": "not-a-list"})
        assert not result.is_valid
        assert any("must be an array" in e for e in result.errors)

    def test_backward_phase_produces_error(self) -> None:
        """Phases going backward in history produce error."""
        data = {
            "current": "specification",
            "history": [
                {"phase": "architecture", "gate": "passed"},
                {"phase": "pseudocode", "gate": "in_progress"},
            ],
        }
        result = validate_phase_data(data)
        assert not result.is_valid
        assert any("must progress forward" in e for e in result.errors)

    def test_invalid_gate_status(self) -> None:
        """Invalid gate status produces error."""
        data = {
            "current": "specification",
            "history": [
                {"phase": "specification", "gate": "unknown"},
            ],
        }
        result = validate_phase_data(data)
        assert not result.is_valid
        assert any("invalid gate status" in e for e in result.errors)

    def test_missing_phase_in_history_entry(self) -> None:
        """Missing phase field in history entry produces error."""
        data = {
            "current": "specification",
            "history": [
                {"gate": "passed"},
            ],
        }
        result = validate_phase_data(data)
        assert not result.is_valid
        assert any("missing 'phase'" in e for e in result.errors)

    def test_quick_fix_entry_at_refinement(self) -> None:
        """Quick fix entering at refinement is valid."""
        data = {
            "current": "refinement",
            "history": [
                {"phase": "refinement", "gate": "in_progress"},
            ],
        }
        result = validate_phase_data(data)
        assert result.is_valid

    def test_docs_only_entry_at_completion(self) -> None:
        """Documentation-only entering at completion is valid."""
        data = {
            "current": "completion",
            "history": [
                {"phase": "completion", "gate": "in_progress"},
            ],
        }
        result = validate_phase_data(data)
        assert result.is_valid

    def test_non_standard_entry_phase_produces_warning(self) -> None:
        """Entering at pseudocode (non-standard) produces warning."""
        data = {
            "current": "pseudocode",
            "history": [
                {"phase": "pseudocode", "gate": "in_progress"},
            ],
        }
        result = validate_phase_data(data)
        assert result.is_valid  # Warning, not error
        assert any("not a standard entry phase" in w for w in result.warnings)

    def test_history_mismatch_current_produces_warning(self) -> None:
        """Last history phase not matching current produces warning."""
        data = {
            "current": "refinement",
            "history": [
                {"phase": "specification", "gate": "passed"},
            ],
        }
        result = validate_phase_data(data)
        assert result.is_valid  # Warning, not error
        assert any("does not match" in w for w in result.warnings)

    def test_empty_history_is_valid(self) -> None:
        """Empty history array is valid."""
        data = {"current": "specification", "history": []}
        result = validate_phase_data(data)
        assert result.is_valid

    def test_all_phases_in_order(self) -> None:
        """Full phase sequence passes validation."""
        data = {
            "current": "completion",
            "history": [
                {"phase": "specification", "gate": "passed"},
                {"phase": "pseudocode", "gate": "passed"},
                {"phase": "architecture", "gate": "passed"},
                {"phase": "refinement", "gate": "passed"},
                {"phase": "completion", "gate": "in_progress"},
            ],
        }
        result = validate_phase_data(data)
        assert result.is_valid
        assert len(result.errors) == 0


def _make_session_log(**extra: object) -> dict:
    """Build a minimal valid session log with optional extra fields."""
    base = {
        "session": {
            "number": 1,
            "date": "2026-01-15",
            "branch": "feat/test",
            "startingCommit": "abc1234",
            "objective": "test",
        },
        "protocolCompliance": {
            "sessionStart": {},
            "sessionEnd": {},
        },
    }
    base.update(extra)
    return base


class TestValidateSessionFile:
    """Tests for validate_session_file with actual JSON files."""

    def test_no_phase_data_is_valid(self, tmp_path: Path) -> None:
        """Session log without developmentPhase passes."""
        log = _make_session_log()
        file_path = tmp_path / "session.json"
        file_path.write_text(json.dumps(log))
        result = validate_session_file(file_path)
        assert result.is_valid

    def test_valid_phase_data_in_file(self, tmp_path: Path) -> None:
        """Session log with valid developmentPhase passes."""
        phase = {
            "current": "refinement",
            "history": [
                {"phase": "specification", "gate": "passed"},
                {"phase": "refinement", "gate": "in_progress"},
            ],
        }
        log = _make_session_log(developmentPhase=phase)
        file_path = tmp_path / "session.json"
        file_path.write_text(json.dumps(log))
        result = validate_session_file(file_path)
        assert result.is_valid

    def test_invalid_json_produces_error(self, tmp_path: Path) -> None:
        """Invalid JSON file produces error."""
        file_path = tmp_path / "bad.json"
        file_path.write_text("not valid json{")
        result = validate_session_file(file_path)
        assert not result.is_valid
        assert any("Invalid JSON" in e for e in result.errors)

    def test_invalid_phase_data_in_file(self, tmp_path: Path) -> None:
        """Session log with invalid phase data fails."""
        log = _make_session_log(developmentPhase={"current": "bogus"})
        file_path = tmp_path / "session.json"
        file_path.write_text(json.dumps(log))
        result = validate_session_file(file_path)
        assert not result.is_valid

    def test_non_object_phase_data(self, tmp_path: Path) -> None:
        """developmentPhase as non-object produces error."""
        log = _make_session_log(developmentPhase="not-an-object")
        file_path = tmp_path / "session.json"
        file_path.write_text(json.dumps(log))
        result = validate_session_file(file_path)
        assert not result.is_valid
        assert any("must be an object" in e for e in result.errors)
