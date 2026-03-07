# ADR Exception Criteria

**Status**: Active  
**Date**: 2026-03-07  
**Related ADR**: ADR-044 (this document implements that decision)  
**GitHub Issue**: #947

---

## Purpose

ADR exceptions permit narrow deviations from accepted decisions. However, creating an exception without understanding *why the rule exists* risks eroding architectural governance over time.

**All ADR exception requests MUST include a Chesterton's Fence analysis before approval.**

---

## Chesterton's Fence Requirement

> "Before you remove a fence, understand why it was built."

Before requesting an ADR exception, you MUST answer the following three questions. Incomplete submissions are rejected without review.

### 1. Why Does the Rule Exist?

Quote the original ADR rationale — do not paraphrase. If you cannot find the rationale, escalate to the architect before proceeding.

### 2. Impact If Removed

Document what breaks, degrades, or becomes inconsistent if the rule is removed or permanently excepted:
- Technical debt introduced
- Testing and tooling fragmentation
- Precedent risk for future violations
- Enforcement complexity

### 3. Alternatives Tried

List at least two compliance attempts made before requesting the exception. For each:
- What was attempted
- Why it did not satisfy the requirement

If you have not attempted compliance, you cannot request an exception.

---

## Exception Request Template

Use this template when adding an exception to an ADR. The exception block is added directly to the ADR's `## Exceptions` section.

```markdown
### Exception to ADR-NNN: [ADR Title]

**Requestor**: [Agent or person]
**Date**: [YYYY-MM-DD]
**PR/Issue**: [Reference link]

#### Chesterton's Fence Analysis

**Why does the rule exist?**
> [Direct quote from the ADR's Context, Decision, or Rationale section]

**Impact if removed?**
- [Consequence 1: be specific — what breaks or degrades?]
- [Consequence 2]
- [Precedent risk: what future violations does this enable?]

**Alternatives tried:**
1. **[Attempt 1]**: [What was tried] → [Why it failed or was insufficient]
2. **[Attempt 2]**: [What was tried] → [Why it failed or was insufficient]

#### Exception Details

**Scope**: [Exact path pattern or bounded context — be as narrow as possible]

**Purpose**: [What this exception enables — one sentence]

**Justification**:
- [Reason 1: ties back to alternatives tried]
- [Reason 2: explains why exception is narrower than removing the rule]

**Conditions**:
1. [MUST requirement 1 — enforceable constraint]
2. [MUST requirement 2]
3. This exception MUST NOT be used as precedent for [scope boundaries]

**Approved By**: [Authority] via [PR/Issue reference]
```

---

## Rejection Criteria

An exception request is rejected if:

- The original ADR rationale is not quoted (paraphrase is insufficient)
- Fewer than two alternatives are documented
- The impact assessment is missing or generic
- The scope is not bounded (e.g., "all Python files" is not a valid scope)
- The conditions do not include enforceable MUST requirements
- The request was submitted without attempting compliance

---

## Example: PR #908 (Claude Code Hooks)

This exception was approved in PR #908 but lacked Chesterton's Fence documentation at the time. It is retroactively documented here as an exemplar.

**ADR-005 rationale (quoted)**:
> "This resulted in: Token waste: Generating bash/Python code that was later replaced with PowerShell; Inconsistent tooling: Mix of bash, Python, and PowerShell across codebase; Testing fragmentation: Pester tests for PowerShell, bats/pytest for bash/Python"

**Impact if ADR-005 removed**:
- Testing fragmentation (Pester + pytest in same repo)
- Agent token waste re-generating scripts in wrong language
- Loss of enforcement signal for new contributors and agents

**Alternatives tried**:
1. **PowerShell HTTP calls to Anthropic API**: Verbose, no official SDK, error-prone SSL handling → insufficient for production hook use
2. **PowerShell wrapper calling Python subprocess**: Introduced dependency on Python availability without gaining SDK benefits → added complexity without solving the core problem

**Result**: Exception approved with narrow scope (`.claude/hooks/**/*.py` only), documented in ADR-005 §Exceptions.

---

## Architect Agent Enforcement

The architect agent validates exception requests against this document. See `src/claude/architect.md` §Exception Request Validation for the checklist.

---

## Governance

- This document is enforced by the architect agent during ADR review.
- Exceptions that bypass this process are subject to retroactive revocation.
- The bar for exceptions is intentionally high. That is by design.
