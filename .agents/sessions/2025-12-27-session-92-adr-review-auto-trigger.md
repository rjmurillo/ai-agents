# Session 92: ADR Review Auto-Trigger Fix

**Date**: 2025-12-27
**Branch**: `feat/adr-review-auto-trigger`
**Issue**: Follow-up from Session 91 (P1 action item)

## Objective

Ensure adr-review skill is ALWAYS triggered automatically when an ADR is created or updated, regardless of which agent performs the operation.

## Customer Impact (Working Backwards)

**Before**: Users must manually request ADR review after architect creates ADRs (discovered in Session 91 with ADR-021).

**After**: ADR review is automatic - architect signals orchestrator with MANDATORY routing, orchestrator enforces the gate.

**Result**: All ADRs receive multi-agent validation without manual intervention.

## Implementation Plan

Based on analysis at `.agents/analysis/adr-review-trigger-fix.md`:

| Change | File | Purpose |
|--------|------|---------|
| 1 | `src/claude/architect.md` | Add BLOCKING gate to handoff protocol |
| 2 | `src/claude/orchestrator.md` | Add ADR Review Enforcement section |
| 3 | `AGENTS.md` | Add global ADR Review Requirement |
| 4 | `.claude/skills/adr-review/SKILL.md` | Update with MANDATORY enforcement language |

## Protocol Compliance

### Session End Checklist

| Step | Status | Evidence |
|------|--------|----------|
| [ ] Session log created | Pending | This file |
| [ ] All changes committed | Pending | |
| [ ] PR created | Pending | |
| [ ] HANDOFF context stored | Pending | |
| [ ] Markdownlint run | Pending | |
| [ ] Validation script | Pending | |

## References

- [Session 91 Analysis](/.agents/analysis/adr-review-trigger-fix.md) - Root cause and fix design
- [Session 91 Log](/.agents/sessions/2025-12-27-session-91-issue-357-quality-gate-prompts.md) - Discovery context
