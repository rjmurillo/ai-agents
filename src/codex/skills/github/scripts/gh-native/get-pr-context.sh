#!/usr/bin/env bash
# Synopsis: Get PR context directly via gh CLI
# Usage: get-pr-context.sh --pull-request <number> [--owner <owner>] [--repo <repo>] [--include-diff] [--include-changed-files] [--diff-stat]
#
# Exit codes (ADR-035):
#   0 - Success
#   1 - Invalid parameters / logic error
#   2 - Not found
#   3 - External error (API failure)
#   4 - Auth error

set -euo pipefail

PR_NUMBER=""
OWNER=""
REPO=""
INCLUDE_DIFF=false
INCLUDE_CHANGED_FILES=false
DIFF_STAT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pull-request)
            PR_NUMBER="$2"
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
        --include-diff)
            INCLUDE_DIFF=true
            shift
            ;;
        --include-changed-files)
            INCLUDE_CHANGED_FILES=true
            shift
            ;;
        --diff-stat)
            DIFF_STAT=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$PR_NUMBER" ]]; then
    echo "Error: --pull-request is required" >&2
    exit 1
fi

# Resolve repo params if not provided
if [[ -z "$OWNER" || -z "$REPO" ]]; then
    repo_info=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null) || {
        echo "Error: Could not determine repository" >&2
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

# Get PR metadata
JSON_FIELDS="number,title,body,headRefName,baseRefName,state,author,labels,reviewRequests,commits,additions,deletions,changedFiles,mergeable,mergedAt,mergedBy,createdAt,updatedAt"

if ! pr_output=$(gh pr view "$PR_NUMBER" --repo "$REPO_FLAG" --json "$JSON_FIELDS" 2>&1); then
    if echo "$pr_output" | grep -q "not found"; then
        exit 2
    fi
    exit 3
fi

# Process the JSON output and build our response
# Using jq for robust JSON handling
pr_data=$(cat <<'EOF'
.
EOF
)

# Extract optional diff/files if requested
DIFF_CONTENT=""
if [[ "$INCLUDE_DIFF" == "true" ]]; then
    DIFF_ARGS=("gh" "pr" "diff" "$PR_NUMBER" "--repo" "$REPO_FLAG")
    if [[ "$DIFF_STAT" == "true" ]]; then
        DIFF_ARGS+=("--stat")
    fi
    if diff_result=$("${DIFF_ARGS[@]}" 2>&1); then
        DIFF_CONTENT="$diff_result"
    fi
fi

FILES_CONTENT=""
if [[ "$INCLUDE_CHANGED_FILES" == "true" ]]; then
    if files_result=$(gh pr diff "$PR_NUMBER" --repo "$REPO_FLAG" --name-only 2>&1); then
        FILES_CONTENT="$files_result"
    fi
fi

# Build the output JSON using jq
output=$(echo "$pr_output" | jq \
  --arg owner "$OWNER" \
  --arg repo "$REPO" \
  --arg diff "$DIFF_CONTENT" \
  --arg files "$FILES_CONTENT" \
  '
  {
    success: true,
    number: .number,
    title: .title,
    body: .body,
    state: .state,
    author: (.author.login // null),
    head_branch: .headRefName,
    base_branch: .baseRefName,
    labels: [.labels[].name],
    commits: (.commits | length),
    additions: .additions,
    deletions: .deletions,
    changed_files: .changedFiles,
    mergeable: .mergeable,
    merged: (.mergedAt != null),
    merged_by: (.mergedBy.login // null),
    created_at: .createdAt,
    updated_at: .updatedAt,
    diff: ($diff | if . == "" then null else . end),
    files: ($files | if . == "" then null else split("\n") | map(select(length > 0)) end),
    owner: $owner,
    repo: $repo
  }
')

echo "$output" | jq .
exit 0
