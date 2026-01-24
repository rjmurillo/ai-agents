#!/bin/bash
# Orchestrator for v0.3.0 Milestone Execution
# Manages 6 parallel worktrees with Claude and Copilot CLI agents
#
# Features:
# - Automatic worktree setup
# - Dependency tracking between issues
# - Message passing for chain handoffs
# - Resume capability via state file
# - Agent selection (claude/copilot)

set -euo pipefail

# Configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT="$(cd "${PROJECT_DIR}/../../.." && pwd)"

# Project-specific paths (all contained within .agents/projects/v0.3.0/)
readonly STATE_FILE="${PROJECT_DIR}/state/orchestrator.json"
readonly LOG_DIR="${PROJECT_DIR}/logs"
readonly INBOX_DIR="${PROJECT_DIR}/messages/inbox"
readonly OUTBOX_DIR="${PROJECT_DIR}/messages/outbox"
readonly WORKTREE_BASE="${PROJECT_DIR}/worktrees"
readonly PLAN_FILE="${REPO_ROOT}/.agents/planning/v0.3.0/PLAN.md"

# Agent configuration
AGENT_CMD="${AGENT_CMD:-claude}"  # claude or copilot
PARALLEL_CHAINS="${PARALLEL_CHAINS:-3}"  # How many chains to run simultaneously

# Chain definitions (issue sequences)
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

# Chain directories (relative to WORKTREE_BASE)
declare -A CHAIN_DIRS
CHAIN_DIRS[1]="chain1"
CHAIN_DIRS[2]="chain2"
CHAIN_DIRS[3]="chain3"
CHAIN_DIRS[4]="chain4"
CHAIN_DIRS[5]="chain5"
CHAIN_DIRS[6]="chain6"

# Week scheduling (which chains start when)
declare -A CHAIN_START_WEEK
CHAIN_START_WEEK[1]=1
CHAIN_START_WEEK[2]=1
CHAIN_START_WEEK[3]=1
CHAIN_START_WEEK[4]=3
CHAIN_START_WEEK[5]=3
CHAIN_START_WEEK[6]=5

# Issue dependencies (blockers)
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
readonly NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Initialize state tracking
init_state() {
    mkdir -p "$(dirname "${STATE_FILE}")"
    mkdir -p "${LOG_DIR}"
    mkdir -p "${INBOX_DIR}"
    mkdir -p "${OUTBOX_DIR}"
    mkdir -p "${WORKTREE_BASE}"

    if [[ ! -f "${STATE_FILE}" ]]; then
        cat > "${STATE_FILE}" << 'EOF'
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
        log_info "Created new state file: ${STATE_FILE}"
    fi
}

# Read state value using jq
read_state() {
    local query="$1"
    jq -r "${query}" "${STATE_FILE}"
}

# Update state using jq
update_state() {
    local query="$1"
    local tmp
    tmp=$(mktemp)
    jq "${query}" "${STATE_FILE}" > "${tmp}" && mv "${tmp}" "${STATE_FILE}"
}

# Check if issue dependencies are satisfied
check_dependencies() {
    local issue="$1"
    local blockers="${ISSUE_BLOCKED_BY[$issue]:-}"

    if [[ -z "${blockers}" ]]; then
        return 0  # No dependencies
    fi

    for blocker in ${blockers}; do
        local status
        status=$(read_state ".issues.\"${blocker}\".status // \"pending\"")
        if [[ "${status}" != "completed" ]]; then
            return 1  # Dependency not satisfied
        fi
    done
    return 0
}

# Setup worktree for a chain
setup_worktree() {
    local chain="$1"
    local branch="${CHAIN_BRANCHES[$chain]}"
    local dir="${WORKTREE_BASE}/${CHAIN_DIRS[$chain]}"

    if [[ -d "${dir}" ]]; then
        log_info "Worktree for chain ${chain} already exists at ${dir}"
        return 0
    fi

    log_info "Creating worktree for chain ${chain}: ${dir} (branch: ${branch})"
    (cd "${REPO_ROOT}" && git worktree add "${dir}" -b "${branch}" 2>/dev/null || \
        git worktree add "${dir}" "${branch}" 2>/dev/null || \
        git worktree add "${dir}" -B "${branch}" origin/main)

    log_success "Created worktree for chain ${chain}"
}

# Remove worktree for a chain
cleanup_worktree() {
    local chain="$1"
    local dir="${WORKTREE_BASE}/${CHAIN_DIRS[$chain]}"

    if [[ -d "${dir}" ]]; then
        log_info "Removing worktree for chain ${chain}"
        (cd "${REPO_ROOT}" && git worktree remove "${dir}" --force 2>/dev/null || true)
    fi
}

# Send message to a chain's inbox
send_message() {
    local from_chain="$1"
    local to_chain="$2"
    local subject="$3"
    local body="$4"
    local timestamp
    timestamp=$(date -Iseconds)
    local msg_file="${INBOX_DIR}/chain${to_chain}-$(date +%Y%m%d-%H%M%S)-from-chain${from_chain}.json"

    cat > "${msg_file}" << EOF
{
  "from_chain": ${from_chain},
  "to_chain": ${to_chain},
  "subject": "${subject}",
  "body": "${body}",
  "timestamp": "${timestamp}",
  "read": false
}
EOF

    # Also save to outbox for sender's records
    cp "${msg_file}" "${OUTBOX_DIR}/"
    log_info "Message sent: chain ${from_chain} -> chain ${to_chain}: ${subject}"
}

# Read unread messages for a chain
read_messages() {
    local chain="$1"
    local messages=""

    for msg_file in "${INBOX_DIR}"/chain"${chain}"-*.json; do
        [[ -f "${msg_file}" ]] || continue
        local read_status
        read_status=$(jq -r '.read' "${msg_file}")
        if [[ "${read_status}" == "false" ]]; then
            local subject body
            subject=$(jq -r '.subject' "${msg_file}")
            body=$(jq -r '.body' "${msg_file}")
            messages="${messages}\n- ${subject}: ${body}"
            # Mark as read
            jq '.read = true' "${msg_file}" > "${msg_file}.tmp" && mv "${msg_file}.tmp" "${msg_file}"
        fi
    done

    echo -e "${messages}"
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
- Plan file: .agents/planning/v0.3.0/PLAN.md
- Read the Implementation Card for #${issue} in the plan file

## Instructions
1. Run /session-init to start your session
2. Assign yourself to issue #${issue}
3. Read the issue and its Traycer plan (if available)
4. Implement the solution following the Haiku-Ready steps if provided
5. Run the verification commands in the Implementation Card
6. Create atomic commits with conventional messages
7. When done, push your branch and create a PR

## Messages from Other Chains
${messages:-"No messages from other chains."}

## Exit Criteria
Complete when ALL verification commands in the Implementation Card exit with code 0.
EOF
}

# Run agent on a specific issue
run_agent() {
    local chain="$1"
    local issue="$2"
    local dir="${WORKTREE_BASE}/${CHAIN_DIRS[$chain]}"
    local log_file="${LOG_DIR}/chain${chain}-issue${issue}-$(date +%Y%m%d-%H%M%S).log"
    local prompt
    prompt=$(generate_prompt "${chain}" "${issue}")

    log_info "Starting ${AGENT_CMD} for chain ${chain}, issue #${issue}"
    update_state ".chains.\"${chain}\".status = \"running\" | .chains.\"${chain}\".current_issue = ${issue} | .issues.\"${issue}\".status = \"in_progress\" | .issues.\"${issue}\".started = \"$(date -Iseconds)\""

    # Run agent in worktree directory
    local exit_code=0
    if [[ "${AGENT_CMD}" == "claude" ]]; then
        (cd "${dir}" && claude --print "${prompt}" 2>&1 | tee "${log_file}") || exit_code=$?
    elif [[ "${AGENT_CMD}" == "copilot" ]]; then
        (cd "${dir}" && gh copilot suggest "${prompt}" 2>&1 | tee "${log_file}") || exit_code=$?
    else
        log_error "Unknown agent: ${AGENT_CMD}"
        return 1
    fi

    if [[ ${exit_code} -eq 0 ]]; then
        update_state ".issues.\"${issue}\".status = \"completed\" | .issues.\"${issue}\".completed = \"$(date -Iseconds)\" | .chains.\"${chain}\".completed_issues += [${issue}]"
        log_success "Issue #${issue} completed"

        # Send completion message to dependent chains
        send_completion_message "${chain}" "${issue}"
    else
        update_state ".issues.\"${issue}\".status = \"failed\" | .issues.\"${issue}\".error = \"Exit code ${exit_code}\""
        log_error "Issue #${issue} failed with exit code ${exit_code}"
    fi

    return ${exit_code}
}

# Send message when an issue completes (for dependency notification)
send_completion_message() {
    local from_chain="$1"
    local issue="$2"

    # Find chains/issues that depend on this issue
    for dep_issue in "${!ISSUE_BLOCKED_BY[@]}"; do
        if [[ "${ISSUE_BLOCKED_BY[$dep_issue]}" == *"${issue}"* ]]; then
            # Find which chain owns this dependent issue
            for chain_num in "${!CHAINS[@]}"; do
                if [[ "${CHAINS[$chain_num]}" == *"${dep_issue}"* ]]; then
                    send_message "${from_chain}" "${chain_num}" \
                        "Dependency #${issue} completed" \
                        "Issue #${issue} is done. You can now start #${dep_issue}."
                fi
            done
        fi
    done
}

# Get next issue to work on for a chain
get_next_issue() {
    local chain="$1"
    local issues=(${CHAINS[$chain]})
    local completed
    completed=$(read_state ".chains.\"${chain}\".completed_issues | .[]?" 2>/dev/null | tr '\n' ' ')

    for issue in "${issues[@]}"; do
        # Skip if already completed
        if [[ "${completed}" == *"${issue}"* ]]; then
            continue
        fi

        # Check if dependencies are satisfied
        if check_dependencies "${issue}"; then
            echo "${issue}"
            return 0
        fi
    done

    echo ""  # No available issues
}

# Check if chain is complete
is_chain_complete() {
    local chain="$1"
    local issues=(${CHAINS[$chain]})
    local completed_count
    completed_count=$(read_state ".chains.\"${chain}\".completed_issues | length")

    [[ "${completed_count}" -eq "${#issues[@]}" ]]
}

# Run orchestration loop for a single chain
run_chain() {
    local chain="$1"

    setup_worktree "${chain}"

    while ! is_chain_complete "${chain}"; do
        local next_issue
        next_issue=$(get_next_issue "${chain}")

        if [[ -z "${next_issue}" ]]; then
            log_warn "Chain ${chain}: Waiting for dependencies..."
            sleep 30
            continue
        fi

        run_agent "${chain}" "${next_issue}"

        # Brief pause between issues
        sleep 5
    done

    update_state ".chains.\"${chain}\".status = \"completed\""
    log_success "Chain ${chain} completed!"
}

# Main orchestration
orchestrate() {
    local week="${1:-1}"

    log_info "Starting v0.3.0 orchestration (week ${week})"
    update_state ".started = \"$(date -Iseconds)\" | .current_week = ${week}"

    # Determine which chains to run based on week
    local chains_to_run=()
    for chain_num in "${!CHAIN_START_WEEK[@]}"; do
        if [[ "${CHAIN_START_WEEK[$chain_num]}" -le "${week}" ]]; then
            chains_to_run+=("${chain_num}")
        fi
    done

    log_info "Chains for week ${week}: ${chains_to_run[*]}"

    # Run chains in parallel (up to PARALLEL_CHAINS)
    local pids=()
    local running=0

    for chain in "${chains_to_run[@]}"; do
        # Check if chain already complete
        if is_chain_complete "${chain}"; then
            log_info "Chain ${chain} already complete, skipping"
            continue
        fi

        # Wait if at parallel limit
        while [[ ${running} -ge ${PARALLEL_CHAINS} ]]; do
            for pid in "${pids[@]}"; do
                if ! kill -0 "${pid}" 2>/dev/null; then
                    running=$((running - 1))
                fi
            done
            sleep 5
        done

        # Start chain in background
        run_chain "${chain}" &
        pids+=($!)
        running=$((running + 1))
        log_info "Started chain ${chain} (PID: ${pids[-1]})"
    done

    # Wait for all chains to complete
    for pid in "${pids[@]}"; do
        wait "${pid}" || log_warn "Chain process ${pid} exited with error"
    done

    log_success "Week ${week} orchestration complete!"
}

# Resume from saved state
resume() {
    local week
    week=$(read_state ".current_week")
    log_info "Resuming from week ${week}"
    orchestrate "${week}"
}

# Show current status
show_status() {
    echo "=== v0.3.0 Orchestration Status ==="
    echo "Project dir: ${PROJECT_DIR}"
    echo ""

    for chain in {1..6}; do
        local status
        status=$(read_state ".chains.\"${chain}\".status")
        local current
        current=$(read_state ".chains.\"${chain}\".current_issue // \"none\"")
        local completed
        completed=$(read_state ".chains.\"${chain}\".completed_issues | length")
        local total
        total=$(echo "${CHAINS[$chain]}" | wc -w)

        local color="${NC}"
        case "${status}" in
            completed) color="${GREEN}" ;;
            running) color="${BLUE}" ;;
            pending) color="${YELLOW}" ;;
            *) color="${RED}" ;;
        esac

        echo -e "Chain ${chain}: ${color}${status}${NC} (${completed}/${total}) - Current: #${current}"
        echo "  Issues: ${CHAINS[$chain]}"
        echo "  Branch: ${CHAIN_BRANCHES[$chain]}"
        echo ""
    done

    local inbox_count
    inbox_count=$(find "${INBOX_DIR}" -name "*.json" 2>/dev/null | wc -l)
    echo "Messages in inbox: ${inbox_count}"
}

# Interactive mode
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
        read -rp "Choice: " choice

        case "${choice}" in
            1) init_state; orchestrate 1 ;;
            2) resume ;;
            3) show_status ;;
            4)
                read -rp "Chain number (1-6): " chain_num
                run_chain "${chain_num}"
                ;;
            5)
                for chain in {1..6}; do
                    setup_worktree "${chain}"
                done
                ;;
            6)
                for chain in {1..6}; do
                    cleanup_worktree "${chain}"
                done
                ;;
            7)
                read -rp "From chain: " from
                read -rp "To chain: " to
                read -rp "Subject: " subject
                read -rp "Body: " body
                send_message "${from}" "${to}" "${subject}" "${body}"
                ;;
            8)
                echo "=== Inbox ==="
                for f in "${INBOX_DIR}"/*.json; do
                    [[ -f "$f" ]] || continue
                    echo "--- $(basename "$f") ---"
                    jq '.' "$f"
                done
                ;;
            9) exit 0 ;;
            *) log_error "Invalid choice" ;;
        esac
    done
}

# Cleanup entire project (for when v0.3.0 completes)
cleanup_project() {
    log_warn "This will remove all v0.3.0 project artifacts!"
    read -rp "Are you sure? (yes/no): " confirm
    if [[ "${confirm}" == "yes" ]]; then
        for chain in {1..6}; do
            cleanup_worktree "${chain}"
        done
        log_info "Worktrees removed. Project directory preserved at ${PROJECT_DIR}"
        log_info "To fully remove: rm -rf ${PROJECT_DIR}"
    fi
}

# Entrypoint
main() {
    init_state

    case "${1:-interactive}" in
        start) orchestrate "${2:-1}" ;;
        resume) resume ;;
        status) show_status ;;
        chain) run_chain "${2}" ;;
        setup)
            for chain in {1..6}; do
                setup_worktree "${chain}"
            done
            ;;
        cleanup) cleanup_project ;;
        interactive) interactive ;;
        help|--help|-h)
            echo "Usage: $0 {start [week]|resume|status|chain N|setup|cleanup|interactive}"
            echo ""
            echo "Commands:"
            echo "  start [week]  - Begin orchestration from specified week (default: 1)"
            echo "  resume        - Continue from last saved state"
            echo "  status        - Show current progress"
            echo "  chain N       - Run only chain N"
            echo "  setup         - Create all worktrees without running"
            echo "  cleanup       - Remove all worktrees (preserves state)"
            echo "  interactive   - Menu-driven mode (default)"
            echo ""
            echo "Environment:"
            echo "  AGENT_CMD=${AGENT_CMD}  (claude or copilot)"
            echo "  PARALLEL_CHAINS=${PARALLEL_CHAINS}"
            ;;
        *)
            echo "Unknown command: $1"
            echo "Run '$0 help' for usage"
            exit 1
            ;;
    esac
}

main "$@"
