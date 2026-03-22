# ADR-051: Synthesis Panel Frontmatter Standard

## Status

Accepted

## Author

Session 2026-03-07-session-01

## Date

2026-03-07

## Context

DESIGN-REVIEW documents (architect synthesis panels) contain critical metadata embedded in prose format, preventing automated enforcement of blocking verdicts. PR #908 (2026-01-14) was created and merged despite a P1 BLOCKING architect review, demonstrating the enforcement gap.

Current state:
- DESIGN-REVIEW verdicts (`APPROVED`, `NEEDS_CHANGES`, `BLOCKED`) are prose-only
- No machine-readable structure for review status, priority, or blocking status
- Architect reviews are advisory; no CI gate prevents PR merge despite blocking verdict
- Inconsistent document structure across existing DESIGN-REVIEW files
- Review automation requires unreliable regex parsing of prose

This violates the project's commitment to automated quality gates (ADR-010) and creates a critical gap between architect authority and enforcement capability.

## Decision

**All DESIGN-REVIEW documents MUST include YAML frontmatter with structured metadata.**

### Frontmatter Schema

```yaml
---
status: APPROVED | NEEDS_CHANGES | BLOCKED
priority: P0 | P1 | P2
reviewer: architect
date: YYYY-MM-DD
pr-branch: branch-name          # optional
scope: Brief scope description  # optional
---
```

### Field Semantics

| Field | Type | Values | Purpose |
|-------|------|--------|---------|
| `status` | enum | `APPROVED`, `NEEDS_CHANGES`, `BLOCKED` | Review outcome |
| `priority` | enum | `P0`, `P1`, `P2` | Issue severity if not approved |
| `reviewer` | string | agent name | Identity of reviewing agent |
| `date` | date | `YYYY-MM-DD` | Review date (ISO 8601) |
| `pr-branch` | string | branch name (pattern: `[a-zA-Z0-9/_.-]+`) | Git branch under review (optional) |
| `scope` | string | max 100 chars, alphanumeric/spaces/hyphens | Brief description of review scope (optional) |

### CI Gate Logic

**For each DESIGN-REVIEW file in PR:**

0. If file has no frontmatter, skip (advisory warning only)
1. Parse frontmatter YAML
2. If (`status: NEEDS_CHANGES` OR `status: BLOCKED`) AND (`priority: P0` OR `priority: P1`):
   - **Block merge** with reason: "Blocking architect review requires changes"
3. If `status: APPROVED`:
   - **Allow merge** (review passed)
4. Otherwise:
   - **Allow merge** (advisory review)

**Result:** No PR can merge to main if it contains DESIGN-REVIEW files with NEEDS_CHANGES or BLOCKED status at P0/P1 priority.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Status Quo** (prose only) | Simple; no syntax overhead | Cannot automate; PR #908 (2026-01-14) proves enforcement fails | Unacceptable: violates ADR-010 quality gate principle |
| **JSON sidecar files** (DESIGN-REVIEW.json) | Separates concerns | Splits context; maintenance burden; harder to read | Would create parallel document problem |
| **Markdown tables** | Easier to read in markdown | Brittle parsing; not standard; hard to validate | YAML is markdown-ecosystem standard |
| **Plain-text header** (First line: "VERDICT: BLOCKED") | Minimal syntax | No structure; easy to miss; hard to parse | Not machine-friendly |
| **Frontmatter + schema validation** (proposed) | Structured; automated; standard | Slight syntax overhead on authors | Solves PR #908 (2026-01-14); aligns with ADR-040; enables automation |

### Trade-offs

**Syntax Overhead vs Enforcement Power:**

- Frontmatter adds 7 lines per document (~5% overhead)
- Enables complete automation of blocking reviews
- Decision: Overhead is negligible compared to enforcement value

**Migration Effort vs Long-term Clarity:**

- New requirement applies to all new DESIGN-REVIEW files
- Existing documents can migrate gradually (optional)
- Decision: New files required; gradual migration acceptable

## Consequences

### Positive

- **Automated enforcement**: Blocking reviews now prevent merge via CI gate
- **Machine-readable status**: Tools can parse review outcomes reliably
- **PR #908 (2026-01-14) prevention**: No PR can merge despite blocking architect review
- **Consistent structure**: All DESIGN-REVIEW documents follow same format
- **Quality gate alignment**: Fulfills ADR-010 principle for automated gates
- **Backwards compatible**: YAML frontmatter is ignored by markdown renderers; documents remain readable
- **Reuses patterns**: YAML frontmatter already established in ADR-040 (skill files) and session protocol

### Negative

- **Syntax burden**: Authors must remember 4 required frontmatter fields
- **Migration work**: Existing DESIGN-REVIEW files lack frontmatter (optional but recommended)
- **Script maintenance**: New validation and CI gate scripts to maintain
- **Requires tooling**: Python validation script and CI gate workflow needed

### Neutral

- **Document body unchanged**: Existing DESIGN-REVIEW body structure remains compatible
- **No breaking changes**: P2 advisory reviews unaffected
- **Gradual adoption**: Old documents continue working; focus on new documents first

## Reversibility Assessment

**Rollback capability**: Remove the CI gate workflow to disable enforcement. Frontmatter in existing files is inert without the gate.

**Escape hatch**: A `gate-override` label on the PR bypasses the frontmatter check for emergency merges. Requires CODEOWNERS approval.

**Migration risk**: Existing DESIGN-REVIEW files without frontmatter are skipped by the gate (no frontmatter = no blocking signal). Only files with frontmatter are evaluated.

## Implementation Notes

### Phase 1: Schema & Template Definition

1. Create `.agents/architecture/DESIGN-REVIEW-template.md` with frontmatter and body sections
2. Document ADR-051 with full specification
3. Update architect agent prompt to reference template

### Phase 2: Validation Script

1. Create `scripts/validation/validate_design_review.py` following ADR-042 (Python Migration Strategy) pattern
2. Validate required fields: `status`, `priority`, `reviewer`, `date`
3. Validate field values against allowed enums
4. Validate date format (YYYY-MM-DD)
5. Integrate with existing validation pipeline
6. Create pytest tests in `tests/test_validate_design_review.py`

### Phase 3: CI Gate Workflow

1. Create `.github/workflows/architect-review-gate.yml` following ADR-006 (thin workflows) pattern
2. Trigger on PR to main branch
3. Detect DESIGN-REVIEW files in diff
4. Parse frontmatter of review files
5. Block merge if (`status: NEEDS_CHANGES` OR `status: BLOCKED`) AND (`priority: P0` OR `priority: P1`)
6. Post status check to PR

### Phase 4: Architect Agent Update

1. Update `.claude/agents/` to require frontmatter
2. Add frontmatter example (copy-paste ready)
3. Add checklist: "Verify all required frontmatter fields are present"

### Phase 5: Migration (Optional, Non-Blocking)

1. Create migration script to add frontmatter to existing DESIGN-REVIEW files
2. Not required; can be done ad-hoc when documents are reviewed again

## Convergence with Related ADRs

- **ADR-042**: Python Migration Strategy → Validation script in Python
- **ADR-006**: Thin Workflows → CI workflow delegates to Python module
- **ADR-010**: Quality Gates Evaluator Optimizer → Frontmatter enables automated gate
- **ADR-040**: Skill Frontmatter Standardization → Reuses YAML frontmatter pattern
- **ADR-043**: Scoped Tool Execution → CI gate applies scoped checking (only DESIGN-REVIEW files)

**Critical Path**: Schema → Template → Validation → CI Gate → Agent Update
**Blocking dependencies**: None (all phases can proceed in parallel after schema definition)

## Related Decisions

- **ADR-010**: Quality Gates Evaluator Optimizer (establishes gate automation principles)
- **ADR-040**: Skill Frontmatter Standardization (established YAML frontmatter pattern for skills)
- **ADR-042**: Python Migration Strategy (validation script language)
- **ADR-006**: Thin Workflows (CI workflow architecture)

## Related Issues

- **Issue #937 (2026-01-15)**: Create DESIGN-REVIEW template (depends on this ADR)
- **Issue #934 (2026-01-15)**: Pre-PR validation parsing (depends on this ADR)
- **Issue #942 (2026-01-15)**: CI gate workflow (depends on this ADR)
- **Issue #947 (2026-01-15)**: Architect agent prompt update (depends on this ADR)
- **PR #908 (2026-01-14)**: Architect BLOCKED but PR created anyway (incident that motivated this ADR)

## References

- `.agents/architecture/ADR-040-skill-frontmatter-standardization.md` (frontmatter pattern reference)
- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (incident analysis)
- `.agents/SESSION-PROTOCOL.md` (YAML frontmatter precedent in session logs)
- `scripts/validation/` (validation pattern reference)
- `.github/workflows/ai-session-protocol.yml` (CI workflow pattern reference)

---

*Created: 2026-03-07*
*GitHub Issue: #946 (2026-01-15)*
*Complexity: Medium (schema definition + scripting + CI)*
*Priority: P1 (blocks automated enforcement of architect reviews)*
