---
type: design
id: DESIGN-021
title: Control-plane disposition ledger for v0.7.0
status: draft
priority: P0
related:
  - REQ-022
created: 2026-09-11
updated: 2026-09-11
author: spec-generator
tags:
  - control-plane
  - disposition
---

# DESIGN-021: Control-plane disposition ledger for v0.7.0

## Requirements Addressed

- REQ-022: Control-plane disposition ledger for v0.7.0

## Design Overview

`.agents/metrics/control-plane-dispositions-v0.7.0.md` is a single
hand-authored markdown document, one row per candidate, in a fixed table
shape. No new code ships with this design; the "design" is the row schema,
the row-writing procedure, and the mechanical completeness check that
verifies every KEEP row carries its five required fields before the
document is committed.

## Component Architecture

```text
control-plane-dispositions-v0.7.0.md
├── Header (pinned baseline SHA it cites, epic link, date)
├── Table: | Candidate | Class | Owner | Consumers | Evidence |
├── Per-KEEP-row expansion (five fields, as a sub-list under the row or a
│   linked ## section per candidate -- see Open Question OQ1 resolution
│   deferred to TASK-029)
└── Footer: candidates whose resolution mechanism is owned elsewhere,
    classified as one of the epic's four dispositions with a one-line
    reason naming the owning mechanism
```

A small check script is optional but not required: AC-02's "all five fields
non-empty" check can be a one-off `grep`/manual review at PR time rather
than a new validator, because writing a validator for an eight-to-a-dozen
row document is disproportionate tooling (YAGNI) and the epic's Abort-if
clause 3 discourages new governance mechanisms. TASK-029's Implementation
Notes record this as a deliberate choice, not an oversight.

## Technology Decisions

| Decision | Choice | O5 source | Rationale |
|---|---|---|---|
| Format | Markdown table plus per-KEEP-row detail | DR2 | Matches the epic's own Disposition contract prose shape; no new schema |
| Completeness check | Manual/PR-review, not a new script | Abort-if clause 3 | A validator for a dozen rows is a new mechanism disproportionate to the problem |
| Evidence citation style | Concrete artifact only (SHA/path:line/test name/ADR id/memory path) | AC-04 | Matches this repository's `universal.md` MUST-4 evidence-citation norm already in force for red-check claims |

## Decision-rule Traceability

| Decision rule | O5 source | Where enforced |
|---|---|---|
| DR2 (KEEP completeness) | ontology fragment | Row-writing procedure requires all five fields before a row is marked KEEP; PR-review check |
| DR3 (already-fixed is KEEP) | ontology fragment | The duplicate-gate row (REQ-022 AC-03) is the worked example this design ships |

## Security Considerations

None beyond REQ-022's Security section (no new attack surface; hand-authored
markdown, no executable content, no new write path).

## Testing Strategy

No automated tests (this is a markdown document, not code). Verification is
the mechanical completeness check (REQ-022 AC-02) performed at PR-review
time: every KEEP row's five fields present; every epic-named candidate has
exactly one row (AC-01); no candidate silently omitted (cross-check against
the epic body's Execution section list). `uv run python
scripts/validation/pre_pr.py` still runs as the standard pre-PR gate (it
will not specifically validate ledger content, but it validates the PR as a
whole per repository convention).

## Open Questions

- Row-detail layout (inline sub-list vs. linked per-candidate section) is
  resolved at TASK-029 time based on how many KEEP rows actually need the
  five-field expansion; if only one or two rows are KEEP (as expected at
  this cohort's scale), an inline sub-list under the table row is simplest
  and avoids a second document structure.
