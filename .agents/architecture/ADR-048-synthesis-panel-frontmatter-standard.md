# ADR-048: Synthesis Panel Frontmatter Standard

## Status

Proposed

## Date

2026-02-19

## Context

Architect blocking reviews are advisory because the markdown format prevents automated enforcement. In PR #908, a P1 BLOCKING review was ignored and the PR merged anyway. The root cause: DESIGN-REVIEW documents use unstructured markdown headers for metadata (status, priority, blocking). No tooling can reliably parse prose-based verdicts.

Current DESIGN-REVIEW documents embed metadata as bold markdown text:

```markdown
**Status**: NEEDS_CHANGES
**Priority**: P1 (Blocking)
**Verdict**: NEEDS_CHANGES
```

This format varies across documents. Some use `**Verdict**`, others use `**Status**`. Priority formatting is inconsistent (`P1`, `P1 (Blocking)`, `P1 - Blocking`). There is no machine-readable way to determine if a review blocks a PR.

## Decision

All DESIGN-REVIEW documents MUST include YAML frontmatter with structured metadata. The frontmatter schema is:

```yaml
---
status: APPROVED | NEEDS_CHANGES | NEEDS_ADR
priority: P0 | P1 | P2
blocking: true | false
reviewer: architect | security | qa | analyst
date: YYYY-MM-DD
pr: <number>
issue: <number>
---
```

Required fields: `status`, `blocking`, `reviewer`, `date`.
Optional fields: `priority`, `pr`, `issue`.

A template file at `.agents/architecture/DESIGN-REVIEW-template.md` defines the standard structure.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (prose only) | No migration effort | Cannot automate enforcement | Blocking reviews ignored in practice |
| JSON sidecar files | Strong schema validation | Splits context from review, maintenance burden | Two files per review is error-prone |
| Markdown tables | Familiar format | Harder to parse reliably than YAML | Regex parsing is fragile for tables |
| Structured markdown headers | Simple | Still requires custom parsing | YAML frontmatter is an ecosystem standard |

### Trade-offs

- YAML frontmatter adds syntax overhead to DESIGN-REVIEW documents. This is acceptable because the frontmatter is small (6-8 lines) and ignored by markdown renderers.
- Existing documents are not required to migrate. New documents MUST use the frontmatter. Migration is optional and can happen incrementally.

## Consequences

### Positive

- Pre-PR validation can parse `blocking: true` and reject PRs with unresolved blocking reviews
- CI gates can enforce architect approval before merge
- Status is unambiguous: `APPROVED` vs `NEEDS_CHANGES` vs `NEEDS_ADR`
- YAML frontmatter is a standard in the markdown ecosystem (Jekyll, Hugo, Astro)

### Negative

- Architect agent prompt must be updated to produce frontmatter
- Existing DESIGN-REVIEW documents lack frontmatter (optional migration)

### Neutral

- Markdown renderers ignore YAML frontmatter, so document readability is unchanged
- The `blocking` field is explicit rather than inferred from `priority`

## Implementation Notes

### Template Location

`.agents/architecture/DESIGN-REVIEW-template.md` provides the standard structure. The architect agent uses this template when creating new reviews.

### Validation

Pre-PR validation (Issue #934) should:

1. Find all `DESIGN-REVIEW-*.md` files in `.agents/architecture/`
2. Parse YAML frontmatter using a standard parser
3. Check for `blocking: true` with `status: NEEDS_CHANGES`
4. Block PR creation if any blocking review is unresolved

### CI Gate

A CI workflow (Issue #942) should:

1. Run on PR events
2. Parse DESIGN-REVIEW frontmatter for the PR
3. Fail the check if `blocking: true` and `status != APPROVED`

### Field Semantics

| Field | Values | Meaning |
|-------|--------|---------|
| `status` | `APPROVED` | Review passes, no changes needed |
| `status` | `NEEDS_CHANGES` | Review fails, changes required before merge |
| `status` | `NEEDS_ADR` | Architectural decision needed before proceeding |
| `blocking` | `true` | PR MUST NOT merge until status is APPROVED |
| `blocking` | `false` | Advisory review, PR may merge |
| `priority` | `P0` | Critical, blocks core functionality |
| `priority` | `P1` | Important, affects user experience |
| `priority` | `P2` | Enhancement, low urgency |

## Related Decisions

- ADR-040: Skill Frontmatter Standardization (precedent for YAML frontmatter in this project)
- ADR-047: Plugin-Mode Hook Behavior (hooks that could enforce frontmatter validation)

## References

- Issue #937 (template creation)
- Issue #934 (validation parsing)
- Issue #942 (CI gate)
- PR #908 (architect BLOCKED review but PR merged)
- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`

---

*Template Version: 1.0*
*Created: 2026-02-19*
*GitHub Issue: #946*
