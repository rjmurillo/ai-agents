# Strategic Advisory: ADR-042 Python Migration

## Verdict: ACCEPT

The decision is correct. The timing is right. The execution needs fixing before implementation starts.

---

## Strategic Assessment

### What You Got Right

**You already made the real decision when you merged PR #962.**

skill-installer introduced Python 3.10+ as a hard prerequisite. That was the inflection point. Everything after is implementation details.

ADR-042 documents what already happened. The question is not "should we migrate to Python?" The question is "should we pretend we didn't already commit to Python?"

**The answer is no.**

### What the Reviews Are Missing

Analyst, Architect, and Critic all say CONCERNS. They list 14 P0/P1/P2 issues. They want governance docs updated, pyproject.toml created, pytest infrastructure built, constraint files synchronized.

**They are correct about the issues.**

**They are wrong about blocking the ADR.**

**ADR-042 is a strategy document, not an implementation plan.**

The ADR answers: "Should we migrate to Python?" YES.

The ADR does not answer: "How do we execute Phase 1 foundation setup?" That is implementation work.

---

## The Real Issue Being Avoided

You wrote: "Bite the bullet and migrate. Incrementally and opportunistically."

**Then your agents are trying to plan the entire migration before approving the strategy decision.**

This is analysis paralysis. You have three agents saying CONCERNS because pyproject.toml does not exist yet. That is like blocking a decision to build a house because you have not bought lumber.

**The decision is whether to build. The lumber comes after.**

---

## Path Forward

### What Should Happen Now

**1. Accept ADR-042 immediately with one P0 fix.**

The ADR claims "Python-only (chosen)" but reality is "Python-first with multi-year migration."

**Fix**: Change decision language from "Python-only" to "Python-first with phased migration."

**Why**: Path dependence. 235 PowerShell files exist. They do not disappear overnight.

**2. Update governance docs as implementation work, not blocking requirements.**

When you start Phase 1 implementation, the implementer will update constraints as part of foundation setup. Updating documentation does not require architect debate. It requires git commits.

**3. Treat Phase 1 foundation as next task, not ADR prerequisite.**

Phase 1 checklist:

- [ ] pyproject.toml
- [ ] pytest infrastructure
- [ ] Updated PROJECT-CONSTRAINTS.md
- [ ] Updated CRITICAL-CONTEXT.md
- [ ] Updated pre-commit hook

**This is implementation work.** Route to implementer after ADR acceptance.

---

## Priority Call

### P0 - Do Before Merging ADR-042

**Fix Path Dependence Language** (10 minutes)

Change decision statement from "Python-only" references to "Python-first with phased migration."

Add "12-24 month migration period" to decision statement.

### P1 - Do During Phase 1 Implementation (Not Before ADR Merge)

All the things architect and critic want:

- pyproject.toml specification
- pytest infrastructure
- PROJECT-CONSTRAINTS.md update
- CRITICAL-CONTEXT.md update
- Pre-commit hook changes

**These are implementation tasks, not strategy blockers.**

Create GitHub issue: "ADR-042 Phase 1 Foundation Setup" with checklist. Route to implementer after ADR merge.

### P2 - Do Before Phase 3 Migration Starts

- Rollback strategy
- Developer training plan
- Deprecation timeline
- Migration priority metrics

**You have months before Phase 3.** Do not block strategy decision on multi-month execution planning.

---

## What You Are Avoiding

**You are avoiding the sunk cost conversation.**

829 lines of bash deleted during PR #60 became the rationale for ADR-005 (PowerShell-only).

Now you want to reverse ADR-005 six weeks after creating it.

**Strategic Answer: This is different.**

ADR-005 rationale was "token efficiency" (agents waste tokens on Python).

**That rationale died when you approved Python exceptions for hooks (PR #908) and SkillForge (PR #760).**

If agents can write Python hooks successfully without token waste, the original ADR-005 premise was wrong.

PR #962 (skill-installer) was the moment you admitted Python is a project dependency.

ADR-042 is not reversing a good decision. It is correcting a decision whose premise no longer holds.

---

## Final Recommendation

### What To Do Right Now

1. **Fix Path Dependence language in ADR-042** (10 minutes)
2. **Merge ADR-042** without waiting for pyproject.toml, pytest, or governance updates
3. **Create Phase 1 implementation issue** with checklist
4. **Route to implementer** for Phase 1 foundation work
5. **Stop debating strategy** and start executing

### Warning

**If you delay ADR-042 waiting for perfect execution plans, you will create governance incoherence.**

Reality: Python is already a prerequisite (PR #962).
Reality: Python exceptions already exist (hooks, SkillForge).
Reality: ADR-005 rationale no longer holds.

Delaying ADR-042 does not delay Python adoption. It just means your ADRs lie about project state.

**Better to have imperfect ADR-042 merged with Phase 1 incomplete than coherent-looking ADR-005 that contradicts reality.**

---

## Summary

**Decision**: ACCEPT ADR-042 with Path Dependence fix.

**Priority**: P0 is language fix (10 min), P1 is Phase 1 implementation (route to implementer), P2 is Phase 3 planning (do later).

**Action**: Fix ADR-042 decision statement, merge immediately, create Phase 1 issue, route to implementer.

**Truth**: You already committed to Python when you merged PR #962. ADR-042 documents that reality. Fix the path dependence language, then execute Phase 1.

---

*Reviewer: high-level-advisor*
*Date: 2026-01-17*
