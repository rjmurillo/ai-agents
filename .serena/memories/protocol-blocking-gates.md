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
