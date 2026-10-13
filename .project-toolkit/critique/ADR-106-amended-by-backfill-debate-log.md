# ADR Debate Log: Amended-by Backfill for ADR-038, 063, 064, 070, 086

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final status**: accepted. Five records gain a footer; no decision text changes.
- **Panel**: reduced, architect and critic.
- **Issue**: #5675. PR #5656 (ADR-106) and PR #3643 (ADR-089) amended these
  records by reference and left no pointer in them.

## Change under review

Staged records: ADR-038, ADR-063, ADR-064, ADR-070, ADR-086.

- ADR-038 and ADR-063 gain an `**Amended by**:` footer naming ADR-089 and
  ADR-106.
- ADR-064, ADR-070 and ADR-086 gain the same footer naming ADR-106.
- `adr-best-practices.md` (adr-generator references) states the convention:
  amending by reference requires the footer in the amended record.

The footer shape is the one ADR-005 carries at its end. No frontmatter field
changes. No `date` field changes, because the decision text did not change.

## Panel basis

AGENTS.md picks the full panel only when the change touches executable
enforcement or a rule other gates read. This edit touches neither.

- `build/scripts/generate_adr_index.py` reads the frontmatter, the title, the
  `## Status` section and the first paragraph of the Decision section
  (`_decision_summary`, `_blocking_condition`). A footer at the end of a file is
  outside all of them. `build_all.py` regenerated the index after the edit and
  wrote no change to `.project-toolkit/architecture/README.md`.
- `scripts/validation/check_adr_exception_markers.py` scans workflow files for
  `# ADR-NNN Exception:` markers and reads ADR frontmatter only. It does not
  parse ADR bodies.
- The convention text lands in a skill reference, which no gate parses.

The reduced panel applies.

Independence limit: the architect and critic passes ran in separate steps by the
authoring agent. They are not independent reviewers. The checks that do not
depend on the author are the unchanged generated index, the `pre_pr.py` run on
the PR branch, and owner review of the PR.

## Evidence verified

- `git grep "ADR-089\|ADR-106"` across ADR-038, 063, 064, 070 and 086 on
  `origin/main` before this change: 0 hits. After: one footer each.
- ADR-106 Decision item 7 lists exactly these five records as amended by
  reference. ADR-089 lines 293 to 294 name ADR-038 and ADR-063.
- ADR-089 landed in PR #3643 on 2026-07-28. ADR-106 landed in PR #5656 on
  2026-09-09. The footer dates and PR numbers come from `git log`.
- Six records carry the footer today: ADR-005, 006, 017, 035, 041, 054. The new
  footers follow ADR-005 and ADR-017 (a list under the label).

## Key Issues Addressed

- Architect: all five footers go at the end of the file, after the last
  section, so a reader finds the pointer in the same place in every record.
  ADR-063 and ADR-070 already end in an "Amendment 2026-07-27" section; the
  footer follows it.
- Architect: the convention text says the amending ADR names every amended
  record and each named record gets its footer. Without that the footer is
  optional in practice.
- Critic: each entry links the amending ADR by relative path, as ADR-005 does
  for ADR-042. A bare id is a second search.
- Critic: "required" in a skill reference binds only agents that load it. A
  reciprocity validator is the enforcement step. It is a separate decision
  (issue #5675 item 4) and is not made here.

## Agent Positions

| Agent | Position |
| --- | --- |
| architect | Accept. The footer follows the existing convention and changes no decision text. |
| critic | Accept. Links are relative and the enforcement gap is recorded as out of scope. No open P0 or P1. |

## Out of scope, recorded

- Index rendering of amendments needs a `generate_adr_index.py` change. It is a
  separate decision.
- A validator for amend-by-reference clauses without a reciprocal footer is a
  separate decision.
- Noticed: ADR-038, ADR-070 and ADR-089 carry `status: proposed` with
  `implemented: true`. Outside this change.

## Next Steps

Owner review of the PR. No further rounds.
