# Skill-Protocol-002: RFC 2119 MUST Evidence

**Statement**: Implement RFC 2119 MUST requirements with verification evidence

**Context**: Any phase transition in protocol

**Evidence**: PR #147 - Agent claimed compliance without verification evidence

**Atomicity**: 96%

**Impact**: 10/10 (CRITICAL)

## Compliance Pattern

1. **Execute**: Perform action via tool call
2. **Verify**: Read output/artifact to confirm success
3. **Log**: Record evidence in session log
4. **Gate**: Do not proceed without all three

## Evidence Format

```markdown
## Phase 3: Session Log Creation

Evidence:
- Tool: Write(.agents/sessions/2025-12-20-session-01.md)
- Verification: Read(...) - 45 lines
- Confirmed: File exists with Protocol Compliance section
```

## Anti-Pattern

Proceeding based on memory of prior action without verification

## Related

- [protocol-012-branch-handoffs](protocol-012-branch-handoffs.md)
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [protocol-continuation-session-gap](protocol-continuation-session-gap.md)
