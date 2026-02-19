# Skill-Workflow-012: Branch Handoffs for Feature Branch Validator Compliance

**Statement**: On feature branches, create branch handoffs at `.agents/handoffs/{branch}/{session}.md` to satisfy validator without updating HANDOFF.md

**Context**: Session End validation on feature branches where HANDOFF.md is read-only (ADR-014)

**Category**: Protocol / Session-Init

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 9/10 - Resolves circular dependency between validator and pre-commit enforcement

**Created**: 2025-12-24

**Last Validated**: 2025-12-24

**Validation Count**: 1

**Failure Count**: 0

## Evidence

**Source**: Session 92-93

**Problem Discovered**:

Agent attempted to update HANDOFF.md to satisfy Session End validator requirement (E_HANDOFF_LINK_MISSING error at line 255 of `Validate-SessionEnd.ps1`). Pre-commit hook blocked the commit with error: "BLOCKED: HANDOFF.md is read-only on feature branches".

Created circular dependency:

- Validator requires HANDOFF.md update
- Hook blocks HANDOFF.md update
- Agent stuck in loop

**Root Cause**:

Three authoritative sources contradict:

1. **HANDOFF.md**: Says "DO NOT update this file" (read-only since ADR-014)
2. **Session End Validator**: Requires HANDOFF.md to reference session log
3. **Pre-commit Hook**: Blocks HANDOFF.md changes on feature branches

**Correct Pattern**:

On feature branches:

1. Create session log as usual (`.agents/sessions/{date}-session-{nn}.md`)
2. Create branch handoff at `.agents/handoffs/{branch}/{session}.md` instead of updating HANDOFF.md
3. Session log satisfies primary documentation requirement
4. HANDOFF.md "Last 5 sessions" table updated only on main branch (manual or automated)

## Protocol Conflict Details

**ADR-014 (Distributed Handoff Architecture)**:

- Status: Accepted (2025-12-22)
- Rationale: HANDOFF.md grew to 122KB / 35K tokens causing merge conflicts on every PR
- Decision: HANDOFF.md becomes read-only on feature branches
- Enforcement: Pre-commit hook blocks direct modifications

**Validator Requirement** (`Validate-SessionEnd.ps1` lines 245-257):

```powershell
# --- Verify HANDOFF contains a link to this session log
$handoffPath = Join-Path $repoRoot ".agents/HANDOFF.md"
if (-not (Test-Path -LiteralPath $handoffPath)) { 
  Fail 'E_HANDOFF_MISSING' "Missing .agents/HANDOFF.md" 
}
$handoff = Read-AllText $handoffPath

# Accept either [Session NN](./sessions/...) or raw path.
if ($handoff -notmatch [Regex]::Escape(($sessionRel -replace '^\\.agents/',''))) {
  $relFromHandoff = $sessionRel -replace '^\\.agents/',''
  if ($handoff -notmatch [Regex]::Escape($relFromHandoff)) {
    Fail 'E_HANDOFF_LINK_MISSING' "HANDOFF.md does not reference this session log: $relFromHandoff"
  }
}
```

**Pre-commit Hook** (`.githooks/pre-commit` lines 516-534):

```bash
# HANDOFF.md Protection (BLOCKING)
#
# Enforces ADR-014: Distributed Handoff Architecture
# HANDOFF.md is now read-only. Agents must NOT update it during sessions.
# Session context goes to:
#   1. Session logs (.agents/sessions/)
#   2. Serena memory (cross-session context)
#   3. Branch handoffs (.agents/handoffs/{branch}/)

CURRENT_BRANCH=$(git branch --show-current)
STAGED_HANDOFF=$(echo "$STAGED_FILES" | grep -E '^\\.agents/HANDOFF\\.md$' || true)

if [ -n "$STAGED_HANDOFF" ]; then
    # Allow HANDOFF.md updates only on main branch
    if [ "$CURRENT_BRANCH" != "main" ]; then
        echo_error "BLOCKED: HANDOFF.md is read-only on feature branches"
        # ... (error message continues)
    fi
fi
```

## Workaround Implementation

**Directory Structure**:

```text
.agents/
├── HANDOFF.md                          # Read-only on feature branches
├── sessions/
│   └── 2025-12-24-session-92.md       # Session log (always required)
└── handoffs/
    └── feature/
        └── issue-123/
            └── 2025-12-24-session-92.md  # Branch handoff (feature branch only)
```

**Branch Handoff Template**:

```markdown
# Session 92 - Feature Branch Handoff

**Branch**: feature/issue-123
**Session Log**: `2025-12-24-session-92.md`
**Date**: 2025-12-24

## Key Decisions

- Decision 1: ...
- Decision 2: ...

## Status

- [x] Task 1
- [ ] Task 2

## Next Steps

- Step 1
- Step 2
```

## Future Fix

**Issue to be Created**: "Update Validate-SessionEnd.ps1 to accept branch handoffs as alternative to HANDOFF.md link"

**Proposed Fix**:

Modify validator to check:

1. Session log exists (primary requirement)
2. EITHER HANDOFF.md references session log OR branch handoff exists at `.agents/handoffs/{branch}/`

**Acceptance Criteria**:

- [ ] Validator passes on feature branches with branch handoffs
- [ ] Validator still requires HANDOFF.md update on main branch
- [ ] Documentation updated (SESSION-PROTOCOL.md)
- [ ] Pre-commit hook behavior unchanged (still blocks HANDOFF.md on feature branches)

## Related Skills

- Skill-Protocol-001: Verification-based BLOCKING gates
- Skill-Workflow-011: HANDOFF.md session history merge

## References

- ADR-014: `.agents/architecture/ADR-014-distributed-handoff-architecture.md`
- Validator: scripts/Validate-SessionEnd.ps1 (removed) (lines 245-257)
- Hook: `.githooks/pre-commit` (lines 516-534)
- Protocol: `.agents/SESSION-PROTOCOL.md` v1.4

## Related

- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [protocol-continuation-session-gap](protocol-continuation-session-gap.md)
- [protocol-legacy-sessions](protocol-legacy-sessions.md)
