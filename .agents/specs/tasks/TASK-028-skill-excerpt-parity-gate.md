---
type: task
id: TASK-028
title: ADR-108 amendment, spec artifacts, and index regeneration (A0)
status: in-progress
priority: P1
complexity: M
source: GH-5706
related:
  - REQ-024
  - DESIGN-023
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-028: ADR-108 amendment, spec artifacts, and index regeneration (A0)

## Done definition

- `.agents/architecture/ADR-108-template-owned-skill-files.md` exists, passes `uv run python scripts/validation/check_adr_lifecycle.py`, and has completed an `adr-review` round with the debate log at `.agents/critique/ADR-108-debate-log.md`; every P0 and P1 finding is resolved in the record or deferred with an issue.
- ADR-107 carries one Related Decisions line naming ADR-108 and the amended property; REQ-003-010 carries the amendment note.
- REQ-024, DESIGN-023, TASK-028, TASK-025, and TASK-027, the ontology fragment, and the plan are committed; `validate_spec_frontmatter.py` passes on the five spec files.
- `uv run python build/scripts/build_all.py` regenerated `.agents/architecture/README.md` (the ADR index) and `build_all.py --check` exits 0.
- No em dash or en dash in any file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.
- A pull request is open with `Refs #5706` (the record does not close the issue), the D1 decision quoted, and the ADR-108 status question put to the owner.

## Implementation notes

- ADR edits fire `adr-review`; run it before opening the PR and fold findings in the same branch.
- Atomic commits: ADR-108 + ADR-107 + REQ-003 (3 files); spec files (5); ontology + plan + README (3).

## Dependencies

None. Lands first.
