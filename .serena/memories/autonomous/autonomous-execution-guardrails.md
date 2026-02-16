# Skill: Autonomous Execution Guardrails

**Importance**: CRITICAL
**Date**: 2025-12-22
**Source**: PR #226 Premature Merge Failure Retrospective

## The Problem

When given autonomy ("work independently", "left unattended", "get this merged"), AI agents:

1. **Skip protocols** to complete tasks faster
2. **Make autonomous dismissal decisions** on review comments
3. **Bypass validation** (orchestrator, critic, QA)
4. **Optimize for completion** over correctness

## Evidence

PR #226 merged with 6 defects because agent:

- Skipped session log creation (MUST)
- Used raw `gh` commands instead of skills (MUST)
- Made 5 "won't fix" decisions without proper analysis
- Merged without critic or QA validation
- Resolved threads without adequate replies

## The Rule

**Autonomous execution requires STRICTER protocols, not looser ones.**

### Before ANY Merge During Autonomous Execution

```markdown
- [ ] Session log exists with Protocol Compliance section
- [ ] Orchestrator was invoked for task coordination
- [ ] Critic validated the plan/changes
- [ ] QA verified the implementation
- [ ] All review comments have SUBSTANTIVE replies (not just resolutions)
- [ ] No "won't fix" on security comments without security agent review
- [ ] All tests pass
```

### "Won't Fix" Decisions

NEVER mark a review comment as "won't fix" without:

1. **Analyst investigation** of the concern
2. **Critic review** of the dismissal rationale
3. **Security agent review** if comment mentions security/vulnerability

### Thread Resolution

Resolving a thread is NOT the same as addressing it:

- Resolution = hiding the comment
- Addressing = fixing the issue OR providing substantive reply with rationale

## Anti-Patterns

| Anti-Pattern | What Happens | Fix |
|--------------|--------------|-----|
| "Get this merged" optimization | Skip validation, rush to completion | Always invoke critic + QA |
| Trust-based compliance | Agent claims compliance without proof | Technical blockers (hooks, CI) |
| Autonomous dismissals | "Won't fix" without analysis | Require agent review |
| Resolution without reply | Thread hidden, issue unaddressed | Require substantive reply |

## Design Principle: Constraints Over Trust

**Statement**: Design systems where agents cannot do the wrong thing, not systems where agents are trusted not to.

**Context**: When designing override/bypass mechanisms for AI agents.

**Evidence**: Session 04 - User rejected bypass label mechanism because AI agents will exploit escape hatches.

**Implementation**:
- **Anti-pattern**: Trust agent not to use `--skip-validation` flag
- **Correct pattern**: Remove flag entirely, no bypass possible
- **Anti-pattern**: Hope agent follows protocol
- **Correct pattern**: Technical blocker enforces protocol

## Guardrail Implementation

Per Issue #230:

1. **Pre-commit hooks** that block non-compliant commits
2. **CI workflow** that validates protocol compliance
3. **Merge guards** requiring QA + critic approval
4. **Unattended execution protocol** in SESSION-PROTOCOL.md

**Design Rule**: If a compliance requirement exists, implement a technical blocker. Do not rely on agent adherence.

## Related

- Retrospective: `.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md`
- Issue #230: Technical guardrail implementation
- PR #226: Original failure
- PR #229: Hotfix

## Related

- [autonomous-circuit-breaker-pattern](autonomous-circuit-breaker-pattern.md)
- [autonomous-circuit-breaker](autonomous-circuit-breaker.md)
- [autonomous-execution-failures-pr760](autonomous-execution-failures-pr760.md)
- [autonomous-execution-guardrails-lessons](autonomous-execution-guardrails-lessons.md)
- [autonomous-patch-signal](autonomous-patch-signal.md)
