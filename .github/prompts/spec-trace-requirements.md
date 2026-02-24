# Requirements Traceability Check

You are verifying that implementation changes trace back to specification requirements.

## Task

1. Identify all requirements in the specification (look for REQ-*, acceptance criteria, user stories)
2. For each requirement, determine if the implementation changes address it
3. Report coverage status for each requirement

## Identification Patterns

Look for requirements in these forms:

- `REQ-NNN`: Formal requirement IDs
- `DESIGN-NNN`: Design specification IDs
- `TASK-NNN`: Task identifiers
- `AC-N` or numbered acceptance criteria
- User stories: "As a [user], I want [goal], so that [benefit]"
- Bullet points describing expected behavior
- "SHALL", "MUST", "SHOULD" statements (RFC 2119)

## Coverage Status Definitions

- `COVERED`: Implementation clearly addresses this requirement
- `PARTIAL`: Implementation partially addresses this requirement
- `NOT_COVERED`: No evidence that implementation addresses this requirement
- `N/A`: Requirement is not applicable to these changes

## Output Format

Output your analysis in this format:

```markdown
### Requirements Coverage Matrix

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| REQ-001 | [brief description] | COVERED | [file:line or description] |
| REQ-002 | [brief description] | NOT_COVERED | - |
| REQ-003 | [brief description] | PARTIAL | [what's missing] |

### Summary

- Total Requirements: N
- Covered: N (X%)
- Partially Covered: N (X%)
- Not Covered: N (X%)

### Gaps

1. [Specific gaps or missing implementations]
```

End your analysis with a GitHub Alert block matching the verdict:

For PASS:

```markdown
> [!TIP]
> **VERDICT: PASS**
> All requirements are covered by the implementation.
```

For PARTIAL:

```markdown
> [!WARNING]
> **VERDICT: PARTIAL**
> Some requirements have gaps. [Brief explanation]
```

For FAIL:

```markdown
> [!CAUTION]
> **VERDICT: FAIL**
> Critical requirements are not covered. [Brief explanation]
```

**IMPORTANT**: The alert block must contain exactly `VERDICT: PASS`, `VERDICT: PARTIAL`, or `VERDICT: FAIL` (no brackets around the token).

## Verdict Guidelines

- `PASS`: 100% of requirements COVERED
- `PARTIAL`: >50% requirements covered, but some gaps
- `FAIL`: <50% requirements covered OR critical requirements NOT_COVERED
