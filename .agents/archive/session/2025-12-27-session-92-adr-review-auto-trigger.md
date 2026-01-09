# Session 92: ADR Review Auto-Trigger Fix

**Date**: 2025-12-27
**Branch**: `feat/adr-review-auto-trigger`
**Issue**: Follow-up from Session 91 (P1 action item)

## Outcome

**Status**: SUCCESS - PR #467 created

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

## Limitation Note

The user correctly identified that this fix is a workaround, not a fundamental solution:

**Root Cause**: Claude Code skills are **pull-based**, not **push-based**. There's no automatic skill invocation based on file operations or context detection.

**Why This Matters**: The skill documentation said "triggers on...when architect creates ADR" but this was aspirational documentation, not implemented behavior.

**This Fix**: Adds explicit BLOCKING gates in agent prompts so they signal and invoke the skill manually.

**True Solution** (out of scope): Would require Claude Code framework changes:

- Event-driven skill invocation
- File pattern matching for automatic activation
- Push-based skill triggering

## Protocol Compliance

### Session End Checklist

| Step | Status | Evidence |
|------|--------|----------|
| [x] Session log created | PASS | This file |
| [x] All changes committed | PASS | 4d61706 |
| [x] PR created | PASS | #467 |
| [ ] HANDOFF context stored | Pending | |
| [x] Markdownlint run | PASS | 0 errors in changed files |
| [ ] Validation script | Pending | |

## References

- [Session 91 Analysis](/.agents/analysis/adr-review-trigger-fix.md) - Root cause and fix design
- [Session 91 Log](/.agents/sessions/2025-12-27-session-91-issue-357-quality-gate-prompts.md) - Discovery context
