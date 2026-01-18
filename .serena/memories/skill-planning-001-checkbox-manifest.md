# Skill: Checkbox Manifest for Analysis Documents

**Skill ID**: Skill-Planning-Verification-001

**Statement**: Analysis documents with N recommendations require checkbox manifest at top linking each item to its section

**Context**: When creating analysis documents that will drive implementation

**Evidence**: Personality integration: 4 of 20 items missed without tracking manifest (20% miss rate)

**Atomicity Score**: 92%

**Tag**: helpful

**Impact**: 9/10

**Category**: planning, verification, tracking

**Created**: 2025-12-19

**Source**: `.agents/retrospective/2025-12-19-personality-integration-gaps.md`

## Pattern

```markdown
## Implementation Checklist

- [ ] ITEM-001: Description of first recommendation (see Section X.Y)
- [ ] ITEM-002: Description of second recommendation (see Section X.Y)
- [ ] ...

Total Items: N
Implemented: M
Gap: N-M
```

## When to Apply

- Analysis documents with 3+ recommendations
- Any document that will drive multi-item implementation
- Plans with numbered action items

## Benefit

- Prevents items from being skipped (visual accountability)
- Provides real-time completion tracking
- Enables gap detection DURING implementation, not just after
