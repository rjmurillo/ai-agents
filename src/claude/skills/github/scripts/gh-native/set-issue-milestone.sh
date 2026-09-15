#!/usr/bin/env bash
# Synopsis: Set milestone on issue directly via gh CLI
# Usage: set-issue-milestone.sh --issue <number> --milestone <name> [--owner <owner>] [--repo <repo>]
#
# Exit codes (ADR-035):
#   0 - Success
#   1 - Invalid parameters / logic error
#   2 - Not found
#   3 - External error (API failure)
#   4 - Auth error

set -euo pipefail

ISSUE_NUMBER=""
MILESTONE=""
OWNER=""
REPO=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --issue)
            ISSUE_NUMBER="$2"
            shift 2
            ;;
        --milestone)
            MILESTONE="$2"
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

if [[ -z "$ISSUE_NUMBER" || -z "$MILESTONE" ]]; then
    echo "Error: --issue and --milestone are required" >&2
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

# Set milestone
if ! gh issue edit "$ISSUE_NUMBER" --repo "$REPO_FLAG" --milestone "$MILESTONE" >/dev/null 2>&1; then
    jq -n \
      --arg owner "$OWNER" \
      --arg repo "$REPO" \
      --argjson issue "$ISSUE_NUMBER" \
      --arg milestone "$MILESTONE" \
      '{
        success: false,
        issue: $issue,
        milestone: $milestone,
        action: "failed",
        owner: $owner,
        repo: $repo,
        error_code: 3
      }'
    exit 3
fi

jq -n \
  --arg owner "$OWNER" \
  --arg repo "$REPO" \
  --argjson issue "$ISSUE_NUMBER" \
  --arg milestone "$MILESTONE" \
  '{
    success: true,
    issue: $issue,
    milestone: $milestone,
    action: "set",
    owner: $owner,
    repo: $repo
  }'

exit 0
