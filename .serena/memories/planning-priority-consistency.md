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

## Related

- [planning-003-parallel-exploration-pattern](planning-003-parallel-exploration-pattern.md)
- [planning-004-approval-checkpoint](planning-004-approval-checkpoint.md)
- [planning-checkbox-manifest](planning-checkbox-manifest.md)
- [planning-multi-platform](planning-multi-platform.md)
- [planning-task-descriptions](planning-task-descriptions.md)
