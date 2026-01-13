# Pre-commit Session Protocol Gap

**Issue**: #796
**Session**: 2026-01-05-session-316
**Severity**: P0 (critical enforcement gap)

## Problem

The `.githooks/pre-commit` hook validates session protocol compliance ONLY when `.agents/` files are staged. This creates a **bypass vulnerability**: if an agent violates SESSION-PROTOCOL.md by not creating a session log, no `.agents/` files exist, and validation is **completely skipped**.

## Root Cause

**Location**: `.githooks/pre-commit` lines 777-831

```bash
# Check if any .agents/ files are staged (indicating an active session)
STAGED_AGENTS_FILES=$(echo "$STAGED_FILES" | grep -E '^\.agents/' || true)

if [ -n "$STAGED_AGENTS_FILES" ]; then
    echo_info "Checking Session Protocol compliance (Start + End)..."
    # ... validation runs ...
fi
```

**Flawed Assumption**: "If `.agents/` files are staged → agent session is running → validate"

**What Actually Happens**: Agent skips protocol → no session log → no `.agents/` files → validation skipped → commit succeeds despite violations

## Case Study: PR #795

**Files Committed**:
- `scripts/Sync-McpConfig.ps1`
- `.factory/mcp.json`

**Session Protocol Violations**:
- ❌ No Serena initialization
- ❌ No HANDOFF.md read
- ❌ No session log created
- ❌ No memory updates
- ❌ No markdown lint
- ❌ No validation run

**Pre-commit Result**: ✅ PASSED (because no `.agents/` files staged)
**CI Status**: WILL FAIL (session protocol validation catches violations)

## Proposed Solution: Option B

**Approach**: Agents must ALWAYS create session logs before substantive work, even for single-file edits or minor changes.

### Requirements

**MUST create session log when**: Modifying any file in these directories
- `scripts/` (infrastructure, automation)
- `src/` (implementation code)
- `build/` (build tooling)
- `.github/` (workflows, actions)
- `.factory/` (Factory Droid configuration)
- `.claude/skills/` (skill definitions)
- `.agents/` (any governance files except HANDOFF.md)

**MAY skip session log when**: Editing documentation only with no functional changes
- `README.md`
- `docs/` (pure documentation, no code/config changes)
- `.vscode/` settings (editor configuration)

### Implementation

Update `.githooks/pre-commit` logic:

```bash
# Detect if this commit requires session validation
REQUIRES_SESSION_LOG=false

for file in $STAGED_FILES; do
    case "$file" in
        scripts/*|src/*|build/*|.github/*|.factory/*|.claude/skills/*)
            REQUIRES_SESSION_LOG=true
            ;;
        .agents/*)
            # Any .agents/ changes require session (even HANDOFF.md checks)
            REQUIRES_SESSION_LOG=true
            ;;
    esac
done

# Require session log for substantive work
if [ "$REQUIRES_SESSION_LOG" = "true" ]; then
    # Check for staged session log
    STAGED_SESSION_LOG=$(echo "$STAGED_FILES" | grep -E '^\.agents/sessions/[0-9]{4}-[0-9]{2}-[0-9]{2}-session-[0-9]+.*\.json$' | tail -n 1)
    
    if [ -z "$STAGED_SESSION_LOG" ]; then
        echo_error "BLOCKED: Session log required"
        echo_info "Before committing scripts/src/build/.github/.factory files:"
        echo_info "  1. Initialize Serena: mcp__serena__activate_project"
        echo_info "  2. Read context: Read HANDOFF.md"
        echo_info "  3. Create session log: .agents/sessions/YYYY-MM-DD-session-NN.json"
        echo_info "  4. Complete protocol requirements in session log"
        echo_info "  5. Re-run git add to include the log"
        echo_info ""
        echo_info "See: .agents/SESSION-PROTOCOL.md for complete requirements"
        EXIT_STATUS=1
    else
        # Session log exists → validate it
        if ! pwsh -NoProfile -ExecutionPolicy Bypass -File "$SESSION_VALIDATE_SCRIPT" -SessionLogPath "$STAGED_SESSION_LOG" -PreCommit 2>&1; then
            echo_error "Session Protocol validation FAILED"
            EXIT_STATUS=1
        else
            echo_success "Session Protocol validation: PASS"
        fi
    fi
else
    echo_info "Documentation-only commit. Skipping session protocol validation."
fi
```

## Rationale

### Why Option B: Always Require Logs

**Alternatives Compared**:

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A: Require logs for specific directories | Explicit, clear scope | Easy to forget which dirs need logs | ❌ Brittle |
| **B: Always require logs** | Simple, consistent, reinforces habits | Forces logs even for trivial edits | ✅ Chosen |
| C: Detect "non-trivial" changes | Flexible, minimal overhead | "Non-trivial" is subjective, hard to define | ❌ Ambiguous |

### Benefits of Session Logs (Even for Minor Work)

1. **Historical traceability**: Every change has context (why, how, who approved)
2. **Learning repository**: Failures and successes are preserved
3. **Debugging aid**: When bugs surface, you have the decision trail
4. **Team onboarding**: New members see "how we do things here"
5. **Process reinforcement**: Repeating the protocol prevents regression

**Evidence**: From `.agents/analysis/001-merge-resolver-session-protocol-gap.md`:
> Session logs (.agents/sessions/), analysis artifacts (.agents/analysis/), and memory updates (.serena/memories/) are **audit trail, not implementation**.

By design, the audit trail has value even for small tasks.

## Implementation Tasks

- [ ] Update `.githooks/pre-commit` to detect "requires session log" directories
- [ ] Add session log requirement check before validation
- [ ] Create light session log template for minor work
- [ ] Update AGENTS.md "Session Protocol" section with new guidance
- [ ] Update SESSION-PROTOCOL.md with "When to Create Session Log" section
- [ ] Test pre-commit hook with various scenarios
- [ ] Add regression test to CI

## Acceptance Criteria

- [ ] Pre-commit blocks commits to `scripts/`, `src/`, `build/`, `.github/`, `.factory/` without session log
- [ ] Pre-commit allows commits to `README.md`, `docs/` without session log
- [ ] Session log validation runs when log is present
- [ ] PR #795 scenario would be blocked under new rules
- [ ] Documentation updated to reflect Option B choice
- [ ] Regression test added to CI to prevent recurrence

## Related

- Issue #796 (full documentation)
- SESSION-PROTOCOL.md
- `.agents/analysis/001-merge-resolver-session-protocol-gap.md`
- PR #795 (case study that exposed gap)
