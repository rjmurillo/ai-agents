#!/bin/bash
# Common functions for AI review workflows
# Source this file in workflow scripts: source .github/scripts/ai-review-common.sh

set -euo pipefail

# Configuration
AI_REVIEW_DIR="${AI_REVIEW_DIR:-/tmp/ai-review}"
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_DELAY="${RETRY_DELAY:-30}"

# Initialize working directory
init_ai_review() {
    mkdir -p "$AI_REVIEW_DIR"
    echo "AI Review working directory: $AI_REVIEW_DIR"
}

# Retry a command with exponential backoff
# Usage: retry_with_backoff "command" [max_retries] [initial_delay]
retry_with_backoff() {
    local cmd="$1"
    local max_retries="${2:-$MAX_RETRIES}"
    local delay="${3:-$RETRY_DELAY}"

    for ((i=1; i<=max_retries; i++)); do
        if eval "$cmd"; then
            return 0
        fi
        echo "Attempt $i/$max_retries failed, retrying in ${delay}s..."
        sleep "$delay"
        delay=$((delay * 2))
    done

    echo "All $max_retries attempts failed"
    return 1
}

# Post or update a PR comment idempotently
# Usage: post_pr_comment <pr_number> <comment_file> <marker>
post_pr_comment() {
    local pr_number="$1"
    local comment_file="$2"
    local marker="${3:-AI-REVIEW}"

    if [ ! -f "$comment_file" ]; then
        echo "Error: Comment file not found: $comment_file"
        return 1
    fi

    # Add marker to comment for idempotency
    local comment_body
    comment_body="<!-- $marker -->"$'\n'$(cat "$comment_file")

    # Check for existing comment with this marker
    local existing_comment_id
    existing_comment_id=$(gh pr view "$pr_number" --json comments -q ".comments[] | select(.body | contains(\"<!-- $marker -->\")) | .databaseId" 2>/dev/null | head -1 || echo "")

    if [ -n "$existing_comment_id" ]; then
        echo "Updating existing comment (ID: $existing_comment_id)"
        echo "$comment_body" | gh pr comment "$pr_number" --edit-last --body-file - 2>/dev/null || \
        echo "$comment_body" | gh pr comment "$pr_number" --body-file -
    else
        echo "Creating new comment"
        echo "$comment_body" | gh pr comment "$pr_number" --body-file -
    fi
}

# Post or update an issue comment idempotently
# Usage: post_issue_comment <issue_number> <comment_file> <marker>
post_issue_comment() {
    local issue_number="$1"
    local comment_file="$2"
    local marker="${3:-AI-TRIAGE}"

    if [ ! -f "$comment_file" ]; then
        echo "Error: Comment file not found: $comment_file"
        return 1
    fi

    # Add marker to comment for idempotency
    local comment_body
    comment_body="<!-- $marker -->"$'\n'$(cat "$comment_file")

    echo "Posting comment to issue #$issue_number"
    echo "$comment_body" | gh issue comment "$issue_number" --body-file -
}

# Parse verdict from AI output
# Usage: verdict=$(parse_verdict "$output")
parse_verdict() {
    local output="$1"

    # Try explicit VERDICT: pattern first
    local verdict
    verdict=$(echo "$output" | grep -oP '(?<=VERDICT:\s*)[A-Z_]+' | head -1 || echo "")

    if [ -n "$verdict" ]; then
        echo "$verdict"
        return
    fi

    # Fall back to keyword detection
    if echo "$output" | grep -qi "CRITICAL_FAIL\|critical failure\|severe issue"; then
        echo "CRITICAL_FAIL"
    elif echo "$output" | grep -qi "REJECTED\|reject\|must fix\|blocking"; then
        echo "REJECTED"
    elif echo "$output" | grep -qi "PASS\|approved\|looks good\|no issues"; then
        echo "PASS"
    else
        echo "WARN"
    fi
}

# Parse labels from AI output
# Usage: labels=$(parse_labels "$output")
parse_labels() {
    local output="$1"

    # Extract LABEL: entries and format as JSON array
    echo "$output" | grep -oP '(?<=LABEL:\s*)\S+' | jq -R -s -c 'split("\n") | map(select(length > 0))' 2>/dev/null || echo "[]"
}

# Parse milestone from AI output
# Usage: milestone=$(parse_milestone "$output")
parse_milestone() {
    local output="$1"

    echo "$output" | grep -oP '(?<=MILESTONE:\s*)\S+' | head -1 || echo ""
}

# Aggregate multiple verdicts into a final verdict
# Usage: final_verdict=$(aggregate_verdicts "${verdicts[@]}")
aggregate_verdicts() {
    local verdicts=("$@")
    local final="PASS"

    for verdict in "${verdicts[@]}"; do
        case "$verdict" in
            CRITICAL_FAIL|REJECTED)
                final="CRITICAL_FAIL"
                break
                ;;
            WARN)
                if [ "$final" = "PASS" ]; then
                    final="WARN"
                fi
                ;;
        esac
    done

    echo "$final"
}

# Format a collapsible details section for GitHub markdown
# Usage: format_details "title" "content"
format_details() {
    local title="$1"
    local content="$2"

    cat << EOF
<details>
<summary>$title</summary>

$content

</details>
EOF
}

# Get exit code based on verdict
# Usage: exit_code=$(get_exit_code "$verdict")
get_exit_code() {
    local verdict="$1"

    case "$verdict" in
        CRITICAL_FAIL|REJECTED)
            echo "1"
            ;;
        *)
            echo "0"
            ;;
    esac
}

# Log with timestamp
# Usage: log "message"
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Log error with timestamp
# Usage: log_error "message"
log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

# Check if required environment variables are set
# Usage: require_env "VAR1" "VAR2"
require_env() {
    local missing=()
    for var in "$@"; do
        if [ -z "${!var:-}" ]; then
            missing+=("$var")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required environment variables: ${missing[*]}"
        return 1
    fi
}

# Get changed files in a PR matching a pattern
# Usage: changed_files=$(get_changed_files "$pr_number" "*.md")
get_changed_files() {
    local pr_number="$1"
    local pattern="${2:-*}"

    gh pr diff "$pr_number" --name-only 2>/dev/null | grep -E "$pattern" || echo ""
}

# Escape string for JSON
# Usage: escaped=$(json_escape "$string")
json_escape() {
    local string="$1"
    echo "$string" | jq -Rs '.'
}

# Format a table row for markdown
# Usage: table_row "col1" "col2" "col3"
table_row() {
    local IFS='|'
    echo "| $* |"
}

# Initialize on source
init_ai_review
