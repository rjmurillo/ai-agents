"""Tests for scripts/error_classification.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.error_classification import (
    ClassifiedError,
    ErrorType,
    RecoveryHint,
    classify_error,
    get_graduation_candidates,
    load_recovery_hints,
    log_error,
)

HINTS_PATH = Path(__file__).resolve().parents[1] / ".agents" / "recovery-hints.yaml"

HintsDB = dict[str, list[RecoveryHint]]


# ---------------------------------------------------------------------------
# RecoveryHint
# ---------------------------------------------------------------------------


class TestRecoveryHint:
    def test_compiled_pattern_matches(self) -> None:
        rh = RecoveryHint(pattern="HTTP 403", hint="rate limited")
        assert rh.compiled_pattern.search("Got HTTP 403 from API")

    def test_compiled_pattern_case_insensitive(self) -> None:
        rh = RecoveryHint(pattern="conflict", hint="merge issue")
        assert rh.compiled_pattern.search("CONFLICT in file.txt")


# ---------------------------------------------------------------------------
# load_recovery_hints
# ---------------------------------------------------------------------------


class TestLoadRecoveryHints:
    def test_loads_from_repo_yaml(self) -> None:
        hints = load_recovery_hints(HINTS_PATH)
        assert "tool_gh" in hints
        assert "general" in hints
        assert len(hints["tool_gh"]) >= 1

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        hints = load_recovery_hints(tmp_path / "nonexistent.yaml")
        assert hints == {}

    def test_returns_empty_for_empty_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        hints = load_recovery_hints(empty)
        assert hints == {}

    def test_skips_malformed_entries(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("tool_gh:\n  - pattern: 'x'\n  - bad_key: 'y'\n")
        hints = load_recovery_hints(bad)
        # First entry has pattern but no hint, skip. Second has neither.
        assert hints == {}


# ---------------------------------------------------------------------------
# classify_error
# ---------------------------------------------------------------------------


class TestClassifyError:
    @pytest.fixture()
    def hints_db(self) -> HintsDB:
        return load_recovery_hints(HINTS_PATH)

    def test_loop_detection_three_identical_calls(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="some error",
            call_history=["gh", "gh", "gh"],
            hints_db=hints_db,
        )
        assert result.error_type is ErrorType.INFINITE_LOOP
        assert not result.is_transient
        assert "Loop detected" in result.recovery_hints[0]

    def test_no_loop_with_mixed_history(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="error",
            call_history=["git", "gh", "gh"],
            hints_db=hints_db,
        )
        assert result.error_type is not ErrorType.INFINITE_LOOP

    def test_exit_code_2_maps_to_tool_failure(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="unknown",
            exit_code=2,
            stderr="",
            hints_db=hints_db,
        )
        assert result.error_type is ErrorType.TOOL_FAILURE

    def test_exit_code_3_maps_to_tool_failure(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="unknown",
            exit_code=3,
            stderr="",
            hints_db=hints_db,
        )
        assert result.error_type is ErrorType.TOOL_FAILURE

    def test_exit_code_4_maps_to_tool_failure(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="unknown",
            exit_code=4,
            stderr="",
            hints_db=hints_db,
        )
        assert result.error_type is ErrorType.TOOL_FAILURE

    def test_transient_detection_rate_limit(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="API rate limit exceeded",
            hints_db=hints_db,
        )
        assert result.is_transient

    def test_transient_detection_timeout(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="curl",
            exit_code=1,
            stderr="connect ETIMEDOUT 1.2.3.4:443",
            hints_db=hints_db,
        )
        assert result.is_transient

    def test_not_transient_for_logic_error(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="python3",
            exit_code=1,
            stderr="AssertionError: expected True",
            hints_db=hints_db,
        )
        assert not result.is_transient

    def test_recovery_hints_match_tool_specific(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="GraphQL: Could not resolve to a node",
            hints_db=hints_db,
        )
        assert any("verify" in h.lower() for h in result.recovery_hints)

    def test_recovery_hints_match_general(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="curl",
            exit_code=1,
            stderr="ECONNREFUSED",
            hints_db=hints_db,
        )
        assert any("network" in h.lower() for h in result.recovery_hints)

    def test_classified_error_fields(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="HTTP 403 forbidden",
            hints_db=hints_db,
        )
        assert isinstance(result, ClassifiedError)
        assert result.tool_name == "gh"
        assert result.exit_code == 1
        assert result.stderr == "HTTP 403 forbidden"

    def test_empty_call_history(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="error",
            call_history=[],
            hints_db=hints_db,
        )
        assert result.error_type is ErrorType.TOOL_FAILURE

    def test_none_call_history(self, hints_db: HintsDB) -> None:
        result = classify_error(
            tool_name="gh",
            exit_code=1,
            stderr="error",
            call_history=None,
            hints_db=hints_db,
        )
        assert result.error_type is ErrorType.TOOL_FAILURE


# ---------------------------------------------------------------------------
# log_error
# ---------------------------------------------------------------------------


class TestLogError:
    def test_creates_log_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        classified = ClassifiedError(
            error_type=ErrorType.TOOL_FAILURE,
            tool_name="gh",
            exit_code=1,
            stderr="HTTP 403",
            is_transient=False,
            recovery_hints=("Wait 60s",),
        )
        log_error(classified, recovery_action="wait_and_retry", success=True, log_path=log_path)
        assert log_path.exists()

    def test_appends_jsonl_entries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        classified = ClassifiedError(
            error_type=ErrorType.TOOL_FAILURE,
            tool_name="gh",
            exit_code=1,
            stderr="error",
            is_transient=False,
            recovery_hints=(),
        )
        log_error(classified, recovery_action="retry", success=True, log_path=log_path)
        log_error(classified, recovery_action="fallback", success=False, log_path=log_path)

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["tool"] == "gh"
        assert entry1["success"] is True

        entry2 = json.loads(lines[1])
        assert entry2["recovery"] == "fallback"
        assert entry2["success"] is False

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nested" / "dir" / "errors.jsonl"
        classified = ClassifiedError(
            error_type=ErrorType.INFINITE_LOOP,
            tool_name="git",
            exit_code=1,
            stderr="loop",
            is_transient=False,
            recovery_hints=(),
        )
        log_error(classified, recovery_action="break_loop", success=True, log_path=log_path)
        assert log_path.exists()


# ---------------------------------------------------------------------------
# get_graduation_candidates
# ---------------------------------------------------------------------------


def _make_entry(
    tool: str,
    recovery: str,
    success: bool,
    timestamp: str = "2026-01-01T00:00:00Z",
) -> dict[str, str | int | bool]:
    """Create a test error log entry."""
    return {
        "timestamp": timestamp,
        "error_type": "tool_failure",
        "tool": tool,
        "exit_code": 1,
        "recovery": recovery,
        "success": success,
    }


class TestGetGraduationCandidates:
    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        candidates = get_graduation_candidates(tmp_path / "nonexistent.jsonl")
        assert candidates == []

    def test_identifies_patterns_at_threshold(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        entries = [
            _make_entry("gh", "wait_and_retry", True, "2026-01-01T00:00:00Z"),
            _make_entry("gh", "wait_and_retry", True, "2026-01-01T00:01:00Z"),
            _make_entry("gh", "wait_and_retry", True, "2026-01-01T00:02:00Z"),
        ]
        log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        candidates = get_graduation_candidates(log_path, threshold=3)
        assert len(candidates) == 1
        assert candidates[0]["tool"] == "gh"
        assert candidates[0]["recovery"] == "wait_and_retry"
        assert candidates[0]["count"] == 3

    def test_excludes_below_threshold(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        entries = [
            _make_entry("gh", "retry", True, "2026-01-01T00:00:00Z"),
            _make_entry("gh", "retry", True, "2026-01-01T00:01:00Z"),
        ]
        log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        candidates = get_graduation_candidates(log_path, threshold=3)
        assert candidates == []

    def test_ignores_failed_recoveries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        entries = [
            _make_entry("gh", "retry", False, "2026-01-01T00:00:00Z"),
            _make_entry("gh", "retry", False, "2026-01-01T00:01:00Z"),
            _make_entry("gh", "retry", False, "2026-01-01T00:02:00Z"),
        ]
        log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        candidates = get_graduation_candidates(log_path, threshold=3)
        assert candidates == []

    def test_handles_malformed_entries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        valid_entry = json.dumps(_make_entry("gh", "retry", True))
        content = f'not valid json\n{{"partial": true}}\n{valid_entry}\n'
        log_path.write_text(content)

        # Should not raise, gracefully skips malformed lines.
        candidates = get_graduation_candidates(log_path, threshold=1)
        assert len(candidates) == 1

    def test_sorts_by_count_descending(self, tmp_path: Path) -> None:
        log_path = tmp_path / "errors.jsonl"
        entries = [
            _make_entry("gh", "retry", True),
            _make_entry("git", "reset", True),
            _make_entry("git", "reset", True),
        ]
        log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        candidates = get_graduation_candidates(log_path, threshold=1)
        assert len(candidates) == 2
        assert candidates[0]["tool"] == "git"
        assert candidates[0]["count"] == 2
        assert candidates[1]["tool"] == "gh"
        assert candidates[1]["count"] == 1
