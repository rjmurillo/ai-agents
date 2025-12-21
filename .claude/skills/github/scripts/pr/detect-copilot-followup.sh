#!/bin/bash
# Detect and analyze Copilot follow-up PR patterns
# Usage: ./detect-copilot-followup.sh <PR_NUMBER> <OWNER> <REPO>

set -euo pipefail

PR_NUMBER="${1:?PR number required}"
OWNER="${2:?Owner required}"
REPO="${3:?Repo required}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

# Query for follow-up PR matching pattern
log_info "Detecting Copilot follow-up PRs for PR #$PR_NUMBER..."

FOLLOW_UP_PATTERN="head:copilot/sub-pr-$PR_NUMBER"
log_info "Searching for: $FOLLOW_UP_PATTERN"

# Fetch follow-up PRs
FOLLOW_UP_DATA=$(gh pr list --state=open \
    --search="$FOLLOW_UP_PATTERN" \
    --json=number,title,body,headRefName,baseRefName,state,author,createdAt 2>/dev/null || echo "[]")

FOLLOW_UP_COUNT=$(echo "$FOLLOW_UP_DATA" | jq 'length')

if [ "$FOLLOW_UP_COUNT" -eq 0 ]; then
    log_success "No follow-up PRs found"
    cat <<EOF | jq '.'
{
  "found": false,
  "followUpPRs": [],
  "announcement": null,
  "analysis": null,
  "recommendation": "NO_ACTION_NEEDED",
  "message": "No follow-up PRs detected",
  "timestamp": "$(date -u +%Y-%m-%dT%TZ)"
}
EOF
    exit 0
fi

log_info "Found $FOLLOW_UP_COUNT follow-up PR(s)"

# Verify Copilot announcement
log_info "Checking for Copilot announcement..."
ANNOUNCEMENT=$(gh api repos/"$OWNER"/"$REPO"/issues/"$PR_NUMBER"/comments \
    --jq '.[] | select(.user.login == "app/copilot-swe-agent" and .body | contains("opened a new pull request")) | {id: .id, body: .body, created_at: .created_at}' 2>/dev/null || echo "null")

if [ "$ANNOUNCEMENT" = "null" ] || [ -z "$ANNOUNCEMENT" ]; then
    log_warn "No Copilot announcement found, but follow-up PR exists"
else
    log_success "Verified Copilot announcement"
fi

# Analyze each follow-up PR
ANALYSIS="[]"

echo "$FOLLOW_UP_DATA" | jq -r '.[] | @base64' | while read -r follow_up_b64; do
    FOLLOW_UP=$(echo "$follow_up_b64" | base64 -d)
    FOLLOW_UP_PR=$(echo "$FOLLOW_UP" | jq -r '.number')
    HEAD_BRANCH=$(echo "$FOLLOW_UP" | jq -r '.headRefName')
    BASE_BRANCH=$(echo "$FOLLOW_UP" | jq -r '.baseRefName')
    CREATED_AT=$(echo "$FOLLOW_UP" | jq -r '.createdAt')
    AUTHOR=$(echo "$FOLLOW_UP" | jq -r '.author.login')

    log_info "Analyzing follow-up PR #$FOLLOW_UP_PR..."

    # Get diff for follow-up PR
    DIFF=$(gh pr diff "$FOLLOW_UP_PR" --no-merges 2>/dev/null || echo "")

    # Count file changes
    FILE_COUNT=$(echo "$DIFF" | grep -c '^diff --git' || echo 0)

    # Determine category based on diff
    if [ -z "$DIFF" ] || [ "$FILE_COUNT" -eq 0 ]; then
        CATEGORY="DUPLICATE"
        SIMILARITY=100
        REASON="Follow-up PR contains no changes"
        RECOMMENDATION="CLOSE_AS_DUPLICATE"
    elif [ "$FILE_COUNT" -eq 1 ]; then
        CATEGORY="LIKELY_DUPLICATE"
        SIMILARITY=85
        REASON="Single file change matching original scope"
        RECOMMENDATION="REVIEW_THEN_CLOSE"
    else
        CATEGORY="POSSIBLE_SUPPLEMENTAL"
        SIMILARITY=40
        REASON="Multiple file changes suggest additional work"
        RECOMMENDATION="EVALUATE_FOR_MERGE"
    fi

    log_info "PR #$FOLLOW_UP_PR category: $CATEGORY (similarity: $SIMILARITY%)"

    # Build analysis entry
    cat <<EOF
{
  "followUpPRNumber": $FOLLOW_UP_PR,
  "headBranch": "$HEAD_BRANCH",
  "baseBranch": "$BASE_BRANCH",
  "createdAt": "$CREATED_AT",
  "author": "$AUTHOR",
  "category": "$CATEGORY",
  "similarity": $SIMILARITY,
  "reason": "$REASON",
  "recommendation": "$RECOMMENDATION",
  "fileCount": $FILE_COUNT
}
EOF
done | jq -s '.' > /tmp/analysis.json

ANALYSIS=$(cat /tmp/analysis.json)
rm -f /tmp/analysis.json

# Determine overall recommendation
FIRST_RECOMMENDATION=$(echo "$ANALYSIS" | jq -r '.[0].recommendation // "NO_ACTION_NEEDED"')
if [ "$(echo "$ANALYSIS" | jq 'length')" -gt 1 ]; then
    OVERALL_RECOMMENDATION="MULTIPLE_FOLLOW_UPS_REVIEW"
else
    OVERALL_RECOMMENDATION="$FIRST_RECOMMENDATION"
fi

# Output result
cat <<EOF | jq '.'
{
  "found": true,
  "originalPRNumber": $PR_NUMBER,
  "followUpPRCount": $FOLLOW_UP_COUNT,
  "announcement": $ANNOUNCEMENT,
  "analysis": $ANALYSIS,
  "recommendation": "$OVERALL_RECOMMENDATION",
  "timestamp": "$(date -u +%Y-%m-%dT%TZ)"
}
EOF
