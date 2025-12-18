# Roadmap Alignment Task

You are aligning a GitHub issue to the product roadmap to determine priority, milestone, and whether a full PRD is warranted.

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

## PRD Escalation Criteria

Recommend full PRD generation (`escalate_to_prd: true`) when ANY of these apply:

| Criterion | Description |
|-----------|-------------|
| **Feature Request** | New functionality, not a bug fix or documentation update |
| **Research Required** | Implementation path is unclear, requires investigation |
| **External Dependency** | Blocked on third-party documentation, APIs, or decisions |
| **Multi-Phase Work** | Cannot be completed in a single PR or session |
| **Architectural Impact** | Affects system design, patterns, or cross-cutting concerns |
| **Customer-Facing** | Issue filed by or impacts external users/stakeholders |

When `escalate_to_prd: true`, the output will be routed to `issue-prd-generation.md` for full analysis.

### PRD Complexity Scoring

Calculate complexity to help prioritize PRD depth:

| Factor | Low (1) | Medium (2) | High (3) |
|--------|---------|------------|----------|
| Scope | Single file/function | Multiple files | System-wide |
| Dependencies | None | Internal only | External/blocking |
| Uncertainty | Clear path | Some unknowns | Significant research |
| Stakeholders | Internal only | Team-wide | Customer-facing |

- **Score 4-6**: Standard PRD (brief analysis, clear requirements)
- **Score 7-9**: Detailed PRD (research section, blocking questions)
- **Score 10-12**: Comprehensive PRD (phased implementation, risk analysis)

## Output Format

Respond with ONLY valid JSON (no markdown, no explanation):

```json
{
  "milestone": "v1.1",
  "priority": "P1",
  "epic_alignment": "EPIC-001-feature-name",
  "confidence": 0.75,
  "reasoning": "Aligns with planned v1.1 consolidation work",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "research_required"],
  "complexity_score": 8
}
```

## Rules

1. Always assign a priority (P0-P3)
2. Only assign milestone if confident (otherwise use empty string)
3. Only assign epic_alignment if clearly matches a roadmap epic
4. Set confidence between 0.0 and 1.0
5. Keep reasoning brief (one sentence)
6. If roadmap context is missing, default to P2 with no milestone
7. Set `escalate_to_prd` to true when ANY escalation criterion applies
8. List applicable criteria in `escalation_criteria` array (use snake_case keys)
9. Calculate `complexity_score` (4-12) for escalated issues only
