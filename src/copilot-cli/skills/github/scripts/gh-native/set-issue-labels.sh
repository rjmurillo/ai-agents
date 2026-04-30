#!/usr/bin/env bash
# Synopsis: Add labels to issue directly via gh CLI
# Usage: set-issue-labels.sh --issue <number> --labels <label1,label2,...> [--owner <owner>] [--repo <repo>]
#
# Exit codes (ADR-035):
#   0 - Success
#   1 - Invalid parameters / logic error
#   2 - Not found
#   3 - External error (API failure)
#   4 - Auth error

set -euo pipefail

ISSUE_NUMBER=""
LABELS=""
OWNER=""
REPO=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --issue)
            ISSUE_NUMBER="$2"
            shift 2
            ;;
        --labels)
            LABELS="$2"
            shift 2
            ;;
        --owner)
            OWNER="$2"
            shift 2
            ;;
        --repo)
            REPO="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$ISSUE_NUMBER" || -z "$LABELS" ]]; then
    echo "Error: --issue and --labels are required" >&2
    exit 1
fi

# Resolve repo params if not provided
if [[ -z "$OWNER" || -z "$REPO" ]]; then
    repo_info=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null) || {
        exit 3
    }
    if [[ -z "$OWNER" ]]; then
        OWNER=$(echo "$repo_info" | cut -d'/' -f1)
    fi
    if [[ -z "$REPO" ]]; then
        REPO=$(echo "$repo_info" | cut -d'/' -f2)
    fi
fi

REPO_FLAG="$OWNER/$REPO"

# Add labels (split by comma and apply each one)
APPLIED_LABELS=()
FAILED_LABELS=()

IFS=',' read -ra LABEL_ARRAY <<< "$LABELS"
for label in "${LABEL_ARRAY[@]}"; do
    label=$(echo "$label" | xargs)  # Trim whitespace
    if gh issue edit "$ISSUE_NUMBER" --repo "$REPO_FLAG" --add-label "$label" >/dev/null 2>&1; then
        APPLIED_LABELS+=("$label")
    else
        FAILED_LABELS+=("$label")
    fi
done

# Generate output JSON using jq
SUCCESS="true"
if [[ ${#FAILED_LABELS[@]} -gt 0 ]]; then
    SUCCESS="false"
fi

APPLIED_JSON=$(printf '%s\n' "${APPLIED_LABELS[@]}" | jq -R . | jq -s .)
FAILED_JSON=$(printf '%s\n' "${FAILED_LABELS[@]}" | jq -R . | jq -s .)

jq -n \
  --arg owner "$OWNER" \
  --arg repo "$REPO" \
  --argjson applied "$APPLIED_JSON" \
  --argjson failed "$FAILED_JSON" \
  --argjson issue "$ISSUE_NUMBER" \
  --argjson success "$SUCCESS" \
  '{
    success: $success,
    issue: $issue,
    applied: $applied,
    failed: $failed,
    owner: $owner,
    repo: $repo
  }'

if [[ "$SUCCESS" == "false" ]]; then
    exit 3
fi
exit 0
