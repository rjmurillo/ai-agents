# Root Cause Pattern: Governance Without Enforcement

**Pattern ID**: RootCause-Process-001
**Category**: Fail-Safe Design
**Created**: 2026-01-15
**Source**: PR #908 Comprehensive Retrospective

## Description

Governance limits exist (ADR-008: 20 commits, best practice: 5-10 files) and are enforced via
pre-push hooks and CI checks. However, enforcement gaps emerge when: agents lack visible counters,
BLOCKING synthesis results are ignored, or the session protocol does not surface limits at the
right moment. When limits are invisible (no running counter) or feedback arrives too late, violations
accumulate despite gates existing.

## Detection Signals

- Commit count exceeds 20 without agent awareness
- PR created with >10 files without validation
- Architect review says "BLOCKING" but work continues
- ADR exists but not referenced in session checklist
- Governance limits mentioned in ADRs but absent from session protocol

## Prevention Skills

- **Skill-Governance-Enforcer-001**: Before PR creation, validate governance: commits ≤20,
  files ≤10, no BLOCKING synthesis, ADR compliance checked
- **Skill-PR-Size-Validator-001**: Automated pre-PR gate checking commit and file counts
- **Skill-Protocol-Commit-Counter-001**: Session protocol includes running commit counter
- **Skill-Orchestrator-Synthesis-Block-001**: Halt execution on BLOCKING synthesis result

## Evidence from PR #908

- **Incident**: PR #908 (59 commits, 95 files, P1 BLOCKING ignored)
- **Root Cause Path**:
  - Q1: Why 59 commits? → No counter
  - Q2: Why no counter? → Not in protocol
  - Q3: Why not in protocol? → ADR-008 not integrated
  - Q4: Why not integrated? → No process to sync ADRs to protocol
  - Q5: Why no process? → Governance gates exist but weren't surfaced at the right moment
- **Resolution**: Created pre-PR validation script that checks all governance limits

## Related Patterns

- **Similar to**: RootCause-Context-Loss-002 (session continuation without loading prior context)
- **Related to**: RootCause-Process-002 (Late Feedback Loop)
- **Related to**: RootCause-Process-003 (Scope Creep via Tool Side Effects)
- **Case Study**: PR #908 (https://github.com/rjmurillo/ai-agents/pull/908)

## References

- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (lines 997-1036)
- PR: https://github.com/rjmurillo/ai-agents/pull/908
- ADR-008: governance limits specification
