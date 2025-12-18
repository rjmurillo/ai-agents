# Roadmap Alignment Task

You are aligning a GitHub issue to the product roadmap to determine priority and milestone.

## Priority Definitions

Use these definitions to assign priority:

- `P0` - **Critical**: Blocks core functionality, security vulnerability, data loss risk
- `P1` - **Important**: Affects user experience significantly, high business value
- `P2` - **Normal**: Standard enhancement or bug fix, moderate impact
- `P3` - **Low**: Nice to have, future consideration, minor improvement

## Priority Decision Matrix

| Impact | Urgency | Priority |
|--------|---------|----------|
| High (core functionality) | Immediate need | P0 |
| High | Can wait | P1 |
| Medium | Immediate need | P1 |
| Medium | Can wait | P2 |
| Low | Any | P3 |

## Milestone Assignment Guidelines

Assign milestone based on:

1. **Current release** - If issue is P0 or blocks current work
2. **Next release** - If issue is P1 and aligns with planned features
3. **Backlog** - If issue is P2/P3 or doesn't fit current roadmap

Common milestones:

- `v1.0` - Initial release (likely complete)
- `v1.1` - Next minor release
- `v1.2` - Future minor release
- `v2.0` - Major release with breaking changes

## Output Format

Respond with ONLY valid JSON (no markdown, no explanation):

```json
{
  "milestone": "v1.1",
  "priority": "P1",
  "epic_alignment": "EPIC-001-feature-name",
  "confidence": 0.75,
  "reasoning": "Aligns with planned v1.1 consolidation work"
}
```

## Rules

1. Always assign a priority (P0-P3)
2. Only assign milestone if confident (otherwise use empty string)
3. Only assign epic_alignment if clearly matches a roadmap epic
4. Set confidence between 0.0 and 1.0
5. Keep reasoning brief (one sentence)
6. If roadmap context is missing, default to P2 with no milestone
