# Skill-PR-Review-007: CI Verification Before Completion

## Statement

Before claiming PR review complete, verify ALL CI checks pass via `gh pr checks`; `mergeable: MERGEABLE` only indicates no conflicts, not CI status.

## Context

When completing PR review response (Phase 8 verification). The `mergeable` field from `gh pr view --json mergeable` only checks:
- No merge conflicts
- Branch is compatible with base

It does NOT indicate:
- CI checks passing
- Required status checks satisfied

## Evidence

**Run 20487393463 (Session 56)**: Agent claimed PR #199 was "MERGEABLE" based on `gh pr view --json mergeable` returning `"MERGEABLE"`, but failed to verify CI checks. The run failed with `MUST: HANDOFF.md Updated: FAIL` but agent claimed completion without checking CI.

**Root Cause**: Agent verified:
1. ✅ Resolved all 11 review threads via GraphQL mutations
2. ✅ Verified 0 unresolved threads via GraphQL query
3. ✅ Ran `gh pr view 199 --json state,mergeable,reviewDecision` → `{"mergeable":"MERGEABLE",...}`

But MISSED:
- ❌ Did NOT run `gh pr checks 199` to verify CI status

## Atomicity

**Score**: 96%

**Deductions**: None - single concept, measurable, actionable, has metrics

## Impact

**Score**: 10/10 (CRITICAL)

**Rationale**: Claiming PR is ready to merge when CI checks are failing wastes reviewer time and can introduce broken code to main branch.

## Pattern

### INCORRECT: Relying on `mergeable` field alone

```bash
# Agent checks mergeable status
gh pr view 199 --json state,mergeable,reviewDecision
# Returns: {"mergeable":"MERGEABLE","state":"OPEN","reviewDecision":"APPROVED"}

# Agent concludes: PR is ready to merge ❌ WRONG
```

**Problem**: `mergeable: "MERGEABLE"` only means no conflicts, not that CI passes.

### CORRECT: Verify CI checks explicitly

```bash
# After all other verification, BEFORE claiming completion
gh pr checks 199 --json name,state,conclusion

# Parse results
FAILED_CHECKS=$(gh pr checks 199 --json name,state,conclusion | \
  jq '[.[] | select(.conclusion != "success" and .conclusion != "skipped" and .conclusion != null)]')

if [ "$(echo "$FAILED_CHECKS" | jq 'length')" -gt 0 ]; then
  echo "[BLOCKED] CI checks not passing:"
  echo "$FAILED_CHECKS" | jq -r '.[].name'
  # Do NOT claim completion
  exit 1
fi
```

## Verification Checklist

Before claiming PR review complete, ALL must be true:

| Criterion | Verification Command | Required |
|-----------|---------------------|----------|
| All comments resolved | `grep -c "Status: \\[COMPLETE\\]\\|\\[WONTFIX\\]"` equals total | Yes |
| No new comments | Re-check after 45s wait returned 0 new | Yes |
| **CI checks pass** | **`gh pr checks` all success/skipped** | **Yes** |
| No unresolved threads | GraphQL query for unresolved reviewThreads | Yes |
| Commits pushed | `git status` shows "up to date with origin" | Yes |

## Implementation

### In pr-comment-responder Phase 8.4

Add after Phase 8.3 (re-check for new comments), before Phase 8.5 (completion criteria checklist):

```bash
#### Phase 8.4: CI Check Verification

**MANDATORY**: Verify CI checks pass before claiming completion.

\```bash
# Check PR CI status
echo "=== CI Check Verification ==="
gh pr checks [number] --json name,state,conclusion > ci-checks.json

# Parse for failures
FAILED_CHECKS=$(cat ci-checks.json | jq '[.[] | select(.conclusion != "success" and .conclusion != "skipped" and .conclusion != null)]')
FAILED_COUNT=$(echo "$FAILED_CHECKS" | jq 'length')

if [ "$FAILED_COUNT" -gt 0 ]; then
  echo "[BLOCKED] $FAILED_COUNT CI checks not passing:"
  echo "$FAILED_CHECKS" | jq -r '.[] | "  - \\(.name): \\(.conclusion)"'
  
  # Parse actionable items from failures
  echo ""
  echo "Actionable items:"
  # Add logic to parse specific failure messages
  
  # Return to Phase 6 for fixes
  exit 1
fi

echo "[PASS] All CI checks passing ($(cat ci-checks.json | jq 'length') checks)"
\```

**Exit codes**:
- `0`: All checks passing (or skipped)
- `1`: One or more checks failed (blocks completion)
```

### In pr-review command

Update completion criteria table to emphasize CI verification:

```markdown
| Criterion | Verification | Required |
|-----------|--------------|----------|
| All comments resolved | Each comment has [COMPLETE] or [WONTFIX] status | Yes |
| No new comments | Re-check after 45s wait returned 0 new | Yes |
| **CI checks pass** | **`gh pr checks` all green (including AI Quality Gate)** | **Yes** |
| No unresolved threads | GraphQL query for unresolved reviewThreads | Yes |
| Commits pushed | `git status` shows "up to date with origin" | Yes |
```

## Related Skills

- Skill-PR-003: Verification count (comment count matching)
- Skill-PR-Review-002: Conversation resolution protocol
- Skill-Validation-006: Self-report verification (don't trust agent claims)

## Category

pr-review, ci-infrastructure, verification

## Tags

helpful, critical, blocking-gate

## Validation Count

1 (Session 56, PR #199 false completion)

## Created

2025-01-XX (from Issue #XXX analysis)

## Source

Issue #XXX: "fix: Add mandatory CI check verification before claiming PR review complete"
