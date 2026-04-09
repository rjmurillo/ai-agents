#!/usr/bin/env bash
# ADR-035 exit code handler for GitHub Actions workflows.
#
# Provides run_with_adr035() which wraps a command with:
#   - Retry logic for exit code 3 (transient/external errors)
#   - Fail-fast for exit code 2 (config errors)
#   - Fail-fast for exit code 4 (auth errors)
#   - Passthrough for exit code 0 (success) and 1 (logic error)
#
# Usage:
#   source .github/scripts/exit_code_handler.sh
#   run_with_adr035 python3 .github/scripts/post_issue_comment.py --issue 42 --body "hello"
#
# Exit codes (ADR-035):
#   0 - Success
#   1 - Logic/validation error
#   2 - Configuration error (fail-fast)
#   3 - External service error (retried, then fails)
#   4 - Authentication error (fail-fast)

# Max retry attempts for transient failures (exit code 3)
ADR035_MAX_RETRIES="${ADR035_MAX_RETRIES:-2}"

# Base delay in seconds between retries (multiplied by attempt number)
ADR035_RETRY_DELAY="${ADR035_RETRY_DELAY:-5}"

run_with_adr035() {
  local attempt=0
  local exit_code=0

  while [ "$attempt" -le "$ADR035_MAX_RETRIES" ]; do
    exit_code=0
    "$@" || exit_code=$?

    case "$exit_code" in
      0)
        return 0
        ;;
      2)
        echo "::error::Configuration error (ADR-035 exit 2). Check script arguments."
        return 2
        ;;
      3)
        if [ "$attempt" -lt "$ADR035_MAX_RETRIES" ]; then
          attempt=$((attempt + 1))
          local delay=$((attempt * ADR035_RETRY_DELAY))
          echo "::warning::Transient failure (ADR-035 exit 3). Retry ${attempt}/${ADR035_MAX_RETRIES} in ${delay}s..."
          sleep "$delay"
        else
          echo "::error::External service error (ADR-035 exit 3) after $((ADR035_MAX_RETRIES + 1)) attempts."
          return 1
        fi
        ;;
      4)
        echo "::error::Authentication error (ADR-035 exit 4). Check token permissions."
        return 1
        ;;
      *)
        return "$exit_code"
        ;;
    esac
  done

  return "$exit_code"
}
