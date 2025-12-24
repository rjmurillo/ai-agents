# Skill-Planning-006: Priority Consistency for Shared Recommendations

**Statement**: Recommendations affecting multiple agents must list identical priority across all affected agent rows.

**Context**: When creating multi-agent recommendation tables.

**Evidence**: FORMAT-001 split across High (explainer) and Low (roadmap) led to roadmap instance being skipped.

**Atomicity**: 95% | **Impact**: 8/10

## Correct Pattern

```markdown
| Agent     | Recommendation             | Priority |
|-----------|----------------------------|----------|
| explainer | Add anti-marketing section | Medium   |
| roadmap   | Add anti-marketing section | Medium   |
```

## Validation Rule

If recommendation affects agents [A, B], priority must be identical for A and B rows.
