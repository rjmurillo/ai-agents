"""Tests for AI Review Common module, porting and exceeding Pester coverage."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ai_review_common import (
    assert_environment_variables,
    convert_to_json_escaped,
    extract_verdict,
    format_collapsible_section,
    format_markdown_table_row,
    format_verdict_alert,
    get_labels,
    get_labels_from_ai_output,
    get_milestone,
    get_milestone_from_ai_output,
    get_verdict,
    initialize_ai_review,
    invoke_with_retry,
    write_log,
    write_log_error,
)

# ---------------------------------------------------------------------------
# Label parsing
# ---------------------------------------------------------------------------


class TestGetLabels:
    def test_single_label(self):
        labels = get_labels("Analysis complete. LABEL: bug")
        assert labels == ["bug"]

    def test_multiple_labels(self):
        labels = get_labels("LABEL: bug LABEL: enhancement LABEL: priority-high")
        assert len(labels) == 3
        assert "bug" in labels
        assert "enhancement" in labels
        assert "priority-high" in labels

    def test_no_labels(self):
        assert get_labels("No labels here") == []

    def test_empty_input(self):
        assert get_labels("") == []

    def test_whitespace_only(self):
        assert get_labels("   ") == []

    def test_multiline_output(self):
        output = "Review analysis:\nLABEL: security\nLABEL: needs-review\nSummary complete."
        labels = get_labels(output)
        assert len(labels) == 2
        assert "security" in labels
        assert "needs-review" in labels

    def test_adjacent_labels(self):
        labels = get_labels("LABEL:bug LABEL:urgent")
        assert len(labels) == 2


# ---------------------------------------------------------------------------
# Milestone parsing
# ---------------------------------------------------------------------------


class TestGetMilestone:
    def test_extracts_milestone(self):
        assert get_milestone("MILESTONE: v2.0 VERDICT: PASS") == "v2.0"

    def test_no_milestone(self):
        assert get_milestone("No milestone specified") == ""

    def test_empty_input(self):
        assert get_milestone("") == ""

    def test_whitespace_only(self):
        assert get_milestone("   ") == ""

    def test_milestone_with_numbers(self):
        assert get_milestone("MILESTONE: Sprint-42") == "Sprint-42"


# ---------------------------------------------------------------------------
# Formatting: collapsible section
# ---------------------------------------------------------------------------


class TestFormatCollapsibleSection:
    def test_valid_html(self):
        result = format_collapsible_section("Details", "Inner content")
        assert "<details>" in result
        assert "</details>" in result
        assert "<summary>Details</summary>" in result
        assert "Inner content" in result

    def test_multiline_content(self):
        content = "Line 1\nLine 2\nLine 3"
        result = format_collapsible_section("Multi", content)
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result


# ---------------------------------------------------------------------------
# Formatting: verdict alert
# ---------------------------------------------------------------------------


class TestFormatVerdictAlert:
    def test_pass_tip(self):
        result = format_verdict_alert("PASS")
        assert "[!TIP]" in result
        assert "Verdict: PASS" in result

    def test_warn_warning(self):
        result = format_verdict_alert("WARN")
        assert "[!WARNING]" in result

    def test_critical_fail_caution(self):
        result = format_verdict_alert("CRITICAL_FAIL")
        assert "[!CAUTION]" in result

    def test_rejected_caution(self):
        result = format_verdict_alert("REJECTED")
        assert "[!CAUTION]" in result

    def test_includes_message(self):
        result = format_verdict_alert("PASS", "All checks passed")
        assert "All checks passed" in result

    def test_unknown_note(self):
        result = format_verdict_alert("UNKNOWN")
        assert "[!NOTE]" in result


# ---------------------------------------------------------------------------
# Formatting: markdown table row
# ---------------------------------------------------------------------------


class TestFormatMarkdownTableRow:
    def test_three_columns(self):
        assert format_markdown_table_row(["A", "B", "C"]) == "| A | B | C |"

    def test_single_column(self):
        assert format_markdown_table_row(["Single"]) == "| Single |"

    def test_many_columns(self):
        assert format_markdown_table_row(["A", "B", "C", "D", "E"]) == "| A | B | C | D | E |"


# ---------------------------------------------------------------------------
# Formatting: JSON escaping
# ---------------------------------------------------------------------------


class TestConvertToJsonEscaped:
    def test_escape_quotes(self):
        assert convert_to_json_escaped('Hello "World"') == '"Hello \\"World\\""'

    def test_empty_string(self):
        assert convert_to_json_escaped("") == '""'

    def test_special_characters(self):
        result = convert_to_json_escaped("Line1\nLine2")
        assert "\\n" in result

    def test_plain_string(self):
        assert convert_to_json_escaped("test") == '"test"'


# ---------------------------------------------------------------------------
# Workflow: initialization
# ---------------------------------------------------------------------------


class TestInitializeAIReview:
    def test_creates_directory(self, tmp_path: Path):
        target = tmp_path / "ai-review-test"
        result = initialize_ai_review(str(target))
        assert target.exists()
        assert result == str(target)

    def test_returns_path(self, tmp_path: Path):
        target = tmp_path / "existing"
        target.mkdir()
        result = initialize_ai_review(str(target))
        assert result == str(target)

    def test_uses_env_var(self, tmp_path: Path):
        target = str(tmp_path / "env-dir")
        with patch.dict(os.environ, {"AI_REVIEW_DIR": target}):
            result = initialize_ai_review()
        assert result == target
        assert Path(target).exists()


# ---------------------------------------------------------------------------
# Workflow: retry logic
# ---------------------------------------------------------------------------


class TestInvokeWithRetry:
    def test_returns_on_success(self):
        assert invoke_with_retry(lambda: "success", max_retries=3, initial_delay=0) == "success"

    def test_retries_and_succeeds(self):
        attempts = {"count": 0}

        def _flaky():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise ValueError("Temporary failure")
            return "success after retry"

        result = invoke_with_retry(_flaky, max_retries=3, initial_delay=0)
        assert result == "success after retry"
        assert attempts["count"] == 2

    def test_raises_after_max_retries(self):
        def _always_fail():
            raise ValueError("Permanent failure")

        with pytest.raises(RuntimeError, match="All 2 attempts failed"):
            invoke_with_retry(_always_fail, max_retries=2, initial_delay=0)

    def test_exponential_backoff(self):
        delays: list[float] = []

        def _mock_sleep(seconds):
            delays.append(seconds)

        def _always_fail():
            raise ValueError("fail")

        with patch("time.sleep", side_effect=_mock_sleep):
            with pytest.raises(RuntimeError):
                invoke_with_retry(_always_fail, max_retries=3, initial_delay=1)

        assert delays == [1, 2]


# ---------------------------------------------------------------------------
# Workflow: logging
# ---------------------------------------------------------------------------


class TestWriteLog:
    def test_logs_message(self, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            write_log("Test message")
        assert "Test message" in caplog.text


class TestWriteLogError:
    def test_logs_error(self, caplog):
        import logging

        with caplog.at_level(logging.ERROR):
            write_log_error("Failure message")
        assert "ERROR: Failure message" in caplog.text


# ---------------------------------------------------------------------------
# Workflow: environment validation
# ---------------------------------------------------------------------------


class TestAssertEnvironmentVariables:
    def test_passes_when_all_set(self):
        with patch.dict(os.environ, {"VAR_A": "1", "VAR_B": "2"}):
            assert_environment_variables(["VAR_A", "VAR_B"])

    def test_raises_when_missing(self):
        with patch.dict(os.environ, {"VAR_A": "1"}, clear=False):
            os.environ.pop("MISSING_VAR", None)
            with pytest.raises(RuntimeError, match="MISSING_VAR"):
                assert_environment_variables(["VAR_A", "MISSING_VAR"])

    def test_lists_all_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MISS_A", None)
            os.environ.pop("MISS_B", None)
            with pytest.raises(RuntimeError, match=r"MISS_A.*MISS_B"):
                assert_environment_variables(["MISS_A", "MISS_B"])

    def test_empty_string_is_missing(self):
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            with pytest.raises(RuntimeError, match="EMPTY_VAR"):
                assert_environment_variables(["EMPTY_VAR"])


# ---------------------------------------------------------------------------
# Security-hardened JSON parsing: labels
# ---------------------------------------------------------------------------


class TestGetLabelsFromAIOutput:
    def test_single_valid_label(self):
        labels = get_labels_from_ai_output('{"labels":["bug"]}')
        assert labels == ["bug"]

    def test_multiple_valid_labels(self):
        labels = get_labels_from_ai_output('{"labels":["bug","enhancement","docs"]}')
        assert len(labels) == 3
        assert "bug" in labels

    def test_labels_with_hyphens(self):
        labels = get_labels_from_ai_output('{"labels":["priority-high","needs-review"]}')
        assert "priority-high" in labels

    def test_labels_with_underscores(self):
        labels = get_labels_from_ai_output('{"labels":["good_first_issue"]}')
        assert "good_first_issue" in labels

    def test_labels_with_periods(self):
        labels = get_labels_from_ai_output('{"labels":["v1.0.0"]}')
        assert "v1.0.0" in labels

    def test_labels_with_spaces(self):
        labels = get_labels_from_ai_output('{"labels":["help wanted","good first issue"]}')
        assert len(labels) == 2
        assert "help wanted" in labels

    def test_rejects_semicolon_injection(self):
        assert get_labels_from_ai_output('{"labels":["bug; rm -rf /"]}') == []

    def test_rejects_backtick_injection(self):
        assert get_labels_from_ai_output('{"labels":["bug`whoami`"]}') == []

    def test_rejects_dollar_injection(self):
        assert get_labels_from_ai_output('{"labels":["bug$(whoami)"]}') == []

    def test_rejects_pipe_injection(self):
        assert get_labels_from_ai_output('{"labels":["bug | curl evil.com"]}') == []

    def test_rejects_newline_injection(self):
        assert get_labels_from_ai_output('{"labels":["bug\\ninjected"]}') == []

    def test_empty_array(self):
        assert get_labels_from_ai_output('{"labels":[]}') == []

    def test_whitespace_only_label_in_array(self):
        # REQ-008-07: a label that is only whitespace inside a non-empty array
        # is skipped, not emitted. Exercises the per-label whitespace guard
        # (verdict.py:257-258) that the empty-array case at line 251 does not
        # reach, since the array_content here ("  ") is non-empty.
        assert get_labels_from_ai_output('{"labels":["  "]}') == []

    def test_missing_key(self):
        assert get_labels_from_ai_output('{"milestone":"v1"}') == []

    def test_null_input(self):
        assert get_labels_from_ai_output(None) == []

    def test_empty_input(self):
        assert get_labels_from_ai_output("") == []

    def test_whitespace_input(self):
        assert get_labels_from_ai_output("   ") == []

    def test_rejects_over_50_chars(self):
        long_label = "a" * 51
        assert get_labels_from_ai_output(f'{{"labels":["{long_label}"]}}') == []

    def test_rejects_leading_special_char(self):
        assert get_labels_from_ai_output('{"labels":["-invalid"]}') == []
        assert get_labels_from_ai_output('{"labels":["_bad"]}') == []
        assert get_labels_from_ai_output('{"labels":[".wrong"]}') == []

    def test_mixed_valid_and_invalid(self):
        output = '{"labels":["bug","evil; rm -rf /","enhancement"]}'
        labels = get_labels_from_ai_output(output)
        assert len(labels) == 2
        assert "bug" in labels
        assert "enhancement" in labels
        assert "evil; rm -rf /" not in labels


# ---------------------------------------------------------------------------
# Security-hardened JSON parsing: milestones
# ---------------------------------------------------------------------------


class TestGetMilestoneFromAIOutput:
    def test_semantic_version(self):
        assert get_milestone_from_ai_output('{"milestone":"v1.2.0"}') == "v1.2.0"

    def test_alphanumeric(self):
        assert get_milestone_from_ai_output('{"milestone":"Sprint42"}') == "Sprint42"

    def test_with_hyphens(self):
        assert get_milestone_from_ai_output('{"milestone":"Q4-2024"}') == "Q4-2024"

    def test_with_spaces(self):
        assert get_milestone_from_ai_output('{"milestone":"Release 2.0"}') == "Release 2.0"

    def test_rejects_semicolon_injection(self):
        assert get_milestone_from_ai_output('{"milestone":"v1; rm -rf /"}') is None

    def test_rejects_pipe_injection(self):
        assert get_milestone_from_ai_output('{"milestone":"v1 | curl evil.com"}') is None

    def test_empty_value(self):
        assert get_milestone_from_ai_output('{"milestone":""}') is None

    def test_missing_key(self):
        assert get_milestone_from_ai_output('{"labels":["bug"]}') is None

    def test_null_input(self):
        assert get_milestone_from_ai_output(None) is None

    def test_empty_input(self):
        assert get_milestone_from_ai_output("") is None

    def test_rejects_over_50_chars(self):
        long = "v" + "1" * 50
        assert get_milestone_from_ai_output(f'{{"milestone":"{long}"}}') is None


# ---------------------------------------------------------------------------
# Integration: complete AI output parsing
# ---------------------------------------------------------------------------


class TestJSONParsingIntegration:
    def test_complete_triage_output(self):
        output = json.dumps(
            {
                "category": "bug",
                "labels": ["bug", "critical", "needs-triage"],
                "milestone": "v1.2.0",
                "confidence": 0.95,
            }
        )
        labels = get_labels_from_ai_output(output)
        milestone = get_milestone_from_ai_output(output)
        assert len(labels) == 3
        assert "bug" in labels
        assert milestone == "v1.2.0"

    def test_messy_whitespace_output(self):
        output = (
            '{\n    "labels" : [ "enhancement" , "documentation" ] ,'
            '\n    "milestone" : "Sprint 42"\n}'
        )
        labels = get_labels_from_ai_output(output)
        milestone = get_milestone_from_ai_output(output)
        assert len(labels) == 2
        assert milestone == "Sprint 42"

    def test_malicious_inputs_never_throw(self):
        malicious = [
            '{"labels":["$(whoami)","${IFS}cat${IFS}/etc/passwd"]}',
            '{"milestone":"v1`id`"}',
            '{"labels":["\\x00\\x00"]}',
            '{"labels":["<script>alert(1)</script>"]}',
        ]
        for inp in malicious:
            get_labels_from_ai_output(inp)
            get_milestone_from_ai_output(inp)


# ---------------------------------------------------------------------------
# Regression: security review output truncation (#2006)
# ---------------------------------------------------------------------------

# Captured from PR #2004's Security Review (run 25642461341): four PASS findings,
# then output stopped mid-sentence during the 4th finding with NO verdict line.
# With the verdict at the END, truncation drops it and the parser cannot recover
# the verdict, so the CI action falls through to NEEDS_REVIEW and blocks the PR.
_TRUNCATED_SECURITY_OUTPUT = (
    "#### 1. Path Traversal Prevention - [PASS]\n"
    "realpath() before startswith() check (CWE-22)\n\n"
    "#### 2. Path Containment - [PASS]\n"
    "validates path is within repo root\n\n"
    "#### 3. Subprocess Security - [PASS]\n"
    "All subprocess calls use list-based argv and explicit timeout=\n\n"
    "#### 4. Exception Handling - [PASS]\n"
    "**Location**: complete_session_log.py:383-399\n"
    "The broad `except Exception`"
)


class TestSecurityTruncationRegression:
    """#2006: the security prompt now emits the VERDICT on the first line, so a
    review truncated by the output budget is still parseable."""

    def test_trailing_verdict_lost_to_truncation_is_unparseable(self):
        # Old shape: the verdict was a final line, so truncation leaves no
        # ``Verdict:`` line. extract_verdict returns UNKNOWN, mirroring the CI
        # action's fall-through to NEEDS_REVIEW (both mean "no verdict found").
        assert extract_verdict(_TRUNCATED_SECURITY_OUTPUT) == "UNKNOWN"

    def test_leading_verdict_survives_truncation(self):
        # New shape (#2006): VERDICT first. Even when the findings below are cut
        # off, the verdict is recovered by both verdict parsers.
        leading = (
            "VERDICT: PASS\nMESSAGE: No security issues found\n\n" + _TRUNCATED_SECURITY_OUTPUT
        )
        assert extract_verdict(leading) == "PASS"
        assert get_verdict(leading) == "PASS"

    def test_single_leading_verdict_is_canonical(self):
        # One leading verdict means the last-match-wins parsers return it
        # unambiguously; there is no trailing duplicate to be truncated away.
        leading = "VERDICT: CRITICAL_FAIL\nMESSAGE: SQL injection at db.py:12\n\nfindings"
        assert extract_verdict(leading) == "CRITICAL_FAIL"
