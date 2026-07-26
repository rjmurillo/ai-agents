"""Tests for validate_session_json module.

These tests verify the session log validation functionality used for
protocol compliance. This is a pilot migration from Validate-SessionJson.ps1
per ADR-042.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from scripts.validate_session_json import (
    _INCOMPLETE_MUST_PREFIX,
    _LEGACY_HANDOFF_FIELD,
    _MISSING_REQUIRED_PREFIX,
    _MUST_NOT_VIOLATED_PREFIX,
    BRANCH_PATTERN,
    COMMIT_SHA_PATTERN,
    CONTRADICTION_PATTERNS,
    SESSION_END_REQUIRED_ITEMS,
    SESSION_START_REQUIRED_ITEMS,
    ValidationResult,
    build_summary,
    count_must_failures,
    filename_session_number,
    get_case_insensitive,
    has_case_insensitive,
    load_session_file,
    validate_checklist_section,
    validate_filename_number,
    validate_protocol_compliance,
    validate_session_end,
    validate_session_log,
    validate_session_section,
    validate_session_start,
)


def _make_complete_start_section(**overrides: dict) -> dict:
    """Build a sessionStart section with all required items complete."""
    section = {
        name: {"complete": True, "evidence": "Evidence", "level": "MUST"}
        for name in SESSION_START_REQUIRED_ITEMS
    }
    section.update(overrides)
    return section


def _make_complete_end_section(**overrides: dict) -> dict:
    """Build a sessionEnd section with all required items complete."""
    section = {
        name: {"complete": True, "evidence": "Evidence", "level": "MUST"}
        for name in SESSION_END_REQUIRED_ITEMS
    }
    # handoffPreserved is MUST: complete=True means HANDOFF.md was not modified
    section["handoffPreserved"] = {
        "complete": True,
        "evidence": "HANDOFF.md not modified",
        "level": "MUST",
    }
    section.update(overrides)
    return section


if TYPE_CHECKING:
    from collections.abc import Iterator

    from _pytest.capture import CaptureFixture


_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scratch() -> Iterator[Path]:
    """A throwaway directory inside the repo.

    `validate_safe_path` rejects any path outside the project root, so a
    `tmp_path` fixture would make every CLI case exit 1 for a path reason and
    prove nothing about the load or the schema.
    """
    with tempfile.TemporaryDirectory(dir=_REPO_ROOT) as name:
        yield Path(name)


def _run_cli(path: Path) -> subprocess.CompletedProcess[str]:
    """Drive the validator as the hooks and the workflow drive it."""
    return subprocess.run(
        [sys.executable, "scripts/validate_session_json.py", str(path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class TestConstants:
    """Tests for module constants."""

    def test_the_schema_requires_the_session_fields_the_protocol_names(self) -> None:
        """The schema is the only enforcer of session shape, so pin what it requires.

        This replaces an assertion on a Python constant that duplicated the
        schema's own ``required`` list. The constant was deleted once the
        duplicate presence check went with it; a test that echoes a literal back
        at itself catches nothing.
        """
        import scripts.validate_session_json as vsj

        schema = json.loads(vsj.SCHEMA_PATH.read_text(encoding="utf-8"))

        assert set(schema["properties"]["session"]["required"]) == {
            "number",
            "date",
            "branch",
            "startingCommit",
            "objective",
        }

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

    def test_missing_required_field_defers_to_schema(self) -> None:
        """Missing required fields are NOT reported here; schema owns shape."""
        session = {
            "number": 1,
            "date": "2026-01-18",
            # Missing branch, startingCommit, objective
        }
        result = ValidationResult()

        validate_session_section(session, result)

        # No errors from validate_session_section; schema validation catches these
        assert result.is_valid
        assert not any("Missing: session." in e for e in result.errors)

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
        session_start = _make_complete_start_section()
        result = ValidationResult()

        validate_session_start(session_start, result)

        assert result.is_valid

    def test_incomplete_must_item(self) -> None:
        """Incomplete MUST item causes error."""
        session_start = _make_complete_start_section(
            serenaActivated={"complete": False, "evidence": "", "level": "MUST"},
        )
        result = ValidationResult()

        validate_session_start(session_start, result)

        assert not result.is_valid
        assert any("Incomplete MUST" in e for e in result.errors)

    def test_missing_evidence_warning(self) -> None:
        """Missing evidence on complete MUST causes warning."""
        session_start = _make_complete_start_section(
            serenaActivated={"complete": True, "evidence": "", "level": "MUST"},
        )
        result = ValidationResult()

        validate_session_start(session_start, result)

        # Still valid, but has warning
        assert result.is_valid
        assert any("Missing evidence" in w for w in result.warnings)


class TestValidateSessionEnd:
    """Tests for validate_session_end function."""

    def test_valid_session_end(self) -> None:
        """Valid session end passes validation."""
        session_end = _make_complete_end_section()
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert result.is_valid

    def test_handoff_preserved_satisfied(self) -> None:
        """handoffPreserved with Complete=true passes (issue #868)."""
        session_end = _make_complete_end_section()
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert result.is_valid

    def test_handoff_preserved_violated(self) -> None:
        """handoffPreserved with Complete=false fails (issue #868)."""
        session_end = _make_complete_end_section(
            handoffPreserved={
                "complete": False,
                "evidence": "HANDOFF.md was modified",
                "level": "MUST",
            },
        )
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert not result.is_valid
        assert any("Incomplete MUST" in e for e in result.errors)

    def test_legacy_handoff_not_updated_satisfied(self) -> None:
        """Legacy handoffNotUpdated with Complete=false passes (backward compat)."""
        session_end = _make_complete_end_section()
        # Replace handoffPreserved with legacy field
        del session_end["handoffPreserved"]
        session_end["handoffNotUpdated"] = {"complete": False, "level": "MUST NOT"}
        result = ValidationResult()

        validate_session_end(session_end, result)

        # handoffNotUpdated is not in SESSION_END_REQUIRED_ITEMS but is
        # picked up by validate_checklist_section as MUST NOT level item.
        # Complete=false for MUST NOT is the satisfied state, and the legacy
        # backward-compat check should not flag it as a violation.
        assert result.is_valid

    def test_legacy_handoff_not_updated_violated(self) -> None:
        """Legacy handoffNotUpdated with Complete=true fails (backward compat)."""
        session_end = _make_complete_end_section()
        # Replace handoffPreserved with violated legacy field
        del session_end["handoffPreserved"]
        session_end["handoffNotUpdated"] = {"complete": True, "level": "MUST NOT"}
        result = ValidationResult()

        validate_session_end(session_end, result)

        assert not result.is_valid
        assert any("MUST NOT violated" in e for e in result.errors)

    def test_session_end_must_items_uses_handoff_preserved(self) -> None:
        """SESSION_END_REQUIRED_ITEMS uses handoffPreserved (not legacy name)."""
        assert "handoffPreserved" in SESSION_END_REQUIRED_ITEMS
        assert _LEGACY_HANDOFF_FIELD not in SESSION_END_REQUIRED_ITEMS


class TestChecklistSectionValidation:
    """Tests for validate_checklist_section - the core fix for issue #1028."""

    def test_unknown_must_item_incomplete_causes_error(self) -> None:
        """MUST items NOT in the required set are still validated."""
        section_data = {
            "usageMandatoryRead": {"complete": False, "evidence": "", "level": "MUST"},
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert not result.is_valid
        assert any("usageMandatoryRead" in e for e in result.errors)

    def test_unknown_must_item_complete_passes(self) -> None:
        """Complete MUST items NOT in the required set pass validation."""
        section_data = {
            "customMustItem": {"complete": True, "evidence": "Done", "level": "MUST"},
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert result.is_valid

    def test_should_items_not_checked_as_must(self) -> None:
        """SHOULD items that are incomplete do not cause errors."""
        section_data = {
            "optionalItem": {"complete": False, "evidence": "", "level": "SHOULD"},
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert result.is_valid

    def test_missing_required_item_causes_error(self) -> None:
        """Required item absent from section_data causes an error."""
        section_data = {
            "someOtherItem": {"complete": True, "evidence": "Done", "level": "MUST"},
        }
        result = ValidationResult()

        validate_checklist_section(
            section_data, frozenset({"requiredButMissing"}), "sessionStart", result
        )

        assert not result.is_valid
        assert any(
            "Missing required item: sessionStart.requiredButMissing" in e for e in result.errors
        )

    def test_non_dict_items_ignored(self) -> None:
        """Non-dict values in section data are ignored."""
        section_data = {
            "someString": "not a dict",
            "someNumber": 42,
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert result.is_valid


class TestEvidenceContradiction:
    """Tests for evidence-contradiction detection."""

    @pytest.mark.parametrize(
        "evidence",
        [
            "not available",
            "SKIPPED",
            "N/A",
            "Deferred to next session",
            "will validate later",
            "will run after merge",
            "TODO",
            "pending review",
            "TBD",
        ],
    )
    def test_contradiction_detected(self, evidence: str) -> None:
        """Evidence containing skip/waiver patterns triggers warning."""
        section_data = {
            "serenaActivated": {
                "complete": True,
                "evidence": evidence,
                "level": "MUST",
            },
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert any("Evidence contradiction" in w for w in result.warnings)

    def test_legitimate_evidence_no_contradiction(self) -> None:
        """Legitimate evidence does not trigger contradiction warning."""
        section_data = {
            "serenaActivated": {
                "complete": True,
                "evidence": "mcp__serena__activate_project output confirmed",
                "level": "MUST",
            },
        }
        result = ValidationResult()

        validate_checklist_section(section_data, frozenset(), "sessionStart", result)

        assert not any("Evidence contradiction" in w for w in result.warnings)

    def test_contradiction_pattern_matches_expected(self) -> None:
        """CONTRADICTION_PATTERNS matches known skip indicators."""
        assert CONTRADICTION_PATTERNS.search("not available")
        assert CONTRADICTION_PATTERNS.search("SKIPPED due to CI")
        assert CONTRADICTION_PATTERNS.search("N/A for this session")
        assert not CONTRADICTION_PATTERNS.search("Tool output confirmed")

    @staticmethod
    def _warn(section_data: dict) -> list[str]:
        """Validate a sessionStart section and return contradiction warnings."""
        result = ValidationResult()
        validate_checklist_section(section_data, frozenset(), "sessionStart", result)
        return [w for w in result.warnings if "Evidence contradiction" in w]

    @staticmethod
    def _item(evidence: str) -> dict:
        """Build a complete MUST item with the given evidence."""
        return {
            "serenaActivated": {
                "complete": True,
                "evidence": evidence,
                "level": "MUST",
            },
        }

    @pytest.mark.parametrize(
        "evidence",
        [
            # Item ITSELF deferred is a genuine contradiction (issue #2007).
            "Deferred to next session",
            "Deferred to pre-commit hook validation",
            "Planning artifacts staged; commit deferred to session-824",
            "Serena init deferred per ADR-007 fast-path",
            "deferred",
            "pending",
            # A genuine token alongside a scope-qualified one still flags.
            "Tests skipped. Perf deferred to follow-up.",
            # Adversative conjunction ties the deferral to the completion, so
            # it contradicts rather than noting separate work (gemini).
            "Tests passed. But we deferred the deploy to next session",
            # Clause boundary must sit AFTER the affirmative word, not before:
            # the ';' precedes 'passed', so it is not a trailing-note separator.
            "Status; passed but pending review",
            # Adverb-separated negation: "not yet validated" negates the
            # affirmative, so the deferral is not suppressed (bug 07f14170).
            "Not yet validated; pending final review",
            # A dot inside a version/decimal is not a clause boundary, so the
            # deferral is not suppressed (bug 0a163adc).
            "Created item v1.5 pending review",
            # Contraction negation: "haven't passed" negates the affirmative, so
            # the trailing deferral is a genuine contradiction (bug 0ea9d246).
            "Tests haven't passed; pending review",
        ],
    )
    def test_genuine_contradiction_still_flags(self, evidence: str) -> None:
        """An item-itself deferral or any genuine token must still warn."""
        assert self._warn(self._item(evidence)), f"expected warning for {evidence!r}"

    @pytest.mark.parametrize(
        "evidence",
        [
            # Deferred/pending in a parenthetical aside about other work.
            "Tests pass (perf benchmark deferred to follow-up)",
            "Schema validated (migration pending review)",
            "Two commits created: P0 (commit 5639b23f) and P1 (pending)",
            "CI checks passing (CodeRabbit pending)",
            # Trailing note after affirmative completion across a clause boundary.
            "Markdown lint passed (0 errors after fix); pending pre-commit final run",
            # Mid-clause adversative ("but" meaning "except") does not introduce
            # the deferral clause, so suppression still applies (bug ref1_dda37e6b).
            "Tests passed. All scenarios but the edge case handled; deferred edge case",
            # Exact strings from issue #2007.
            "Used: spec skill (Step 0 + Step 0.5 gates), plan skill (decomposition). "
            "Bash: grep, awk, wc, gh CLI. No Python scorer (deferred per PRD 11).",
            "Spec scope validation: Step 0 First Principles Gate PASS (after H3 halt "
            "+ revision); Step 0.5 Memory-First Gate PASS (after H11 halt + "
            "reclassification); Step 9 critic checks 9a/9b/9c/9d all PASS. "
            "Audit-execution validation per TASK-011 Step 10 deferred to audit commit.",
        ],
    )
    def test_scope_qualified_deferral_not_flagged(self, evidence: str) -> None:
        """Deferred/pending pointing at a different scope must not warn (#2007)."""
        assert not self._warn(self._item(evidence)), f"false positive on {evidence!r}"

    @pytest.mark.parametrize(
        "evidence",
        [
            # Exact string from issue #3141: full pytest summary line.
            "uv run pytest tests/ -q: 14434 passed, 21 skipped, 45 xfailed",
            # Minimal numeric count.
            "21 skipped",
            # Zero is still a numeric count, not a skipped step.
            "0 skipped",
            # Thousands separator keeps the digit immediately before the token.
            "1,234 skipped",
            # Whitespace between digit and token (multiple spaces / tab).
            "12   skipped",
        ],
    )
    def test_numeric_skipped_count_not_flagged(self, evidence: str) -> None:
        """A pytest numeric 'N skipped' count is not a contradiction (#3141)."""
        assert not self._warn(self._item(evidence)), f"false positive on {evidence!r}"

    @pytest.mark.parametrize(
        "evidence",
        [
            # Bare status word: the item itself was skipped.
            "Tests skipped.",
            # A word (not a digit) immediately precedes the token, so it is a
            # skipped step, not a numeric count.
            "step skipped",
            # The digit is not immediately before the token ("step" is), so this
            # describes a skipped validation step and must still flag.
            "1 step skipped",
            # A numeric skipped count alongside a genuine incomplete token still
            # flags on the genuine token (TODO).
            "14434 passed, 21 skipped, 45 xfailed; TODO wire up remaining check",
            # Numeric identifier immediately before "skipped" where the number is
            # part of an identifier phrase, not a pytest count. These must flag.
            "step 21 skipped",
            "PR #3141 skipped review",
            "v2.1 skipped tests",
            # A numbered prose step sits after a word, not a delimiter, so it is
            # not a pytest count and must still flag (#3141 review).
            "Phase 2 skipped",
            "check 5 skipped",
            "test 3 skipped",
            "phase3 skipped",
        ],
    )
    def test_skipped_step_still_flags(self, evidence: str) -> None:
        """A skipped validation step (not a numeric count) must still warn (#3141)."""
        assert self._warn(self._item(evidence)), f"expected warning for {evidence!r}"


class TestValidateProtocolCompliance:
    """Tests for validate_protocol_compliance function."""

    def test_missing_session_start_is_left_to_the_schema(self) -> None:
        """The schema's protocolCompliance.required already names it (issue #3346).

        This layer only walks the section it was given; it must not restate the
        absence under a second spelling. The one-message guarantee is pinned in
        TestSectionAbsenceIsReportedOnce, which drives the full validator.
        """
        result = ValidationResult()

        validate_protocol_compliance({"sessionEnd": {}}, result)

        assert not any("protocolCompliance.sessionStart" in error for error in result.errors)
        assert any(
            error.startswith("Missing required item: sessionEnd.") for error in result.errors
        )

    def test_missing_session_end_is_left_to_the_schema(self) -> None:
        """Mirror of the sessionStart case."""
        result = ValidationResult()

        validate_protocol_compliance({"sessionStart": {}}, result)

        assert not any("protocolCompliance.sessionEnd" in error for error in result.errors)
        assert any(
            error.startswith("Missing required item: sessionStart.") for error in result.errors
        )

    def test_both_sections_present(self) -> None:
        """Both sections present passes section validation."""
        protocol: dict[str, Any] = {
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
                "sessionStart": _make_complete_start_section(),
                "sessionEnd": _make_complete_end_section(),
            },
        }

        result = validate_session_log(data)

        assert result.is_valid

    def test_missing_session_section(self) -> None:
        """Missing session section causes error."""
        data: dict[str, Any] = {
            "protocolCompliance": {"sessionStart": {}, "sessionEnd": {}},
        }

        result = validate_session_log(data)

        assert not result.is_valid
        # The schema owns presence reporting since #3346; the
        # hand-rolled "Missing: session" duplicate was removed.
        assert any("'session' is a required property" in e for e in result.errors)

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
        # The schema owns presence reporting since #3346; the
        # hand-rolled "Missing: protocolCompliance" duplicate was removed.
        assert any("'protocolCompliance' is a required property" in e for e in result.errors)


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
        assert error is not None
        assert "not found" in error

    def test_error_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns error for invalid JSON."""
        session_file = tmp_path / "invalid.json"
        session_file.write_text('{"invalid": }')

        data, error = load_session_file(session_file)

        assert data is None
        assert error is not None
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
                "sessionStart": _make_complete_start_section(),
                "sessionEnd": _make_complete_end_section(),
            },
        }
        session_file = tmp_path / "valid-session.json"
        session_file.write_text(json.dumps(data))
        return session_file

    @pytest.fixture
    def invalid_session_file(self, tmp_path: Path) -> Path:
        """Create an invalid session log file."""
        data: dict[str, Any] = {
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
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", valid_session_file.parent)
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
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", invalid_session_file.parent)
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
        monkeypatch.setattr(validate_session_json, "_PROJECT_ROOT", invalid_session_file.parent)
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
        data: dict[str, Any] = {
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
                "sessionStart": _make_complete_start_section(),
                "sessionEnd": _make_complete_end_section(),
            },
            "workLog": [],
            "decisions": [],
            "outcome": {},
        }

        result = validate_session_log(data)

        assert result.is_valid


def _make_valid_log(**session_overrides: object) -> dict:
    """Build a session log that satisfies both the schema and the protocol checks."""
    session: dict[str, object] = {
        "number": 3346,
        "date": "2026-07-25",
        "branch": "fix/3346-session-schema-enforcement",
        "startingCommit": "1ffee3834e910608ed6c03c374fb71ff7c39bdc3",
        "objective": "Enforce the committed schema in the session log validator.",
    }
    session.update(session_overrides)
    return {
        "session": session,
        "protocolCompliance": {
            "sessionStart": _make_complete_start_section(),
            "sessionEnd": _make_complete_end_section(),
        },
    }


class TestSchemaIsActuallyEnforced:
    """The docstring promises schema validation; these prove the schema runs.

    Issue #3346: the validator advertised schema validation and never loaded the
    schema, so a bot reviewer caught by hand a `session.number` the gate passed.
    """

    def test_valid_log_passes(self) -> None:
        result = validate_session_log(_make_valid_log())
        assert result.errors == []

    def test_string_session_number_is_rejected(self) -> None:
        """The exact shape a bot reviewer caught by hand on PR #3344."""
        result = validate_session_log(_make_valid_log(number="3343-branch-context-merge"))
        assert any("number" in e and e.startswith("Schema:") for e in result.errors)

    def test_null_session_number_is_rejected(self) -> None:
        """The shape sitting in 2026-01-09-session-389.json."""
        result = validate_session_log(_make_valid_log(number=None))
        assert any("number" in e and e.startswith("Schema:") for e in result.errors)

    def test_session_number_below_minimum_is_rejected(self) -> None:
        """`minimum: 1` is a schema-only rule; no hand-rolled check covers it."""
        result = validate_session_log(_make_valid_log(number=0))
        assert any("number" in e and e.startswith("Schema:") for e in result.errors)

    def test_malformed_date_is_rejected(self) -> None:
        result = validate_session_log(_make_valid_log(date="July 25, 2026"))
        assert any("date" in e and e.startswith("Schema:") for e in result.errors)

    def test_wrong_type_for_a_declared_object_is_rejected(self) -> None:
        log = _make_valid_log()
        log["protocolCompliance"] = ["sessionStart", "sessionEnd"]
        result = validate_session_log(log)
        assert any(e.startswith("Schema:") for e in result.errors)

    def test_every_violation_is_reported_not_just_the_first(self) -> None:
        """One commit round should fix the log, not one field per round."""
        result = validate_session_log(_make_valid_log(number="x", date="nope"))
        schema_errors = [e for e in result.errors if e.startswith("Schema:")]
        assert len(schema_errors) >= 2

    def test_violation_names_the_field_path(self) -> None:
        result = validate_session_log(_make_valid_log(number="x"))
        assert any("session.number" in e for e in result.errors)

    def test_missing_section_is_reported_once_not_twice(self) -> None:
        """The schema owns presence; the hand-rolled check must not restate it."""
        log = _make_valid_log()
        del log["session"]
        result = validate_session_log(log)
        assert sum("'session' is a required property" in e for e in result.errors) == 1
        assert "Missing: session" not in result.errors

    def test_unloadable_schema_is_an_error_not_a_silent_pass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A gate that cannot load its contract has checked nothing; say so."""
        import scripts.validate_session_json as vsj

        monkeypatch.setattr(vsj, "SCHEMA_PATH", Path("/nonexistent/session-log.schema.json"))
        result = ValidationResult()
        vsj.validate_against_schema(_make_valid_log(), result)
        assert any("schema layer skipped" in e for e in result.errors)

    def test_unloadable_schema_does_not_claim_the_whole_gate_checked_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """validate_session_log still runs protocol checks; the message must not
        claim total silence when only the schema layer was skipped."""
        import scripts.validate_session_json as vsj

        monkeypatch.setattr(vsj, "SCHEMA_PATH", Path("/nonexistent/session-log.schema.json"))
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"]["handoffRead"] = {
            "complete": False,
            "evidence": "",
            "level": "MUST",
        }
        result = vsj.validate_session_log(log)
        assert not any("nothing was checked" in e for e in result.errors)
        assert any("handoffRead" in e for e in result.errors)

    @pytest.mark.parametrize(
        ("schema", "reason"),
        [
            ({"type": "nope"}, "unknown type name raises UnknownType"),
            (
                {"$schema": "http://json-schema.org/draft-07/schema#", "properties": "notadict"},
                "non-object properties raises AttributeError",
            ),
            ({"required": "notalist"}, "non-array required raises nothing until use"),
        ],
    )
    def test_an_invalid_schema_is_an_error_not_a_crash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        schema: dict[str, object],
        reason: str,
    ) -> None:
        """Driven with real malformed schemas, not a mock of ``validator_for``.

        Mocking the constructor to raise ``SchemaError`` proves only that the
        handler is reachable. It does not prove the handler catches what
        jsonschema actually raises, and for two of these three it does not:
        ``UnknownType`` and ``AttributeError`` are not ``SchemaError``.
        """
        import scripts.validate_session_json as vsj

        schema_path = tmp_path / "broken.schema.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        monkeypatch.setattr(vsj, "SCHEMA_PATH", schema_path)

        result = ValidationResult()
        vsj.validate_against_schema(_make_valid_log(), result)

        assert any("not a valid schema" in e for e in result.errors), reason

    def test_a_valid_schema_is_not_reported_as_malformed(self) -> None:
        """Negative control: the guard must not fire on the committed schema."""
        import scripts.validate_session_json as vsj

        result = ValidationResult()
        vsj.validate_against_schema(_make_valid_log(), result)

        assert not any("not a valid schema" in e for e in result.errors)

    def test_array_indices_are_ordered_numerically_not_lexically(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pins why the sort key stays raw.

        Stringifying every path element to dodge a mixed str/int comparison
        would order index 10 ahead of index 2. Session logs carry workLog arrays
        well past ten entries, so the reordering is reachable on real data.

        The mixed comparison the stringify guards against is not: two paths are
        only compared past a shared prefix, and a shared prefix names one
        container, whose child keys are all strings or all integers.
        """
        import scripts.validate_session_json as vsj

        schema_path = tmp_path / "array.schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "array",
                    "items": {"type": "string"},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(vsj, "SCHEMA_PATH", schema_path)

        document: list[object] = ["ok"] * 12
        document[2] = 2
        document[10] = 10

        result = ValidationResult()
        vsj.validate_against_schema(document, result)

        assert [e.split(":")[1].strip() for e in result.errors] == ["2", "10"]

    def test_committed_schema_is_readable(self) -> None:
        """Guards against a schema edit that leaves the file unparseable."""
        import scripts.validate_session_json as vsj

        assert vsj.SCHEMA_PATH.is_file()
        assert isinstance(vsj._load_schema(), dict)

    def test_malformed_history_timestamp_is_rejected(self) -> None:
        """The schema declares `format: "date-time"` on
        developmentPhase.history[].timestamp. jsonschema treats "format" as
        annotation-only unless a FormatChecker covering it is supplied, so
        this was previously accepted silently."""
        log = _make_valid_log()
        log["developmentPhase"] = {
            "current": "refinement",
            "history": [{"phase": "refinement", "timestamp": "not-a-date"}],
        }
        result = validate_session_log(log)
        assert any(
            "developmentPhase.history" in e and "not a" in e and e.startswith("Schema:")
            for e in result.errors
        )

    def test_valid_history_timestamp_passes(self) -> None:
        """A real RFC 3339 date-time must not be rejected by the new check."""
        log = _make_valid_log()
        log["developmentPhase"] = {
            "current": "refinement",
            "history": [{"phase": "refinement", "timestamp": "2026-07-26T01:12:11Z"}],
        }
        result = validate_session_log(log)
        assert result.errors == []

    def test_offset_naive_history_timestamp_is_rejected(self) -> None:
        """`datetime.fromisoformat` accepts a timestamp with no UTC offset,
        but RFC 3339 section 5.6 (what the schema's `format: "date-time"`
        means) requires one. A naive parse must not pass as RFC 3339."""
        log = _make_valid_log()
        log["developmentPhase"] = {
            "current": "refinement",
            "history": [{"phase": "refinement", "timestamp": "2026-07-26T01:12:11"}],
        }
        result = validate_session_log(log)
        assert any(
            "developmentPhase.history" in e and e.startswith("Schema:") for e in result.errors
        )


class TestProtocolChecksSurviveSchemaEnforcement:
    """The schema cannot express these; adding it must not displace them."""

    def test_incomplete_must_item_still_fails(self) -> None:
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"]["handoffRead"] = {
            "complete": False,
            "evidence": "",
            "level": "MUST",
        }
        result = validate_session_log(log)
        assert any("handoffRead" in e for e in result.errors)

    def test_both_checklist_casings_still_accepted(self) -> None:
        """`definitions.checklistItem` is an anyOf over Complete/complete.

        Note the asymmetry: the anyOf varies the casing of Complete and
        Evidence but declares `level` lowercase in both branches, and all
        16675 checklist items in .agents/sessions/ agree. A log spelling it
        `Level` passes the Python check (which is case-insensitive) and fails
        the schema; that is the schema's call to make, so this test pins the
        casing the corpus actually uses.
        """
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"] = {
            name: {"Complete": True, "Evidence": "Evidence", "level": "MUST"}
            for name in SESSION_START_REQUIRED_ITEMS
        }
        result = validate_session_log(log)
        assert result.errors == []


class TestHistoricalLogsAreExemptByConstruction:
    """Issue #3346 accepted exemption-by-changed-files over backfilling 131 logs.

    The exemption is not a flag anyone can forget to set: it holds because both
    call sites hand the validator one changed path at a time. These tests fail
    if a future change points the validator at the whole directory, which would
    turn every historical log into a blocking failure.
    """

    @staticmethod
    def _invoked_paths(paths: list[str]) -> list[str]:
        """Return the session paths validate_branch_sessions actually shelled out for."""
        from scripts.validation import git_hook_policy

        seen: list[str] = []

        def _record(command: list[str], _repo_root: Path) -> subprocess.CompletedProcess[str]:
            seen.append(command[-1])
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(git_hook_policy, "_run_command", _record):
            git_hook_policy.validate_branch_sessions(paths, Path.cwd())
        return seen

    def test_git_hook_policy_validates_only_the_paths_it_is_given(self) -> None:
        given = ["a/one.json", "b/two.json"]
        assert self._invoked_paths(given) == given

    def test_git_hook_policy_validates_nothing_when_given_nothing(self) -> None:
        """No path list means no work. A directory fallback would fail 131 logs."""
        assert self._invoked_paths([]) == []

    def test_workflow_validates_one_file_per_invocation(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/ai-session-protocol.yml"
        ).read_text(encoding="utf-8")
        assert "validate_session_json.py $sessionFile" in workflow
        assert "validate_session_json.py .agents/sessions/*" not in workflow


class TestMainNarrowsOnThePayload:
    """`main` branches on `error is not None`, not on `data is None` (issue #3346).

    The old form left `data` optional and carried a type suppression. These
    pin the observable behavior so the narrowing cannot be reverted silently.

    Fixtures live inside the repo on purpose: `validate_safe_path` rejects any
    path outside the project root, so a `tmp_path` fixture would make every
    case exit 1 for a path reason and prove nothing about the load or the
    schema.
    """

    def test_missing_file_exits_one_with_the_load_error(self, scratch: Path) -> None:
        proc = _run_cli(scratch / "absent.json")
        assert proc.returncode == 1
        assert "not found" in (proc.stdout + proc.stderr)

    def test_unparseable_file_exits_one(self, scratch: Path) -> None:
        bad = scratch / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        proc = _run_cli(bad)
        assert proc.returncode == 1
        assert "Invalid JSON" in (proc.stdout + proc.stderr)

    def test_schema_violation_exits_one(self, scratch: Path) -> None:
        """The headline acceptance criterion, driven through the CLI."""
        log = scratch / "log.json"
        log.write_text(json.dumps(_make_valid_log(number="not-an-integer")), encoding="utf-8")
        proc = _run_cli(log)
        assert proc.returncode == 1
        assert "Schema:" in (proc.stdout + proc.stderr)

    def test_valid_file_exits_zero(self, scratch: Path) -> None:
        log = scratch / "log.json"
        log.write_text(json.dumps(_make_valid_log()), encoding="utf-8")
        proc = _run_cli(log)
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestNonObjectPayloadsAreReportedNotCrashed:
    """A session log is an object, but any JSON value can reach the validator.

    Before issue #3346's review, a top-level array reached ``data.get`` and
    exited 2 with ``'list' object has no attribute 'get'``: a crash, reported as
    an internal error, for input the schema already describes.
    """

    @pytest.mark.parametrize("payload", [[1, 2, 3], "a string", 7, True])
    def test_the_schema_reports_the_type_instead_of_crashing(self, payload: object) -> None:
        result = validate_session_log(payload)
        assert not result.is_valid
        assert any("is not of type 'object'" in error for error in result.errors)

    def test_protocol_checks_do_not_run_on_a_non_object(self) -> None:
        """Only the schema speaks. A protocol message here means a mapping was assumed."""
        result = validate_session_log([1, 2, 3])
        assert all(error.startswith("Schema:") for error in result.errors)

    def test_a_non_object_file_exits_one_not_two(self, scratch: Path) -> None:
        path = scratch / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert _run_cli(path).returncode == 1

    def test_json_null_reaches_the_schema_rather_than_looking_like_a_load_error(
        self, scratch: Path
    ) -> None:
        """`json.loads('null')` succeeds, so the loader reports no error for it.

        `main` therefore branches on `error`, not on the payload. Branching on
        the payload would print `ERROR: None` for a file that parsed fine.
        """
        path = scratch / "null.json"
        path.write_text("null", encoding="utf-8")

        data, error = load_session_file(path)
        assert data is None
        assert error is None

        proc = _run_cli(path)
        assert proc.returncode == 1
        assert "ERROR: None" not in (proc.stdout + proc.stderr)
        assert "is not of type 'object'" in (proc.stdout + proc.stderr)


class TestValidatorFollowsTheSchemaDeclaration:
    """The committed schema declares draft-07; pinning another draft changes meaning.

    Asserting `validator_for` returns Draft7Validator would only test jsonschema.
    These drive `validate_against_schema` against a schema whose result differs
    between the two drafts, so a hard-coded validator fails them.
    """

    # Array-form `items` is tuple validation in draft-07. Draft 2020-12 replaced
    # it with `prefixItems` and ignores this spelling, so the two drafts disagree
    # on whether [1] is valid here.
    _DIVERGENT = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "array",
        "items": [{"type": "string"}],
    }

    def test_draft_seven_semantics_are_applied(
        self, scratch: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.validate_session_json as module

        schema_path = scratch / "divergent.schema.json"
        schema_path.write_text(json.dumps(self._DIVERGENT), encoding="utf-8")
        monkeypatch.setattr(module, "SCHEMA_PATH", schema_path)

        result = ValidationResult()
        module.validate_against_schema([1], result)

        assert result.errors, "draft-07 tuple validation was not applied"
        assert any("is not of type 'string'" in error for error in result.errors)

    def test_the_committed_schema_declares_draft_seven(self) -> None:
        """Pins the premise. If the schema is upgraded, the test above must be revisited."""
        import scripts.validate_session_json as module

        schema = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
        assert schema["$schema"].startswith("http://json-schema.org/draft-07/")

    def test_the_committed_schema_is_itself_valid(self) -> None:
        """A malformed schema would silently accept everything."""
        from jsonschema.validators import validator_for

        import scripts.validate_session_json as module

        schema = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)


class TestSectionAbsenceIsReportedOnce:
    """protocolCompliance.required names both sections, so Python must not restate it."""

    def test_a_missing_session_start_is_named_once(self) -> None:
        log = _make_valid_log()
        del log["protocolCompliance"]["sessionStart"]
        result = validate_session_log(log)
        naming = [error for error in result.errors if "sessionStart" in error]
        assert len(naming) == 1
        assert naming[0].startswith("Schema:")

    def test_a_missing_session_end_is_named_once(self) -> None:
        log = _make_valid_log()
        del log["protocolCompliance"]["sessionEnd"]
        result = validate_session_log(log)
        naming = [error for error in result.errors if "sessionEnd" in error]
        assert len(naming) == 1
        assert naming[0].startswith("Schema:")

    def test_a_non_mapping_section_does_not_reach_the_protocol_checks(self) -> None:
        log = _make_valid_log()
        log["protocolCompliance"]["sessionStart"] = "not a mapping"
        result = validate_session_log(log)
        assert any(
            "sessionStart" in error and error.startswith("Schema:") for error in result.errors
        )


class TestCountMustFailures:
    """Issue #3365: the CI MUST counter must be able to reach a nonzero value.

    The workflow previously counted MUST failures with a regex for markdown
    table rows this validator has never emitted, so the count was pinned at 0
    and the "Enforce MUST Requirements" step could not fire on its own terms.
    """

    def test_no_errors_counts_zero(self) -> None:
        assert count_must_failures(ValidationResult()) == 0

    @pytest.mark.parametrize(
        "prefix",
        [_INCOMPLETE_MUST_PREFIX, _MISSING_REQUIRED_PREFIX, _MUST_NOT_VIOLATED_PREFIX],
        ids=["incomplete-must", "missing-required", "must-not-violated"],
    )
    def test_every_must_prefix_is_counted(self, prefix: str) -> None:
        """Each MUST-level error shape the validator emits must be countable."""
        result = ValidationResult(errors=[f"{prefix}sessionStart.handoffRead"])
        assert count_must_failures(result) == 1

    def test_non_must_errors_are_not_counted(self) -> None:
        """Schema and format errors are real failures but not MUST-level."""
        result = ValidationResult(
            errors=[
                "Invalid commit SHA format: zzz",
                "Schema: cannot load session-log.schema.json, schema layer skipped: boom",
            ]
        )
        assert count_must_failures(result) == 0

    def test_must_and_non_must_errors_are_separated(self) -> None:
        result = ValidationResult(
            errors=[
                f"{_INCOMPLETE_MUST_PREFIX}sessionStart.handoffRead",
                f"{_INCOMPLETE_MUST_PREFIX}sessionStart.serenaActivated",
                "Invalid commit SHA format: zzz",
            ]
        )
        assert count_must_failures(result) == 2
        assert len(result.errors) == 3

    def test_an_incomplete_must_item_reaches_the_counter_end_to_end(self) -> None:
        """The prefix constants must match what the validators actually emit.

        A test that only feeds hand-written strings to the counter would stay
        green if the emit sites drifted. This one runs a real validation.
        """
        start = _make_complete_start_section()
        start["handoffRead"]["complete"] = False
        result = ValidationResult()
        validate_session_start(start, result)
        assert count_must_failures(result) >= 1


class TestBuildSummary:
    """The --json-output summary is the workflow's machine-readable contract."""

    def test_a_clean_result_reports_compliant(self, tmp_path: Path) -> None:
        summary = build_summary(tmp_path / "s.json", ValidationResult())
        assert summary["verdict"] == "COMPLIANT"
        assert summary["exit_code"] == 0
        assert summary["must_failures"] == 0
        assert summary["error_count"] == 0

    def test_a_failing_result_reports_non_compliant(self, tmp_path: Path) -> None:
        result = ValidationResult(
            errors=[f"{_INCOMPLETE_MUST_PREFIX}sessionStart.handoffRead"],
            warnings=["Missing evidence: sessionEnd.changesCommitted"],
        )
        summary = build_summary(tmp_path / "s.json", result)
        assert summary["verdict"] == "NON_COMPLIANT"
        assert summary["exit_code"] == 1
        assert summary["must_failures"] == 1
        assert summary["error_count"] == 1
        assert summary["warnings"] == ["Missing evidence: sessionEnd.changesCommitted"]

    def test_non_must_errors_leave_must_failures_at_zero(self, tmp_path: Path) -> None:
        """A NON_COMPLIANT verdict with 0 MUST failures is legitimate."""
        result = ValidationResult(errors=["Invalid commit SHA format: zzz"])
        summary = build_summary(tmp_path / "s.json", result)
        assert summary["verdict"] == "NON_COMPLIANT"
        assert summary["must_failures"] == 0
        assert summary["error_count"] == 1

    def test_the_summary_is_json_serialisable(self, tmp_path: Path) -> None:
        summary = build_summary(tmp_path / "s.json", ValidationResult(errors=["boom"]))
        assert json.loads(json.dumps(summary)) == summary


class TestFilenameSessionNumber:
    """The number encoded in a session log filename."""

    def test_reads_the_number_from_a_conventional_stem(self, tmp_path: Path) -> None:
        assert filename_session_number(tmp_path / "2026-07-26-session-3355.json") == 3355

    def test_reads_the_number_when_a_slug_follows(self, tmp_path: Path) -> None:
        path = tmp_path / "2026-07-26-session-3355-validate-session-number.json"
        assert filename_session_number(path) == 3355

    def test_leading_zeros_read_as_the_integer(self, tmp_path: Path) -> None:
        """`session-09` and `session-9` name the same session."""
        assert filename_session_number(tmp_path / "2026-01-18-session-09-slug.json") == 9

    def test_a_non_numeric_discriminator_returns_none(self, tmp_path: Path) -> None:
        """Six committed logs predate the convention; they are skipped, not failed."""
        for stem in (
            "2026-03-01-session-64a-slug",
            "2026-03-01-session-critic-468-slug",
            "2026-03-01-session-pr513-slug",
            "2026-03-01-session-qa-issue-500-slug",
            "2026-03-01-session-chain1-slug",
            "2026-03-01-session-2993b-slug",
        ):
            assert filename_session_number(tmp_path / f"{stem}.json") is None, stem

    def test_a_stem_without_the_date_prefix_returns_none(self, tmp_path: Path) -> None:
        assert filename_session_number(tmp_path / "session-3355.json") is None

    def test_a_number_elsewhere_in_the_stem_is_not_read(self, tmp_path: Path) -> None:
        """The pattern anchors at the start; a slug number must not be mistaken."""
        assert filename_session_number(tmp_path / "2026-07-26-session-12-fix-3355.json") == 12


class TestValidateFilenameNumber:
    """session.number must agree with the number in the filename (issue #3355)."""

    @staticmethod
    def _check(path: Path, number: object) -> ValidationResult:
        result = ValidationResult()
        validate_filename_number(path, {"session": {"number": number}}, result)
        return result

    def test_agreement_passes(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-07-26-session-3355-slug.json", 3355)
        assert result.errors == []

    def test_disagreement_is_an_error(self, tmp_path: Path) -> None:
        """The reported bite: filename 3342 carrying number 3343."""
        result = self._check(tmp_path / "2026-07-26-session-3342-slug.json", 3343)
        assert len(result.errors) == 1
        assert "3343" in result.errors[0]
        assert "3342" in result.errors[0]

    def test_the_error_names_both_repairs(self, tmp_path: Path) -> None:
        """Either side can be the wrong one, so the message must not assume."""
        result = self._check(tmp_path / "2026-07-26-session-3342-slug.json", 3343)
        assert "Set session.number" in result.errors[0]
        assert "rename the file" in result.errors[0]

    def test_the_error_names_the_file(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-07-26-session-3342-slug.json", 3343)
        assert "2026-07-26-session-3342-slug.json" in result.errors[0]

    def test_leading_zeros_still_agree(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-01-18-session-09-slug.json", 9)
        assert result.errors == []

    def test_an_unparseable_stem_is_skipped(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-03-01-session-64a-slug.json", 999)
        assert result.errors == []

    def test_a_missing_number_is_left_to_the_schema(self, tmp_path: Path) -> None:
        """Reporting it here would print the same defect under two spellings."""
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", {"session": {}}, result)
        assert result.errors == []

    def test_a_string_number_is_left_to_the_schema(self, tmp_path: Path) -> None:
        result = self._check(tmp_path / "2026-07-26-session-3355.json", "3355")
        assert result.errors == []

    def test_a_bool_number_is_left_to_the_schema(self, tmp_path: Path) -> None:
        """bool is an int subclass, so the type check has to exclude it explicitly.

        The filename number is deliberately not 1: ``True == 1`` in Python, so a
        ``session-1`` filename would agree by coercion and pass either way.
        """
        result = self._check(tmp_path / "2026-07-26-session-3355.json", True)
        assert result.errors == []

    def test_a_bool_number_does_not_agree_by_coercion(self, tmp_path: Path) -> None:
        """``True == 1`` must not read as a valid number for session 1."""
        result = self._check(tmp_path / "2026-07-26-session-1.json", True)
        assert result.errors == []

    def test_a_missing_session_object_is_skipped(self, tmp_path: Path) -> None:
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", {}, result)
        assert result.errors == []

    def test_a_non_mapping_session_is_skipped(self, tmp_path: Path) -> None:
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", {"session": []}, result)
        assert result.errors == []

    def test_a_non_mapping_root_is_skipped(self, tmp_path: Path) -> None:
        result = ValidationResult()
        validate_filename_number(tmp_path / "2026-07-26-session-3355.json", [1, 2], result)
        assert result.errors == []

    def test_the_legacy_snake_case_shape_is_skipped(self, tmp_path: Path) -> None:
        """Pre-convention logs carry `session_number` at the root and no `session`."""
        result = ValidationResult()
        validate_filename_number(
            tmp_path / "2026-01-09-session-389.json", {"session_number": 389}, result
        )
        assert result.errors == []

    def test_the_violation_is_not_counted_as_a_must_failure(self, tmp_path: Path) -> None:
        """It is a naming defect, not a protocol MUST the session skipped."""
        result = self._check(tmp_path / "2026-07-26-session-3342.json", 3343)
        assert count_must_failures(result) == 0


class TestEveryCommittedLogSatisfiesTheFilenameInvariant:
    """The guard is only trustworthy if the corpus it governs already passes."""

    def test_no_committed_session_log_violates_it(self) -> None:
        sessions = Path(__file__).resolve().parents[1] / ".agents" / "sessions"
        violations = []
        checked = 0
        for path in sorted(sessions.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            result = ValidationResult()
            validate_filename_number(path, data, result)
            if filename_session_number(path) is not None:
                checked += 1
            violations.extend(result.errors)

        assert checked > 900, f"expected the whole corpus, only reached {checked}"
        assert violations == [], "\n".join(violations)
