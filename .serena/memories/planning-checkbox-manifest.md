# Skill-Planning-005: Checkbox Manifest for Analysis

**Statement**: Analysis documents with N recommendations require checkbox manifest at top linking each item to its section.

**Context**: When creating analysis documents that will drive implementation.

**Evidence**: Personality integration: 4 of 20 items missed without tracking manifest (20% miss rate).

**Atomicity**: 92% | **Impact**: 9/10

**Pattern**:

```markdown
## Implementation Checklist

- [ ] ITEM-001: Description of first recommendation (see Section X.Y)
- [ ] ITEM-002: Description of second recommendation (see Section X.Y)

Total Items: N | Implemented: M | Gap: N-M
```

**When to Apply**: Analysis documents with 3+ recommendations
