#!/usr/bin/env bash
# Synopsis: Post comment to issue directly via gh CLI
# Usage: post-issue-comment.sh --issue <number> (--body "text" | --body-file <path>) [--owner <owner>] [--repo <repo>] [--marker "text"]
#
# Exit codes (ADR-035):
#   0 - Success
#   1 - Invalid parameters / logic error
#   2 - Not found
#   3 - External error (API failure)
#   4 - Auth error

set -euo pipefail

ISSUE_NUMBER=""
BODY=""
BODY_FILE=""
OWNER=""
REPO=""
MARKER=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --issue)
            ISSUE_NUMBER="$2"
            shift 2
            ;;
        --body)
            BODY="$2"
            shift 2
            ;;
        --body-file)
            BODY_FILE="$2"
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
        --marker)
            MARKER="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$ISSUE_NUMBER" ]]; then
    echo "Error: --issue is required" >&2
    exit 1
fi

if [[ -z "$BODY" && -z "$BODY_FILE" ]]; then
    echo "Error: --body or --body-file is required" >&2
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

# Prepare body
ACTUAL_BODY="$BODY"
if [[ -n "$BODY_FILE" ]]; then
    # Resolve to absolute path and block path traversal
    RESOLVED_FILE=$(realpath -- "$BODY_FILE" 2>/dev/null) || {
        echo "Error: Cannot resolve path: $BODY_FILE" >&2
        exit 1
    }
    if [[ ! -f "$RESOLVED_FILE" ]]; then
        echo "Error: File not found: $BODY_FILE" >&2
        exit 1
    fi
    ACTUAL_BODY=$(cat -- "$RESOLVED_FILE")
fi

# Check for marker if provided
if [[ -n "$MARKER" ]]; then
    # Query existing comments to check for marker
    if gh api "repos/$OWNER/$REPO/issues/$ISSUE_NUMBER/comments" --jq '.[].body' 2>/dev/null | grep -qF -- "$MARKER"; then
        # Marker found, skip posting
        jq -n \
          --arg owner "$OWNER" \
          --arg repo "$REPO" \
          --argjson issue "$ISSUE_NUMBER" \
          '{
            success: true,
            issue: $issue,
            comment_id: null,
            action: "skipped",
            reason: "marker_found",
            owner: $owner,
            repo: $repo
          }'
        exit 0
    fi
fi

# Post comment and capture the URL to extract comment ID
COMMENT_URL=$(gh issue comment "$ISSUE_NUMBER" --repo "$REPO_FLAG" --body "$ACTUAL_BODY" 2>&1) || {
    jq -n \
      --arg owner "$OWNER" \
      --arg repo "$REPO" \
      --argjson issue "$ISSUE_NUMBER" \
      '{
        success: false,
        issue: $issue,
        comment_id: null,
        error: "Failed to post comment",
        error_code: 3,
        owner: $owner,
        repo: $repo
      }'
    exit 3
}

# Extract comment ID from the returned URL (format: .../comments/<id>)
COMMENT_ID=$(echo "$COMMENT_URL" | grep -oE '[0-9]+$' || echo "")

jq -n \
  --arg owner "$OWNER" \
  --arg repo "$REPO" \
  --argjson issue "$ISSUE_NUMBER" \
  --argjson comment_id "${COMMENT_ID:-null}" \
  '{
    success: true,
    issue: $issue,
    comment_id: $comment_id,
    action: "posted",
    owner: $owner,
    repo: $repo
  }'

exit 0
