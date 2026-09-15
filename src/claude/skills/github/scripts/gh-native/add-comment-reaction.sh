#!/usr/bin/env bash
# Synopsis: Add emoji reaction to comment
# Usage: add-comment-reaction.sh --comment-id <id> --reaction <reaction> [--comment-type (issue|review)] [--owner <owner>] [--repo <repo>]
#
# Exit codes (ADR-035):
#   0 - Success
#   1 - Invalid parameters / logic error
#   2 - Not found
#   3 - External error (API failure)
#   4 - Auth error

set -euo pipefail

COMMENT_ID=""
REACTION=""
COMMENT_TYPE="issue"
OWNER=""
REPO=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --comment-id)
            COMMENT_ID="$2"
            shift 2
            ;;
        --reaction)
            REACTION="$2"
            shift 2
            ;;
        --comment-type)
            COMMENT_TYPE="$2"
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

if [[ -z "$COMMENT_ID" || -z "$REACTION" ]]; then
    echo "Error: --comment-id and --reaction are required" >&2
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

# Determine API endpoint based on comment type
if [[ "$COMMENT_TYPE" == "review" ]]; then
    API_PATH="repos/$OWNER/$REPO/pulls/comments/$COMMENT_ID/reactions"
else
    API_PATH="repos/$OWNER/$REPO/issues/comments/$COMMENT_ID/reactions"
fi

# Add reaction
if ! gh api "$API_PATH" -X POST -f content="$REACTION" >/dev/null 2>&1; then
    jq -n \
      --arg owner "$OWNER" \
      --arg repo "$REPO" \
      --argjson comment_id "$COMMENT_ID" \
      --arg comment_type "$COMMENT_TYPE" \
      --arg reaction "$REACTION" \
      '{
        success: false,
        comment_id: $comment_id,
        comment_type: $comment_type,
        reaction: $reaction,
        error: "Failed to add reaction",
        error_code: 3,
        owner: $owner,
        repo: $repo
      }'
    exit 3
fi

jq -n \
  --arg owner "$OWNER" \
  --arg repo "$REPO" \
  --argjson comment_id "$COMMENT_ID" \
  --arg comment_type "$COMMENT_TYPE" \
  --arg reaction "$REACTION" \
  '{
    success: true,
    comment_id: $comment_id,
    comment_type: $comment_type,
    reaction: $reaction,
    owner: $owner,
    repo: $repo
  }'

exit 0
