# Skill: Section Cross-References in Summaries

**Skill ID**: Skill-Requirements-Clarity-001

**Statement**: Recommendation summaries must include section references for detailed specifications (e.g., 'Add X - see Section 5.3')

**Context**: When creating summary tables for recommendations with detailed specifications elsewhere

**Evidence**: TECH-003 and AGENCY-004 missed specification details due to summary-only implementation

**Atomicity Score**: 90%

**Tag**: helpful

**Impact**: 8/10

**Category**: requirements, documentation, cross-reference

**Created**: 2025-12-19

**Source**: `.agents/retrospective/2025-12-19-personality-integration-gaps.md`

## Pattern

### Before (Avoid)

```markdown
| Agent | Recommendation | Priority |
|-------|----------------|----------|
| qa    | Add code quality gates | Medium |
```

### After (Use)

```markdown
| Agent | Recommendation | Priority |
|-------|----------------|----------|
| qa    | Add code quality gates (see Section 5.3) | Medium |
```

## When to Apply

- Any summary table where items have detailed specifications in other sections
- When recommendations require specific implementation details beyond the summary

## Benefit

- Encourages implementers to read full specifications before implementing
- Prevents interpretation ambiguity
- Addresses 2-3 of 4 root causes observed in personality integration retrospective
