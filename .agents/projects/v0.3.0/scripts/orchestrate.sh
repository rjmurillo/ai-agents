#!/bin/bash
# Orchestrator for v0.3.0 Milestone Execution
# Manages up to 6 worktrees with Claude and Copilot CLI agents (default parallelism: 3)
#
# Features:
# - Automatic worktree setup with fallback strategies
# - Dependency tracking between issues (multiple issues can depend on same blocker)
# - Message passing for chain handoffs via inbox/outbox JSON files
# - Resume capability via persistent state file with file locking
# - Agent selection (claude/copilot) - NOTE: copilot mode is experimental
#
# Chain definitions are synced with PLAN.md. Update here if PLAN.md changes.
# Week scheduling is synced with PLAN.md timeline.

set -euo pipefail

# Configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT="$(cd "${PROJECT_DIR}/../../.." && pwd)"

# Project-specific paths (all contained within .agents/projects/v0.3.0/)
readonly STATE_FILE="${PROJECT_DIR}/state/orchestrator.json"
readonly STATE_LOCK="${STATE_FILE}.lock"
readonly LOG_DIR="${PROJECT_DIR}/logs"
readonly INBOX_DIR="${PROJECT_DIR}/messages/inbox"
readonly OUTBOX_DIR="${PROJECT_DIR}/messages/outbox"
# WORKTREE_BASE: Parent of current worktree (where all worktrees live)
# When running from v0.3.0 worktree, REPO_ROOT is the worktree root, so parent is worktrees dir
readonly WORKTREE_BASE="$(cd "${REPO_ROOT}/.." && pwd)"
readonly PLAN_FILE="${REPO_ROOT}/.agents/planning/v0.3.0/PLAN.md"

# Agent configuration
AGENT_CMD="${AGENT_CMD:-claude}"  # claude or copilot
PARALLEL_CHAINS="${PARALLEL_CHAINS:-3}"  # How many chains to run simultaneously (max 6)

# Chain definitions (issue sequences) - See PLAN.md for authoritative source
declare -A CHAINS
CHAINS[1]="997 998 999 1001"
CHAINS[2]="751 734 747 731"
CHAINS[3]="724 721 722 723"
CHAINS[4]="749 778 840"
CHAINS[5]="761 809"
CHAINS[6]="77 90 71 101"

# Chain branches
declare -A CHAIN_BRANCHES
CHAIN_BRANCHES[1]="chain1/memory-enhancement"
CHAIN_BRANCHES[2]="chain2/memory-optimization"
CHAIN_BRANCHES[3]="chain3/traceability"
CHAIN_BRANCHES[4]="chain4/quality-testing"
CHAIN_BRANCHES[5]="chain5/skill-quality"
CHAIN_BRANCHES[6]="chain6/ci-docs"

# Week scheduling - Sync with PLAN.md timeline if schedule changes
declare -A CHAIN_START_WEEK
CHAIN_START_WEEK[1]=1
CHAIN_START_WEEK[2]=1
CHAIN_START_WEEK[3]=1
CHAIN_START_WEEK[4]=3
CHAIN_START_WEEK[5]=3
CHAIN_START_WEEK[6]=5

# Issue dependencies (blockers) - Multiple issues may depend on same blocker and run in parallel once unblocked
declare -A ISSUE_BLOCKED_BY
ISSUE_BLOCKED_BY[998]="997"
ISSUE_BLOCKED_BY[999]="998"
ISSUE_BLOCKED_BY[1001]="999"
ISSUE_BLOCKED_BY[734]="751"
ISSUE_BLOCKED_BY[747]="751"
ISSUE_BLOCKED_BY[731]="734"
ISSUE_BLOCKED_BY[721]="724"
ISSUE_BLOCKED_BY[722]="721"
ISSUE_BLOCKED_BY[723]="722"
ISSUE_BLOCKED_BY[778]="749"
ISSUE_BLOCKED_BY[840]="749"
ISSUE_BLOCKED_BY[809]="761"
ISSUE_BLOCKED_BY[71]="77 90"
ISSUE_BLOCKED_BY[101]="90"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Helper to run a function on all chains. Returns count of failures.
for_each_chain() {
    local func="$1"
    local failures=0
    for chain in {1..6}; do
        if ! "${func}" "${chain}"; then
            failures=$((failures + 1))
        fi
    done
    return ${failures}
}

# Initialize state tracking. Creates directories and state file if missing.
# Safe to call multiple times (idempotent). State file preserves progress across interruptions.
# Returns 1 if any directory or state file creation fails.
init_state() {
    if ! mkdir -p "$(dirname "${STATE_FILE}")"; then
        log_error "Failed to create state directory"
        return 1
    fi
    if ! mkdir -p "${LOG_DIR}"; then
        log_error "Failed to create log directory: ${LOG_DIR}"
        return 1
    fi
    if ! mkdir -p "${INBOX_DIR}"; then
        log_error "Failed to create inbox directory: ${INBOX_DIR}"
        return 1
    fi
    if ! mkdir -p "${OUTBOX_DIR}"; then
        log_error "Failed to create outbox directory: ${OUTBOX_DIR}"
        return 1
    fi
    if ! mkdir -p "${WORKTREE_BASE}"; then
        log_error "Failed to create worktree directory: ${WORKTREE_BASE}"
        return 1
    fi

    if [[ ! -f "${STATE_FILE}" ]]; then
        if ! cat > "${STATE_FILE}" << 'EOF'
{
  "version": "0.3.0",
  "started": null,
  "current_week": 1,
  "chains": {
    "1": {"status": "pending", "current_issue": null, "completed_issues": []},
    "2": {"status": "pending", "current_issue": null, "completed_issues": []},
    "3": {"status": "pending", "current_issue": null, "completed_issues": []},
    "4": {"status": "pending", "current_issue": null, "completed_issues": []},
    "5": {"status": "pending", "current_issue": null, "completed_issues": []},
    "6": {"status": "pending", "current_issue": null, "completed_issues": []}
  },
  "issues": {},
  "messages": []
}
EOF
        then
            log_error "Failed to create state file: ${STATE_FILE}"
            return 1
        fi
        log_info "Created new state file: ${STATE_FILE}"
    fi
}

# Query state file using jq syntax. Returns 1 on failure.
# Example: read_state '.chains."1".status' returns status of chain 1.
read_state() {
    local query="$1"
    local result

    log_info "read_state: Running jq query: ${query}" >&2
    if ! result=$(jq -r "${query}" "${STATE_FILE}" 2>&1); then
        log_error "Failed to read state: ${result}"
        log_error "Query: ${query}"
        return 1
    fi
    log_info "read_state: Result: ${result}" >&2

    echo "${result}"
}

# Update state file atomically with file locking for concurrent access.
# Returns 1 on failure with detailed error message.
update_state() {
    local query="$1"
    local tmp
    local error_output
    local subshell_exit=0

    if ! tmp=$(mktemp 2>&1); then
        log_error "Failed to create temp file for state update: ${tmp}"
        return 1
    fi

    # Use file locking for concurrent access from parallel chains
    # Capture subshell exit code since return inside subshell doesn't propagate
    (
        flock -x 200 || { log_error "Failed to acquire state lock"; rm -f "${tmp}"; exit 1; }

        if ! error_output=$(jq "${query}" "${STATE_FILE}" 2>&1 > "${tmp}"); then
            log_error "jq query failed: ${query}"
            log_error "Error: ${error_output}"
            rm -f "${tmp}"
            exit 1
        fi

        # Validate the output is valid JSON
        if ! jq -e '.' "${tmp}" >/dev/null 2>&1; then
            log_error "jq produced invalid JSON output"
            rm -f "${tmp}"
            exit 1
        fi

        if ! mv "${tmp}" "${STATE_FILE}"; then
            log_error "Failed to write state file: ${STATE_FILE}"
            rm -f "${tmp}"
            exit 1
        fi
    ) 200>"${STATE_LOCK}"
    subshell_exit=$?

    if [[ ${subshell_exit} -ne 0 ]]; then
        return 1
    fi
}

# Critic validation configuration
CRITIC_MODEL="${CRITIC_MODEL:-sonnet}"  # sonnet for speed, opus for thoroughness
MAX_CRITIQUE_ROUNDS=2  # Allow one retry after critique
CRITIQUE_LOG="${PROJECT_DIR}/decisions/critiques.jsonl"

# Verify PR exists and CI checks pass.
# Returns 0 if PR exists with passing checks, 1 otherwise.
verify_pr_and_checks() {
    local chain="$1"
    local issue="$2"
    local dir="${WORKTREE_BASE}/chain${chain}"
    local branch="${CHAIN_BRANCHES[$chain]}"

    log_info "Verifying PR and CI checks for chain ${chain}, issue #${issue}..."

    # Check if PR exists for this branch
    local pr_number
    pr_number=$(cd "${dir}" && gh pr list --head "${branch}" --json number --jq '.[0].number' 2>/dev/null || echo "")

    if [[ -z "${pr_number}" ]]; then
        log_error "No PR found for branch ${branch}"
        log_error "Agent must create a PR before marking issue complete"
        return 1
    fi

    log_info "Found PR #${pr_number} for branch ${branch}"

    # Check CI status
    local check_status
    check_status=$(cd "${dir}" && gh pr checks "${pr_number}" --json state --jq '.[].state' 2>/dev/null || echo "UNKNOWN")

    # Count failures
    local failures
    failures=$(echo "${check_status}" | grep -c "FAILURE\|ERROR" || echo "0")

    if [[ "${failures}" -gt 0 ]]; then
        log_error "PR #${pr_number} has ${failures} failing CI check(s)"
        log_error "CI checks must pass before marking issue complete"

        # Show which checks are failing
        log_info "Failing checks:"
        cd "${dir}" && gh pr checks "${pr_number}" 2>/dev/null | grep -E "fail|error" || true

        return 1
    fi

    # Check if any checks are still pending
    local pending
    pending=$(echo "${check_status}" | grep -c "PENDING\|QUEUED\|IN_PROGRESS" || echo "0")

    if [[ "${pending}" -gt 0 ]]; then
        log_warn "PR #${pr_number} has ${pending} pending CI check(s)"
        log_warn "Waiting for CI to complete..."

        # Wait up to 5 minutes for CI
        local wait_count=0
        local max_wait=30  # 30 * 10s = 5 minutes

        while [[ ${wait_count} -lt ${max_wait} ]]; do
            sleep 10
            wait_count=$((wait_count + 1))

            check_status=$(cd "${dir}" && gh pr checks "${pr_number}" --json state --jq '.[].state' 2>/dev/null || echo "UNKNOWN")
            pending=$(echo "${check_status}" | grep -c "PENDING\|QUEUED\|IN_PROGRESS" || echo "0")
            failures=$(echo "${check_status}" | grep -c "FAILURE\|ERROR" || echo "0")

            if [[ "${failures}" -gt 0 ]]; then
                log_error "CI check(s) failed after waiting"
                return 1
            fi

            if [[ "${pending}" -eq 0 ]]; then
                log_success "All CI checks completed"
                break
            fi

            log_info "Still waiting for CI... (${wait_count}/${max_wait})"
        done

        if [[ "${pending}" -gt 0 ]]; then
            log_error "CI checks still pending after 5 minutes"
            return 1
        fi
    fi

    # Update state with PR number
    update_state ".issues.\"${issue}\".pr = ${pr_number}"
    log_success "PR #${pr_number} verified with passing CI checks"
    return 0
}

# Run critic validation on completed work.
# Returns 0 if approved, 1 if rejected with feedback.
# Outputs critique verdict and feedback via stdout.
run_critic_validation() {
    local chain="$1"
    local issue="$2"
    local dir="${WORKTREE_BASE}/chain${chain}"
    local critique_prompt

    log_info "Running critic validation for chain ${chain}, issue #${issue}..."

    # Get the diff of changes made
    local changes
    changes=$(cd "${dir}" && git diff origin/main --stat 2>/dev/null || echo "No diff available")
    local detailed_diff
    detailed_diff=$(cd "${dir}" && git diff origin/main 2>/dev/null | head -500 || echo "No diff available")

    critique_prompt=$(cat << CRITIQUE_EOF
You are a critic agent validating work completed for issue #${issue}.

## Your Role
Review the implementation for quality, completeness, and correctness.
Be rigorous but fair. The goal is to catch real problems, not nitpick.

## Changes Made
\`\`\`
${changes}
\`\`\`

## Detailed Diff (first 500 lines)
\`\`\`diff
${detailed_diff}
\`\`\`

## Validation Criteria
1. **Completeness**: Does the implementation address the issue requirements?
2. **Quality**: Is the code well-structured, following patterns in the codebase?
3. **Safety**: Are there any security issues, error handling gaps, or breaking changes?
4. **Tests**: If code was added, were tests added or updated?

## Response Format (EXACTLY this format)
VERDICT: [PASS or FAIL]
CONFIDENCE: [HIGH, MEDIUM, or LOW]
SUMMARY: [One sentence summary of assessment]
ISSUES: [If FAIL, list specific issues that must be fixed. If PASS, write "None"]
CRITIQUE_EOF
)

    local critique=""
    local model_flag=""

    case "${CRITIC_MODEL}" in
        opus)
            model_flag="--model claude-opus-4-5-20251101"
            ;;
        sonnet)
            model_flag="--model claude-sonnet-4-20250514"
            ;;
        *)
            model_flag="--model claude-sonnet-4-20250514"
            ;;
    esac

    log_info "Running critic (${CRITIC_MODEL} model)..."
    # Use || true to prevent grep exit code 1 (no matches) from failing the pipeline
    critique=$(claude ${model_flag} --dangerously-skip-permissions -p "${critique_prompt}" 2>/dev/null | grep -E '^(VERDICT|CONFIDENCE|SUMMARY|ISSUES):' | head -4 || true)

    # Log the critique
    log_critique "${chain}" "${issue}" "${critique}"

    # Parse verdict
    local verdict
    verdict=$(echo "${critique}" | grep "^VERDICT:" | cut -d: -f2 | tr -d ' ')

    if [[ "${verdict}" == "PASS" ]]; then
        log_success "Critic validation PASSED for issue #${issue}"
        echo "${critique}"
        return 0
    else
        log_warn "Critic validation FAILED for issue #${issue}"
        echo "${critique}"
        return 1
    fi
}

# Log critique for audit trail
log_critique() {
    local chain="$1"
    local issue="$2"
    local critique="$3"
    local timestamp
    timestamp=$(date -Iseconds)

    mkdir -p "$(dirname "${CRITIQUE_LOG}")"

    jq -n \
        --arg ts "${timestamp}" \
        --argjson chain "${chain}" \
        --argjson issue "${issue}" \
        --arg critique "${critique}" \
        --arg model "${CRITIC_MODEL}" \
        '{timestamp: $ts, chain: $chain, issue: $issue, critique: $critique, model: $model}' \
        >> "${CRITIQUE_LOG}"

    log_info "Critique logged: Chain ${chain}, Issue #${issue}"
}

# Verify that actual work was done in the worktree.
# Returns 0 if work detected, 1 if no work detected.
# Checks: new commits, uncommitted changes, or new files.
verify_work_done() {
    local chain="$1"
    local issue="$2"
    local dir="${WORKTREE_BASE}/chain${chain}"
    local branch="${CHAIN_BRANCHES[$chain]}"

    log_info "Verifying work was done for chain ${chain}, issue #${issue}..."

    # Check 1: Are there new commits on this branch vs origin/main?
    local new_commits
    new_commits=$(cd "${dir}" && git log origin/main..HEAD --oneline 2>/dev/null | wc -l)
    if [[ "${new_commits}" -gt 0 ]]; then
        log_info "Found ${new_commits} new commit(s)"
        return 0
    fi

    # Check 2: Are there uncommitted changes?
    if (cd "${dir}" && git status --porcelain | grep -q .); then
        log_info "Found uncommitted changes"
        return 0
    fi

    # Check 3: Were any files modified in the working tree?
    local modified_files
    modified_files=$(cd "${dir}" && git diff --name-only HEAD 2>/dev/null | wc -l)
    if [[ "${modified_files}" -gt 0 ]]; then
        log_info "Found ${modified_files} modified file(s)"
        return 0
    fi

    log_warn "NO WORK DETECTED for issue #${issue} - agent may have stalled"
    return 1
}

# State update helpers for common operations
mark_issue_started() {
    local chain="$1" issue="$2"
    local now
    now=$(date -Iseconds)
    update_state ".chains.\"${chain}\".status = \"running\" | .chains.\"${chain}\".current_issue = ${issue} | .issues.\"${issue}\".status = \"in_progress\" | .issues.\"${issue}\".started = \"${now}\""
}

mark_issue_completed() {
    local chain="$1" issue="$2"
    local now
    now=$(date -Iseconds)
    update_state ".issues.\"${issue}\".status = \"completed\" | .issues.\"${issue}\".completed = \"${now}\" | .chains.\"${chain}\".completed_issues += [${issue}]"
}

mark_issue_failed() {
    local issue="$1" exit_code="$2"
    update_state ".issues.\"${issue}\".status = \"failed\" | .issues.\"${issue}\".error = \"Exit code ${exit_code}\""
}

# Check if issue dependencies are satisfied.
# Returns 0 if all blockers completed or no blockers exist.
# Returns 1 if any blocker is pending or in progress.
# Returns 2 if state read failed (distinct error code).
check_dependencies() {
    local issue="$1"
    local blockers="${ISSUE_BLOCKED_BY[$issue]:-}"

    if [[ -z "${blockers}" ]]; then
        return 0
    fi

    for blocker in ${blockers}; do
        local status
        if ! status=$(read_state ".issues.\"${blocker}\".status // \"pending\""); then
            log_error "Failed to check dependency status for blocker #${blocker}"
            return 2
        fi
        if [[ "${status}" != "completed" ]]; then
            return 1
        fi
    done
    return 0
}

# Setup worktree for a chain with detailed error reporting.
# Tries: 1) Create new branch, 2) Use existing branch, 3) Force-create from origin/main.
setup_worktree() {
    local chain="$1"
    local branch="${CHAIN_BRANCHES[$chain]}"
    local dir="${WORKTREE_BASE}/chain${chain}"

    if [[ -d "${dir}" ]]; then
        log_info "Worktree for chain ${chain} already exists at ${dir}"
        return 0
    fi

    log_info "Creating worktree for chain ${chain}: ${dir} (branch: ${branch})"

    local error_output

    # Attempt 1: Create new branch
    if error_output=$(cd "${REPO_ROOT}" && git worktree add "${dir}" -b "${branch}" 2>&1); then
        log_success "Created worktree for chain ${chain} (new branch)"
        return 0
    fi
    log_warn "Attempt 1 (new branch) failed: ${error_output}"

    # Attempt 2: Use existing branch
    if error_output=$(cd "${REPO_ROOT}" && git worktree add "${dir}" "${branch}" 2>&1); then
        log_success "Created worktree for chain ${chain} (existing branch)"
        return 0
    fi
    log_warn "Attempt 2 (existing branch) failed: ${error_output}"

    # Attempt 3: Force recreate from origin/main
    if error_output=$(cd "${REPO_ROOT}" && git worktree add "${dir}" -B "${branch}" origin/main 2>&1); then
        log_success "Created worktree for chain ${chain} (reset from origin/main)"
        return 0
    fi

    log_error "All worktree creation attempts failed for chain ${chain}"
    log_error "Last error: ${error_output}"
    log_error "Manual fix: Check git status, clean up stale worktrees with 'git worktree prune'"
    return 1
}

# Sync chain branch after issue completion.
# Ensures commits from previous issues are available to subsequent issues.
# Called after each issue completes successfully.
sync_chain_branch() {
    local chain="$1"
    local issue="$2"
    local dir="${WORKTREE_BASE}/chain${chain}"
    local branch="${CHAIN_BRANCHES[$chain]}"

    log_info "Syncing chain ${chain} branch after issue #${issue}..."

    # Check for uncommitted changes and commit them
    if (cd "${dir}" && git status --porcelain | grep -q .); then
        log_info "Found uncommitted changes, committing..."
        (cd "${dir}" && git add -A && git commit -m "chore(chain${chain}): auto-commit for issue #${issue}

Orchestrator auto-commit to preserve work between issues.

Co-Authored-By: Orchestrator <noreply@orchestrator.local>") || {
            log_warn "Auto-commit failed, changes may be lost"
        }
    fi

    # Push to remote
    log_info "Pushing ${branch} to origin..."
    if ! (cd "${dir}" && git push -u origin "${branch}" 2>&1); then
        log_warn "Push failed for chain ${chain}, subsequent issues may not see this work"
        return 1
    fi

    log_success "Chain ${chain} branch synced after issue #${issue}"
    return 0
}

# Pull latest changes before starting an issue.
# Ensures work from previous issues in the chain is available.
pull_chain_branch() {
    local chain="$1"
    local dir="${WORKTREE_BASE}/chain${chain}"
    local branch="${CHAIN_BRANCHES[$chain]}"

    log_info "Pulling latest for chain ${chain} branch..."

    # Fetch and pull
    if ! (cd "${dir}" && git fetch origin && git pull origin "${branch}" --rebase 2>&1); then
        log_warn "Pull failed for chain ${chain}, may be working with stale code"
        # Don't fail - the branch might be new
    fi

    return 0
}

# Remove worktree for a chain. Logs warnings on failure but allows continuation.
cleanup_worktree() {
    local chain="$1"
    local dir="${WORKTREE_BASE}/chain${chain}"

    if [[ -d "${dir}" ]]; then
        log_info "Removing worktree for chain ${chain}"
        local error_output
        if ! error_output=$(cd "${REPO_ROOT}" && git worktree remove "${dir}" --force 2>&1); then
            log_warn "Worktree removal failed for chain ${chain}: ${error_output}"
            log_warn "Manual cleanup may be needed: rm -rf '${dir}' && git worktree prune"
            return 1
        fi
        log_success "Worktree removed for chain ${chain}"
    fi
}

# Send message to a chain's inbox using jq for safe JSON construction.
send_message() {
    local from_chain="$1"
    local to_chain="$2"
    local subject="$3"
    local body="$4"
    local timestamp
    timestamp=$(date -Iseconds)
    local msg_file="${INBOX_DIR}/chain${to_chain}-$(date +%Y%m%d-%H%M%S)-from-chain${from_chain}.json"

    if ! jq -n \
        --argjson from "${from_chain}" \
        --argjson to "${to_chain}" \
        --arg subject "${subject}" \
        --arg body "${body}" \
        --arg timestamp "${timestamp}" \
        '{from_chain: $from, to_chain: $to, subject: $subject, body: $body, timestamp: $timestamp, read: false}' \
        > "${msg_file}"; then
        log_error "Failed to write message to ${msg_file}"
        return 1
    fi

    if ! cp "${msg_file}" "${OUTBOX_DIR}/"; then
        log_warn "Failed to copy message to outbox (non-fatal)"
    fi
    log_info "Message sent: chain ${from_chain} -> chain ${to_chain}: ${subject}"
}

# Read unread messages for a chain. Logs warnings on parse errors but continues.
read_messages() {
    local chain="$1"
    local messages=""

    for msg_file in "${INBOX_DIR}"/chain"${chain}"-*.json; do
        [[ -f "${msg_file}" ]] || continue
        local read_status
        if ! read_status=$(jq -r '.read' "${msg_file}" 2>&1); then
            log_warn "Failed to read message file ${msg_file}: ${read_status}"
            continue
        fi
        if [[ "${read_status}" == "false" ]]; then
            local subject body
            if ! subject=$(jq -r '.subject' "${msg_file}" 2>&1); then
                log_warn "Failed to parse subject from ${msg_file}: ${subject}"
                continue
            fi
            if ! body=$(jq -r '.body' "${msg_file}" 2>&1); then
                log_warn "Failed to parse body from ${msg_file}: ${body}"
                continue
            fi
            messages="${messages}\n- ${subject}: ${body}"
            # Mark as read
            if ! jq '.read = true' "${msg_file}" > "${msg_file}.tmp"; then
                log_warn "Failed to mark message as read: ${msg_file}"
                continue
            fi
            if ! mv "${msg_file}.tmp" "${msg_file}"; then
                log_warn "Failed to update message file ${msg_file}, message may be re-read"
                rm -f "${msg_file}.tmp"
            fi
        fi
    done

    echo -e "${messages}"
}

# Decision maker configuration
DECISION_MODEL="${DECISION_MODEL:-opus}"  # opus or gpt
DECISION_LOG="${PROJECT_DIR}/decisions/decisions.jsonl"
MAX_DECISION_ROUNDS=3  # Prevent infinite loops

# Detect if agent output contains a question requiring a decision
# Returns 0 if question detected, 1 otherwise
detect_question() {
    local log_file="$1"
    local last_lines
    last_lines=$(tail -50 "${log_file}" 2>/dev/null || echo "")

    # Patterns that indicate agent is asking for input
    if echo "${last_lines}" | grep -qiE '(which (option|approach)|how would you like|would you prefer|should I|do you want|please (choose|select|confirm)|option [A-Z]:|waiting for|need.*clarification|\?$)'; then
        return 0
    fi
    return 1
}

# Get autonomous decision using orchestrator agent pattern
# Args: chain, issue, question_context
# Returns: decision text via stdout
get_decision() {
    local chain="$1"
    local issue="$2"
    local context="$3"
    local decision_prompt

    # Use orchestrator agent pattern - it has workflow to handle ambiguity
    decision_prompt=$(cat << DECISION_EOF
You are the orchestrator agent making an autonomous decision for v0.3.0 milestone execution.

## Situation
An implementer agent working on issue #${issue} (chain ${chain}) encountered ambiguity and needs guidance to continue.

## Agent's Question/Context
${context}

## Decision Framework
Apply the orchestrator workflow:
1. Analyze dependencies - what blocks what?
2. Apply YAGNI - what's the minimum to unblock progress?
3. Consider chain ownership - this chain owns its issues sequentially
4. Prefer implementation over waiting - momentum matters

## Constraints
- Do NOT ask follow-up questions
- Do NOT suggest waiting for human input
- Make a decisive choice NOW
- The system must not stall

## Response Format (EXACTLY this format)
DECISION: [Your choice - e.g., "Option C" or clear directive]
RATIONALE: [One sentence why]
NEXT_ACTION: [What the agent should do immediately]
DECISION_EOF
)

    local decision=""
    local model_flag=""

    case "${DECISION_MODEL}" in
        opus)
            model_flag="--model claude-opus-4-5-20251101"
            ;;
        sonnet)
            model_flag="--model claude-sonnet-4-20250514"
            ;;
        *)
            model_flag="--model claude-opus-4-5-20251101"
            ;;
    esac

    log_info "Escalating decision to ${DECISION_MODEL} model..."
    # Use || true to prevent grep exit code 1 (no matches) from failing the pipeline
    decision=$(claude ${model_flag} --dangerously-skip-permissions -p "${decision_prompt}" 2>/dev/null | grep -E '^(DECISION|RATIONALE|NEXT_ACTION):' | head -3 || true)

    # Fallback if decision is empty or malformed
    if [[ -z "${decision}" ]] || ! echo "${decision}" | grep -q "^DECISION:"; then
        decision="DECISION: Option A - Proceed with first available option
RATIONALE: Decision service returned incomplete response, defaulting to forward progress
NEXT_ACTION: Implement the first option and iterate"
    fi

    echo "${decision}"
}

# Log decision for audit trail
log_decision() {
    local chain="$1"
    local issue="$2"
    local question="$3"
    local decision="$4"
    local timestamp
    timestamp=$(date -Iseconds)

    mkdir -p "$(dirname "${DECISION_LOG}")"

    jq -n \
        --arg ts "${timestamp}" \
        --argjson chain "${chain}" \
        --argjson issue "${issue}" \
        --arg question "${question}" \
        --arg decision "${decision}" \
        --arg model "${DECISION_MODEL}" \
        '{timestamp: $ts, chain: $chain, issue: $issue, question: $question, decision: $decision, model: $model}' \
        >> "${DECISION_LOG}"

    log_info "Decision logged: Chain ${chain}, Issue #${issue}"
}

# Generate agent prompt for an issue
generate_prompt() {
    local chain="$1"
    local issue="$2"
    local messages
    messages=$(read_messages "${chain}")

    cat << EOF
You are working on v0.3.0 milestone, chain ${chain}, issue #${issue}.

## Context
- Branch: ${CHAIN_BRANCHES[$chain]}
- Plan file: ${PLAN_FILE}
- Read the Implementation Card for #${issue} in the plan file

## Instructions
1. Run /session-init to start your session
2. Assign yourself to issue #${issue}
3. Read the issue and its Traycer plan (if available)
4. Implement the solution following the Haiku-Ready steps if provided
5. Run the verification commands in the Implementation Card
6. Create atomic commits with conventional messages
7. When done, push your branch and create a PR

## CRITICAL: Autonomous Execution (MUST FOLLOW)
You are running non-interactively. There is NO human to answer questions.

**NEVER**:
- Wait for permission approvals (you have --dangerously-skip-permissions)
- Ask "how would you like to proceed?" or similar questions
- Wait for clarification - make the best choice and document it
- Stall on missing dependencies - implement stubs if needed

**ALWAYS**:
- Make autonomous decisions immediately
- Create files, edit code, run commands without asking
- If previous phase code is missing, implement it yourself or create minimal stubs
- Document your decisions in commit messages
- Complete your assigned issue, don't stop halfway

The orchestrator will escalate to a decision-maker ONLY if absolutely necessary.
Prefer forward progress over perfect information.

## Messages from Other Chains
${messages:-"No messages from other chains."}

## Exit Criteria
Complete when ALL verification commands in the Implementation Card exit with code 0.
EOF
}

# Run agent on a specific issue with automatic decision escalation.
# If agent asks a question, escalates to decision-maker and re-runs with answer.
# Side effects: Updates state file, logs to LOG_DIR, sends completion messages.
run_agent() {
    local chain="$1"
    local issue="$2"
    local dir="${WORKTREE_BASE}/chain${chain}"
    local branch="${CHAIN_BRANCHES[$chain]}"
    local log_file="${LOG_DIR}/chain${chain}-issue${issue}-$(date +%Y%m%d-%H%M%S).log"
    local base_prompt
    base_prompt=$(generate_prompt "${chain}" "${issue}")

    log_info "run_agent: Starting ${AGENT_CMD} for chain ${chain}, issue #${issue}"
    log_info "run_agent: Working directory: ${dir}"
    log_info "run_agent: Log file: ${log_file}"

    # Pull latest chain branch to get work from previous issues
    pull_chain_branch "${chain}"

    if ! mark_issue_started "${chain}" "${issue}"; then
        log_error "Failed to mark issue #${issue} as started"
        return 1
    fi

    local exit_code=0
    local decision_round=0
    local prompt="${base_prompt}"
    local accumulated_decisions=""

    # Decision loop - runs agent, checks for questions, escalates if needed
    while [[ ${decision_round} -lt ${MAX_DECISION_ROUNDS} ]]; do
        log_info "run_agent: Round $((decision_round + 1))/${MAX_DECISION_ROUNDS}"

        # Run agent
        log_info "run_agent: Executing ${AGENT_CMD} command..."
        case "${AGENT_CMD}" in
            claude)
                log_info "run_agent: Running claude in ${dir}"
                (cd "${dir}" && claude --dangerously-skip-permissions -p "${prompt}" 2>&1 | tee -a "${log_file}") || exit_code=$?
                log_info "run_agent: claude exited with code ${exit_code}"
                ;;
            copilot)
                (cd "${dir}" && gh copilot suggest --yolo "${prompt}" 2>&1 | tee -a "${log_file}") || exit_code=$?
                ;;
            *)
                log_error "Unknown agent: ${AGENT_CMD}"
                return 1
                ;;
        esac

        # Check if agent asked a question
        if detect_question "${log_file}"; then
            decision_round=$((decision_round + 1))
            log_warn "Agent asked a question (round ${decision_round}/${MAX_DECISION_ROUNDS}), escalating to decision-maker..."

            # Extract question context (last 100 lines of log)
            local question_context
            question_context=$(tail -100 "${log_file}" 2>/dev/null || echo "No context available")

            # Get decision from higher model
            local decision
            decision=$(get_decision "${chain}" "${issue}" "${question_context}")

            # Log the decision
            log_decision "${chain}" "${issue}" "${question_context}" "${decision}"

            log_info "Decision received:"
            echo "${decision}" | while read -r line; do log_info "  ${line}"; done

            # Append decision to prompt and continue
            accumulated_decisions="${accumulated_decisions}

## Decision from Orchestrator (Round ${decision_round})
${decision}

Continue implementing based on this decision. Do NOT ask further questions - make autonomous choices."

            prompt="${base_prompt}${accumulated_decisions}"

            # Add separator to log file
            echo "" >> "${log_file}"
            echo "=== DECISION ESCALATION (Round ${decision_round}) ===" >> "${log_file}"
            echo "${decision}" >> "${log_file}"
            echo "=== CONTINUING WITH DECISION ===" >> "${log_file}"
            echo "" >> "${log_file}"
        else
            # No question detected, agent completed its work
            log_info "run_agent: No question detected, agent work complete"
            break
        fi
    done

    if [[ ${decision_round} -ge ${MAX_DECISION_ROUNDS} ]]; then
        log_error "Max decision rounds (${MAX_DECISION_ROUNDS}) reached for issue #${issue}"
        exit_code=1
    fi

    # Handle completion or failure
    if [[ ${exit_code} -eq 0 ]]; then
        # CRITICAL: Verify actual work was done before marking complete
        local work_verified=0
        verify_work_done "${chain}" "${issue}" || work_verified=$?

        if [[ ${work_verified} -ne 0 ]]; then
            log_error "Issue #${issue} exited cleanly but NO WORK WAS DETECTED"
            log_error "Agent may have stalled, asked questions, or encountered silent failure"
            log_error "NOT marking issue as complete - requires investigation"
            update_state ".issues.\"${issue}\".status = \"stalled\" | .issues.\"${issue}\".error = \"No work detected - agent may have stalled\""
            return 1
        fi

        # FEEDBACK LOOP: Run critic validation with retry
        local critique_round=0
        local critique_passed=false
        local critique_feedback=""

        while [[ ${critique_round} -lt ${MAX_CRITIQUE_ROUNDS} ]]; do
            critique_round=$((critique_round + 1))
            log_info "Critic validation round ${critique_round}/${MAX_CRITIQUE_ROUNDS}..."

            local critic_result=0
            critique_feedback=$(run_critic_validation "${chain}" "${issue}") || critic_result=$?

            if [[ ${critic_result} -eq 0 ]]; then
                critique_passed=true
                break
            fi

            # Critic rejected - if we have retries left, send feedback to agent
            if [[ ${critique_round} -lt ${MAX_CRITIQUE_ROUNDS} ]]; then
                log_warn "Critic rejected work, running remediation round..."

                local remediation_prompt="${base_prompt}

## CRITIC FEEDBACK - MUST ADDRESS
The critic agent reviewed your implementation and found issues:

${critique_feedback}

## Instructions
1. Address ALL issues listed above
2. Make the necessary fixes
3. Commit your changes
4. Do NOT ask questions - fix the issues directly"

                # Run agent again to fix issues
                log_info "Running remediation agent..."
                case "${AGENT_CMD}" in
                    claude)
                        (cd "${dir}" && claude --dangerously-skip-permissions -p "${remediation_prompt}" 2>&1 | tee -a "${log_file}") || log_warn "Critic remediation agent failed"
                        ;;
                    copilot)
                        (cd "${dir}" && gh copilot suggest --yolo "${remediation_prompt}" 2>&1 | tee -a "${log_file}") || log_warn "Critic remediation agent failed"
                        ;;
                esac

                # Log remediation attempt
                echo "" >> "${log_file}"
                echo "=== CRITIC REMEDIATION (Round ${critique_round}) ===" >> "${log_file}"
                echo "${critique_feedback}" >> "${log_file}"
                echo "=== REMEDIATION COMPLETE ===" >> "${log_file}"
            fi
        done

        if [[ "${critique_passed}" != "true" ]]; then
            log_error "Issue #${issue} failed critic validation after ${MAX_CRITIQUE_ROUNDS} rounds"
            log_error "Marking as needs_review for manual inspection"
            update_state ".issues.\"${issue}\".status = \"needs_review\" | .issues.\"${issue}\".error = \"Failed critic validation\" | .issues.\"${issue}\".critique = \"${critique_feedback}\""
            return 1
        fi

        log_success "Issue #${issue} passed critic validation (round ${critique_round})"

        # FINAL GATE: Verify PR exists and CI checks pass
        local pr_verified=0
        verify_pr_and_checks "${chain}" "${issue}" || pr_verified=$?

        if [[ ${pr_verified} -ne 0 ]]; then
            log_error "Issue #${issue} failed PR/CI verification"

            # Check if PR exists (with proper error handling)
            local pr_check_result=""
            local pr_check_exit=0
            pr_check_result=$(cd "${dir}" && gh pr list --head "${branch}" --json number --jq '.[0].number' 2>&1) || pr_check_exit=$?

            # If gh command failed (not just empty result), log and continue to CI fix
            if [[ ${pr_check_exit} -ne 0 ]]; then
                log_warn "PR check failed: ${pr_check_result}"
            fi

            # If no PR (empty result and command succeeded), run agent to create one
            if [[ ${pr_check_exit} -eq 0 && -z "${pr_check_result}" ]]; then
                log_info "Running agent to create PR..."
                local pr_prompt="${base_prompt}

## MISSING PR - MUST CREATE
Your implementation is ready but you did not create a Pull Request.

## Instructions
1. Push your branch if not already pushed
2. Create a PR with: gh pr create --title 'fix(chain${chain}): implement issue #${issue}' --body '...'
3. Wait for CI to start
4. Do NOT ask questions - just create the PR"

                case "${AGENT_CMD}" in
                    claude)
                        (cd "${dir}" && claude --dangerously-skip-permissions -p "${pr_prompt}" 2>&1 | tee -a "${log_file}") || log_warn "PR creation agent failed"
                        ;;
                    copilot)
                        (cd "${dir}" && gh copilot suggest --yolo "${pr_prompt}" 2>&1 | tee -a "${log_file}") || log_warn "PR creation agent failed"
                        ;;
                esac

                # Retry PR verification
                verify_pr_and_checks "${chain}" "${issue}" || pr_verified=$?
            fi

            # If CI is failing, run agent to fix
            if [[ ${pr_verified} -ne 0 ]]; then
                log_info "Running agent to fix CI failures..."
                local ci_fix_prompt="${base_prompt}

## CI CHECKS FAILING - MUST FIX
Your PR has failing CI checks. You must fix them before the issue can be marked complete.

## Instructions
1. Run: gh pr checks
2. Identify the failing checks
3. Fix the issues in your code
4. Commit and push the fixes
5. Do NOT ask questions - fix the CI failures"

                case "${AGENT_CMD}" in
                    claude)
                        (cd "${dir}" && claude --dangerously-skip-permissions -p "${ci_fix_prompt}" 2>&1 | tee -a "${log_file}") || log_warn "CI fix agent failed"
                        ;;
                    copilot)
                        (cd "${dir}" && gh copilot suggest --yolo "${ci_fix_prompt}" 2>&1 | tee -a "${log_file}") || log_warn "CI fix agent failed"
                        ;;
                esac

                # Final retry
                verify_pr_and_checks "${chain}" "${issue}" || pr_verified=$?
            fi
        fi

        if [[ ${pr_verified} -ne 0 ]]; then
            log_error "Issue #${issue} could not pass PR/CI verification after remediation"
            update_state ".issues.\"${issue}\".status = \"ci_failed\" | .issues.\"${issue}\".error = \"PR or CI checks failed\""
            return 1
        fi

        if ! mark_issue_completed "${chain}" "${issue}"; then
            log_error "CRITICAL: Issue #${issue} completed but state update failed!"
            log_error "Manual fix needed: Update ${STATE_FILE} to mark issue ${issue} complete"
            return 1
        fi
        log_success "Issue #${issue} completed (${decision_round} decision rounds, ${critique_round} critique rounds)"

        # Sync branch so subsequent issues in this chain can access the code
        sync_chain_branch "${chain}" "${issue}"

        if ! send_completion_message "${chain}" "${issue}"; then
            log_warn "Some completion notifications failed, dependent chains will discover via polling"
        fi
    else
        if ! mark_issue_failed "${issue}" "${exit_code}"; then
            log_error "Failed to record failure state for issue #${issue}"
        fi
        log_error "Issue #${issue} failed with exit code ${exit_code}"
    fi

    return ${exit_code}
}

# Send message when an issue completes (for dependency notification).
# Uses space-delimited matching to avoid partial matches (e.g., "1" matching "1001").
send_completion_message() {
    local from_chain="$1"
    local issue="$2"
    local send_failures=0

    for dep_issue in "${!ISSUE_BLOCKED_BY[@]}"; do
        # Use space-delimited matching to avoid partial matches (e.g., "1" matching "1001")
        if [[ " ${ISSUE_BLOCKED_BY[$dep_issue]} " =~ [[:space:]]${issue}[[:space:]] ]]; then
            for chain_num in "${!CHAINS[@]}"; do
                # Same space-delimited check for chain membership
                if [[ " ${CHAINS[$chain_num]} " =~ [[:space:]]${dep_issue}[[:space:]] ]]; then
                    if ! send_message "${from_chain}" "${chain_num}" \
                        "Dependency #${issue} completed" \
                        "Issue #${issue} is done. You can now start #${dep_issue}."; then
                        send_failures=$((send_failures + 1))
                    fi
                fi
            done
        fi
    done

    if [[ ${send_failures} -gt 0 ]]; then
        log_warn "Failed to send ${send_failures} completion notification(s)"
        return 1
    fi
}

# Get next issue to work on for a chain
get_next_issue() {
    local chain="$1"
    local issues
    read -ra issues <<< "${CHAINS[$chain]}"
    local completed

    if ! completed=$(read_state ".chains.\"${chain}\".completed_issues | .[]?" | tr '\n' ' '); then
        log_error "Failed to read completion state for chain ${chain}"
        return 1
    fi

    for issue in "${issues[@]}"; do
        # Use space-delimited matching to avoid partial matches (e.g., "1" matching "1001")
        if [[ " ${completed} " =~ [[:space:]]${issue}[[:space:]] ]]; then
            continue
        fi

        local dep_result=0
        check_dependencies "${issue}" || dep_result=$?
        if [[ ${dep_result} -eq 2 ]]; then
            log_error "Cannot determine dependency status for issue #${issue}, skipping"
            continue
        elif [[ ${dep_result} -eq 0 ]]; then
            echo "${issue}"
            return 0
        fi
    done

    echo ""
}

# Check if chain is complete.
# Returns 0 if complete, 1 if incomplete, 2 on state read error.
is_chain_complete() {
    local chain="$1"
    log_info "is_chain_complete: Checking chain ${chain}"
    local issues
    read -ra issues <<< "${CHAINS[$chain]}"
    log_info "is_chain_complete: Chain ${chain} has ${#issues[@]} issues"
    local completed_count

    log_info "is_chain_complete: Reading state for chain ${chain}..."
    if ! completed_count=$(read_state ".chains.\"${chain}\".completed_issues | length"); then
        log_error "Failed to read completion count for chain ${chain}"
        return 2
    fi
    log_info "is_chain_complete: Chain ${chain} has ${completed_count} completed"

    [[ "${completed_count}" -eq "${#issues[@]}" ]]
}

# Run orchestration loop for a single chain. Blocks until all chain issues complete.
# Waits 30s when blocked by dependencies, 5s between issues.
# Exits with error if state cannot be read (prevents infinite loop).
run_chain() {
    local chain="$1"

    log_info "run_chain: Starting chain ${chain}"

    if ! setup_worktree "${chain}"; then
        log_error "Failed to setup worktree for chain ${chain}"
        return 1
    fi

    log_info "run_chain: Worktree ready for chain ${chain}, entering main loop"

    local chain_complete_result
    while true; do
        chain_complete_result=0
        is_chain_complete "${chain}" || chain_complete_result=$?
        if [[ ${chain_complete_result} -eq 0 ]]; then
            break  # Chain is complete
        elif [[ ${chain_complete_result} -eq 2 ]]; then
            log_error "Cannot determine chain ${chain} completion status, aborting"
            return 1
        fi
        # chain_complete_result == 1 means chain is not complete, continue

        local next_issue
        local get_issue_result
        next_issue=$(get_next_issue "${chain}")
        get_issue_result=$?
        log_info "run_chain: get_next_issue returned '${next_issue}' (exit: ${get_issue_result})"

        if [[ ${get_issue_result} -ne 0 ]]; then
            log_error "Failed to get next issue for chain ${chain}, aborting"
            return 1
        fi

        if [[ -z "${next_issue}" ]]; then
            log_warn "Chain ${chain}: Waiting for dependencies..."
            sleep 30
            continue
        fi

        log_info "run_chain: Will work on issue #${next_issue}"

        if ! run_agent "${chain}" "${next_issue}"; then
            log_error "Agent failed for chain ${chain} issue #${next_issue}"
            # Continue to next issue - failed issues are tracked in state
        fi

        sleep 5
    done

    if ! update_state ".chains.\"${chain}\".status = \"completed\""; then
        log_error "Failed to mark chain ${chain} as completed"
        return 1
    fi
    log_success "Chain ${chain} completed!"
}

# Main orchestration. Runs chains in parallel (up to PARALLEL_CHAINS).
# Uses process polling with 5s intervals to detect completion and start queued chains.
orchestrate() {
    local week="${1:-1}"

    log_info "Starting v0.3.0 orchestration (week ${week})"
    if ! update_state ".started = \"$(date -Iseconds)\" | .current_week = ${week}"; then
        log_error "Failed to update orchestration start state, aborting"
        return 1
    fi

    local chains_to_run=()
    for chain_num in "${!CHAIN_START_WEEK[@]}"; do
        if [[ "${CHAIN_START_WEEK[$chain_num]}" -le "${week}" ]]; then
            chains_to_run+=("${chain_num}")
        fi
    done

    log_info "Chains for week ${week}: ${chains_to_run[*]}"

    if [[ ${#chains_to_run[@]} -eq 0 ]]; then
        log_warn "No chains to run for week ${week}"
        return 0
    fi

    # Track chain-to-PID mapping for error reporting
    declare -A chain_pids
    local pids=()
    local running=0

    for chain in "${chains_to_run[@]}"; do
        log_info "Evaluating chain ${chain}..."
        local complete_result=0
        is_chain_complete "${chain}" || complete_result=$?
        log_info "Chain ${chain} completion check returned: ${complete_result}"
        if [[ ${complete_result} -eq 0 ]]; then
            log_info "Chain ${chain} already complete, skipping"
            continue
        elif [[ ${complete_result} -eq 2 ]]; then
            log_error "Cannot check chain ${chain} completion status, skipping"
            continue
        fi
        log_info "Chain ${chain} is not complete, will start"

        # Wait if at parallel limit, removing completed PIDs
        while [[ ${running} -ge ${PARALLEL_CHAINS} ]]; do
            local new_pids=()
            for pid in "${pids[@]}"; do
                # Skip invalid PIDs (empty or non-numeric)
                [[ -n "${pid}" && "${pid}" =~ ^[0-9]+$ ]] || continue
                # Check if process is still running. kill -0 returns 0 if process exists.
                if kill -0 "${pid}" 2>/dev/null; then
                    new_pids+=("${pid}")
                else
                    running=$((running - 1))
                fi
            done
            # Handle empty array case explicitly to avoid bash errors
            if [[ ${#new_pids[@]} -gt 0 ]]; then
                pids=("${new_pids[@]}")
            else
                pids=()
            fi
            sleep 5
        done

        run_chain "${chain}" &
        local pid=$!
        chain_pids[${chain}]=${pid}
        pids+=("${pid}")
        running=$((running + 1))
        log_info "Started chain ${chain} (PID: ${pid})"
    done

    log_info "Started ${#chain_pids[@]} chain(s), waiting for completion..."

    if [[ ${#chain_pids[@]} -eq 0 ]]; then
        log_warn "No chains were started"
        return 0
    fi

    # Wait with proper error tracking
    local failed_chains=()
    for chain in "${!chain_pids[@]}"; do
        local pid="${chain_pids[$chain]}"
        if ! wait "${pid}"; then
            log_error "Chain ${chain} (PID ${pid}) failed"
            failed_chains+=("${chain}")
        else
            log_success "Chain ${chain} completed successfully"
        fi
    done

    if [[ ${#failed_chains[@]} -gt 0 ]]; then
        log_error "Failed chains: ${failed_chains[*]}"
        log_error "Check logs in ${LOG_DIR} for details"
        return 1
    fi

    log_success "Week ${week} orchestration complete!"
}

# Resume from saved state
resume() {
    local week
    if ! week=$(read_state ".current_week"); then
        log_error "Failed to read current week from state"
        return 1
    fi
    log_info "Resuming from week ${week}"
    orchestrate "${week}"
}

# Show current status. Gracefully handles state read failures.
show_status() {
    echo "=== v0.3.0 Orchestration Status ==="
    echo "Project dir: ${PROJECT_DIR}"
    echo ""

    for chain in {1..6}; do
        local status current completed total
        if ! status=$(read_state ".chains.\"${chain}\".status"); then
            status="unknown"
        fi
        if ! current=$(read_state ".chains.\"${chain}\".current_issue // \"none\""); then
            current="unknown"
        fi
        if ! completed=$(read_state ".chains.\"${chain}\".completed_issues | length"); then
            completed="?"
        fi
        # Use bash array for word count to avoid wc output format issues
        if [[ -z "${CHAINS[$chain]:-}" ]]; then
            log_error "No chain definition for chain ${chain}"
            total="?"
        else
            local -a issues_arr
            read -ra issues_arr <<< "${CHAINS[$chain]}"
            total=${#issues_arr[@]}
        fi

        local color="${NC}"
        case "${status}" in
            completed) color="${GREEN}" ;;
            running) color="${BLUE}" ;;
            pending) color="${YELLOW}" ;;
            unknown) color="${RED}" ;;
            *) color="${RED}" ;;
        esac

        echo -e "Chain ${chain}: ${color}${status}${NC} (${completed}/${total}) - Current: #${current}"
        echo "  Issues: ${CHAINS[$chain]}"
        echo "  Branch: ${CHAIN_BRANCHES[$chain]}"
        echo ""
    done

    local inbox_count
    if [[ ! -d "${INBOX_DIR}" ]]; then
        log_warn "Inbox directory does not exist: ${INBOX_DIR}"
        inbox_count=0
    else
        # Use bash glob for file counting to avoid find exit code issues
        local -a json_files=("${INBOX_DIR}"/*.json)
        if [[ -e "${json_files[0]}" ]]; then
            inbox_count=${#json_files[@]}
        else
            inbox_count=0
        fi
    fi
    echo "Messages in inbox: ${inbox_count}"
}

# Interactive mode. Exits cleanly on EOF/stdin closure.
interactive() {
    while true; do
        echo ""
        echo "=== v0.3.0 Orchestrator ==="
        echo "1. Start fresh (week 1)"
        echo "2. Resume"
        echo "3. Show status"
        echo "4. Run specific chain"
        echo "5. Setup worktrees only"
        echo "6. Cleanup worktrees"
        echo "7. Send manual message"
        echo "8. View inbox"
        echo "9. Exit"
        echo ""
        if ! read -rp "Choice: " choice; then
            log_info "Input stream closed, exiting interactive mode"
            break
        fi

        case "${choice}" in
            1) init_state; orchestrate 1 ;;
            2) resume ;;
            3) show_status ;;
            4)
                if ! read -rp "Chain number (1-6): " chain_num; then
                    log_info "Input stream closed"
                    break
                fi
                if [[ ! "${chain_num}" =~ ^[1-6]$ ]]; then
                    log_error "Invalid chain number: '${chain_num}'. Must be 1-6."
                    continue
                fi
                run_chain "${chain_num}"
                ;;
            5) for_each_chain setup_worktree || true ;;
            6) for_each_chain cleanup_worktree || true ;;
            7)
                if ! read -rp "From chain (1-6): " from; then
                    log_info "Input stream closed"
                    break
                fi
                if ! read -rp "To chain (1-6): " to; then
                    log_info "Input stream closed"
                    break
                fi
                if [[ ! "${from}" =~ ^[1-6]$ ]] || [[ ! "${to}" =~ ^[1-6]$ ]]; then
                    log_error "Invalid chain number. Must be 1-6."
                    continue
                fi
                if ! read -rp "Subject: " subject; then
                    log_info "Input stream closed"
                    break
                fi
                if ! read -rp "Body: " body; then
                    log_info "Input stream closed"
                    break
                fi
                send_message "${from}" "${to}" "${subject}" "${body}"
                ;;
            8)
                echo "=== Inbox ==="
                if [[ ! -d "${INBOX_DIR}" ]]; then
                    log_warn "Inbox directory does not exist: ${INBOX_DIR}"
                else
                    for f in "${INBOX_DIR}"/*.json; do
                        [[ -f "$f" ]] || continue
                        echo "--- $(basename "$f") ---"
                        if ! jq '.' "$f" 2>&1; then
                            log_warn "Failed to parse: $f"
                        fi
                    done
                fi
                ;;
            9) exit 0 ;;
            *) log_error "Invalid choice" ;;
        esac
    done
}

# Cleanup entire project (for when v0.3.0 completes)
cleanup_project() {
    log_warn "This will remove all v0.3.0 project artifacts!"
    local confirm
    if ! read -rp "Are you sure? (yes/no): " confirm; then
        log_warn "Input stream closed, aborting cleanup"
        return 1
    fi
    if [[ "${confirm}" != "yes" ]]; then
        log_info "Cleanup cancelled"
        return 0
    fi
    local failures=0
    for_each_chain cleanup_worktree || failures=$?
    if [[ ${failures} -gt 0 ]]; then
        log_warn "${failures} worktree(s) failed to remove"
    fi
    log_info "Worktrees removed. Project directory preserved at ${PROJECT_DIR}"
    log_info "To fully remove: rm -rf ${PROJECT_DIR}"
}

# Entrypoint
main() {
    if ! init_state; then
        log_error "Failed to initialize state, aborting"
        exit 1
    fi

    case "${1:-interactive}" in
        start) orchestrate "${2:-1}" ;;
        resume) resume ;;
        status) show_status ;;
        chain)
            if [[ -z "${2:-}" ]] || [[ ! "${2}" =~ ^[1-6]$ ]]; then
                log_error "Usage: $0 chain N (where N is 1-6)"
                exit 1
            fi
            run_chain "${2}"
            ;;
        setup) for_each_chain setup_worktree || true ;;
        cleanup) cleanup_project ;;
        interactive) interactive ;;
        help|--help|-h)
            echo "Usage: $0 {start [week]|resume|status|chain N|setup|cleanup|interactive}"
            echo ""
            echo "Commands:"
            echo "  start [week]  - Begin orchestration from specified week (default: 1)"
            echo "  resume        - Continue from last saved state"
            echo "  status        - Show current progress"
            echo "  chain N       - Run only chain N (1-6)"
            echo "  setup         - Create all worktrees without running"
            echo "  cleanup       - Remove all worktrees (preserves state)"
            echo "  interactive   - Menu-driven mode (default)"
            echo ""
            echo "Environment:"
            echo "  AGENT_CMD=${AGENT_CMD}  (claude or copilot)"
            echo "  PARALLEL_CHAINS=${PARALLEL_CHAINS}  (max concurrent chains, default 3)"
            echo "  DECISION_MODEL=${DECISION_MODEL}  (opus or sonnet for decision escalation)"
            echo "  CRITIC_MODEL=${CRITIC_MODEL}  (sonnet or opus for critic validation)"
            echo ""
            echo "Feedback Loops:"
            echo "  1. Work Verification: Checks for actual commits/changes before proceeding"
            echo "  2. Critic Validation: Reviews code quality, runs ${MAX_CRITIQUE_ROUNDS} rounds max"
            echo "  3. PR/CI Gate: Ensures PR exists and all CI checks pass"
            echo ""
            echo "Decision Escalation:"
            echo "  When agents ask questions, they are automatically escalated to"
            echo "  the DECISION_MODEL for autonomous resolution. Decisions are logged"
            echo "  to ${DECISION_LOG}"
            echo ""
            echo "Completion Criteria (ALL required):"
            echo "  - Actual work done (commits or changes)"
            echo "  - Critic validation passed"
            echo "  - PR created"
            echo "  - All CI checks passing"
            ;;
        *)
            echo "Unknown command: $1"
            echo "Run '$0 help' for usage"
            exit 1
            ;;
    esac
}

main "$@"
