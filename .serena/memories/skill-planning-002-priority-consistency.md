# Skill: Priority Consistency for Shared Recommendations

**Skill ID**: Skill-Planning-Consistency-001

**Statement**: Recommendations affecting multiple agents must list identical priority across all affected agent rows

**Context**: When creating multi-agent recommendation tables with priority assignments

**Evidence**: FORMAT-001 split across High (explainer) and Low (roadmap) led to roadmap instance being skipped

**Atomicity Score**: 95%

**Tag**: helpful

**Impact**: 8/10

**Category**: planning, prioritization, consistency

**Created**: 2025-12-19

**Source**: `.agents/retrospective/2025-12-19-personality-integration-gaps.md`

## Pattern

### Correct

```markdown
| Agent     | Recommendation             | Priority |
|-----------|----------------------------|----------|
| explainer | Add anti-marketing section | Medium   |
| roadmap   | Add anti-marketing section | Medium   |
```

### Incorrect (Triggers Validation Error)

```markdown
| Agent     | Recommendation             | Priority |
|-----------|----------------------------|----------|
| explainer | Add anti-marketing section | High     |
| roadmap   | Add anti-marketing section | Low      |
```

## When to Apply

- Multi-agent recommendation tables
- Any table where the same recommendation appears for multiple agents

## Validation Rule

"If recommendation affects agents [A, B], priority must be identical for A and B rows"

## Benefit

- Prevents priority-based skipping of shared items
- Ensures consistent implementation across all affected agents
