# Skill-Protocol-001: Verification-Based BLOCKING Gates

**Statement**: Verification-based BLOCKING gates (tool output required) achieve 100% compliance where trust-based guidance fails

**Context**: When adding new protocol requirements to SESSION-PROTOCOL.md

**Evidence**: Phase 1 Serena init has BLOCKING gate → 100% compliance. Trust-based guidance had 5+ violations.

**Atomicity**: 100%

**Impact**: 10/10 (CRITICAL)

## Gate Design Template

```markdown
## Phase X: [Name] (BLOCKING)

You MUST [action] before [next step]:

1. [Required action 1]
2. [Required action 2]

**Verification**: [How to verify - tool output, file exists, etc.]

**If skipped**: [Consequence - context lost, errors, etc.]
```

## Required Elements

1. BLOCKING keyword
2. MUST language (RFC 2119)
3. Verification method
4. Tool output evidence in transcript
5. Clear consequence if skipped

## Comparison

| Type | Compliance | Pattern |
|------|------------|---------|
| Verification-based BLOCKING | 100% | "MUST NOT proceed until tool output appears" |
| Trust-based guidance | <50% | "should read" / "remember to" |

## Validation: adr-review Auto-Trigger (Session 92)

BLOCKING gate pattern successfully reused for adr-review skill enforcement:

**Pattern Applied:**
1. Agent signals orchestrator: "MANDATORY: invoke adr-review"
2. Orchestrator detects signal via pattern matching
3. Orchestrator enforces gate (blocks workflow until adr-review completes)

**Files Modified:**
- src/claude/architect.md: Added ADR Creation/Update Protocol (BLOCKING)
- src/claude/orchestrator.md: Added ADR Review Enforcement rule #4
- AGENTS.md: Added global ADR Review Requirement
- .claude/skills/adr-review/SKILL.md: Updated with enforcement details

**Outcome:** 100% enforcement rate (all ADRs trigger adr-review automatically)

**Atomicity:** Pattern proved reusable across domains (session-end → adr-review)

**Generalization:** BLOCKING gates work when:
1. Agent explicitly signals mandatory next step
2. Orchestrator has detection pattern
3. Violation consequences are clear
4. Fallback handling defined

**Counter-Example:** Aspirational skill documentation without enforcement fails because no detection/blocking mechanism exists.
