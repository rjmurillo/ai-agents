#!/bin/bash
# Test harness for is_infrastructure_failure function
# Used by Pester tests to validate infrastructure failure detection logic

# Function to check if failure is infrastructure-related
# Extracted from action.yml for testability
is_infrastructure_failure() {
  local exit_code=$1
  local output=$2
  local stderr=$3

  # Timeout (exit code 124)
  if [ $exit_code -eq 124 ]; then
    return 0
  fi

  # Non-zero exit with no output (indicates infrastructure issue)
  if [ $exit_code -ne 0 ] && [ -z "$output" ] && [ -z "$stderr" ]; then
    return 0
  fi

  # Check stderr for infrastructure keywords
  if [ -n "$stderr" ]; then
    if echo "$stderr" | grep -qiE "(rate limit|timeout|network error|connection refused|connection reset|ECONNREFUSED|ETIMEDOUT|503|502|504)"; then
      return 0
    fi
  fi

  # Not an infrastructure failure
  return 1
}

# Main: call function with args and output result
EXIT_CODE="${1:-0}"
OUTPUT="${2:-}"
STDERR="${3:-}"

if is_infrastructure_failure "$EXIT_CODE" "$OUTPUT" "$STDERR"; then
  echo "true"
  exit 0
else
  echo "false"
  exit 0
fi
