#!/bin/bash
# Detect and analyze Copilot follow-up PR patterns
# Bash fallback for cross-platform support
#
# Usage: ./detect-copilot-followup.sh <pr_number> <owner> <repo>
#
# Pattern: Copilot creates PR with branch copilot/sub-pr-{original_pr}
# Targets original PR's base branch (not main)
# Posts announcement: "I've opened a new pull request, #{number}"

set -euo pipefail

PR_NUMBER="${1:?Usage: $0 <pr_number> <owner> <repo>}"
OWNER="${2:?Usage: $0 <pr_number> <owner> <repo>}"
REPO="${3:?Usage: $0 <pr_number> <owner> <repo>}"

# Check if a branch matches Copilot follow-up pattern
test_followup_pattern() {
    local branch="$1"
    [[ "$branch" =~ ^copilot/sub-pr-[0-9]+$ ]]
}

# Find Copilot's announcement comment on the original PR
get_copilot_announcement() {
    local pr_num="$1"
    gh api "repos/${OWNER}/${REPO}/issues/${pr_num}/comments" \
        --jq '.[] | select(.user.login == "app/copilot-swe-agent" and (.body | contains("opened a new pull request"))) | {id: .id, body: .body, created_at: .created_at}' 2>/dev/null || true
}

# Get unified diff for follow-up PR
get_followup_diff() {
    local pr_num="$1"
    gh pr diff "$pr_num" --no-merges 2>/dev/null || true
}

# Compare follow-up diff to determine category
compare_diff_content() {
    local diff="$1"

    if [[ -z "$diff" ]]; then
        echo '{"similarity": 100, "category": "DUPLICATE", "reason": "Follow-up PR contains no changes"}'
        return
    fi

    # Count file changes in follow-up
    local file_count
    file_count=$(echo "$diff" | grep -c '^diff --git' || echo 0)

    if [[ "$file_count" -eq 0 ]]; then
        echo '{"similarity": 95, "category": "DUPLICATE", "reason": "No code changes in follow-up PR"}'
    elif [[ "$file_count" -eq 1 ]]; then
        echo '{"similarity": 85, "category": "LIKELY_DUPLICATE", "reason": "Single file change matching original scope"}'
    else
        echo '{"similarity": 40, "category": "POSSIBLE_SUPPLEMENTAL", "reason": "Multiple file changes suggest additional work"}'
    fi
}

# Determine recommendation based on category
get_recommendation() {
    local category="$1"
    case "$category" in
        DUPLICATE) echo "CLOSE_AS_DUPLICATE" ;;
        LIKELY_DUPLICATE) echo "REVIEW_THEN_CLOSE" ;;
        POSSIBLE_SUPPLEMENTAL) echo "EVALUATE_FOR_MERGE" ;;
        *) echo "MANUAL_REVIEW" ;;
    esac
}

# Main detection logic
main() {
    echo "Detecting Copilot follow-up PRs for PR #${PR_NUMBER}..." >&2

    # Step 1: Query for follow-up PR matching pattern
    local query="head:copilot/sub-pr-${PR_NUMBER}"
    echo "Searching for: $query" >&2

    local follow_up_prs
    follow_up_prs=$(gh pr list --state=open --search "$query" \
        --json number,title,body,headRefName,baseRefName,state,author,createdAt 2>/dev/null || echo "[]")

    local pr_count
    pr_count=$(echo "$follow_up_prs" | jq 'length')

    if [[ "$pr_count" -eq 0 ]]; then
        jq -n '{
            found: false,
            followUpPRs: [],
            announcement: null,
            analysis: null,
            recommendation: "NO_ACTION_NEEDED",
            message: "No follow-up PRs detected"
        }'
        return
    fi

    echo "Found $pr_count follow-up PR(s)" >&2

    # Step 2: Verify Copilot announcement
    local announcement
    announcement=$(get_copilot_announcement "$PR_NUMBER")
    if [[ -z "$announcement" ]]; then
        echo "Warning: No Copilot announcement found, but follow-up PR exists" >&2
    else
        echo "Verified Copilot announcement" >&2
    fi

    # Step 3: Analyze each follow-up PR
    local analysis="[]"
    for row in $(echo "$follow_up_prs" | jq -r '.[] | @base64'); do
        local pr_data
        pr_data=$(echo "$row" | base64 -d)

        local pr_num head_branch base_branch created_at author
        pr_num=$(echo "$pr_data" | jq -r '.number')
        head_branch=$(echo "$pr_data" | jq -r '.headRefName')
        base_branch=$(echo "$pr_data" | jq -r '.baseRefName')
        created_at=$(echo "$pr_data" | jq -r '.createdAt')
        author=$(echo "$pr_data" | jq -r '.author.login')

        echo "Analyzing follow-up PR #${pr_num}..." >&2

        local diff comparison category similarity reason recommendation
        diff=$(get_followup_diff "$pr_num")
        comparison=$(compare_diff_content "$diff")
        category=$(echo "$comparison" | jq -r '.category')
        similarity=$(echo "$comparison" | jq -r '.similarity')
        reason=$(echo "$comparison" | jq -r '.reason')
        recommendation=$(get_recommendation "$category")

        local result
        result=$(jq -n \
            --argjson prNum "$pr_num" \
            --arg headBranch "$head_branch" \
            --arg baseBranch "$base_branch" \
            --arg createdAt "$created_at" \
            --arg author "$author" \
            --arg category "$category" \
            --argjson similarity "$similarity" \
            --arg reason "$reason" \
            --arg recommendation "$recommendation" \
            '{
                followUpPRNumber: $prNum,
                headBranch: $headBranch,
                baseBranch: $baseBranch,
                createdAt: $createdAt,
                author: $author,
                category: $category,
                similarity: $similarity,
                reason: $reason,
                recommendation: $recommendation
            }')

        analysis=$(echo "$analysis" | jq --argjson item "$result" '. + [$item]')
    done

    # Determine final recommendation
    local final_recommendation
    if [[ "$pr_count" -eq 1 ]]; then
        final_recommendation=$(echo "$analysis" | jq -r '.[0].recommendation')
    else
        final_recommendation="MULTIPLE_FOLLOW_UPS_REVIEW"
    fi

    # Build final result
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local announcement_json="null"
    if [[ -n "$announcement" ]]; then
        announcement_json="$announcement"
    fi

    jq -n \
        --argjson found true \
        --argjson originalPRNumber "$PR_NUMBER" \
        --argjson followUpPRs "$follow_up_prs" \
        --argjson announcement "$announcement_json" \
        --argjson analysis "$analysis" \
        --arg recommendation "$final_recommendation" \
        --arg timestamp "$timestamp" \
        '{
            found: $found,
            originalPRNumber: $originalPRNumber,
            followUpPRs: $followUpPRs,
            announcement: $announcement,
            analysis: $analysis,
            recommendation: $recommendation,
            timestamp: $timestamp
        }'
}

main
