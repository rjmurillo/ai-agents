# ADR Debate Log: Notes After the Vendor Provenance Removal

## Summary

- **Rounds**: 1
- **Panel**: reduced (architect and critic). The change is prose only and touches no executable enforcement.
- **Outcome**: Consensus
- **Final Status**: ADR-097, ADR-101, ADR-109 and ADR-114 stay `accepted`. Each gains one dated amendment. No decision text changes.

## Context

PR #6260 (merge commit 44bc741e4) deleted the Vendor Provenance workflow and its validator. It also deleted every copy of the markdownlint safe config. Eight planning documents still described the gate or the config as current. The owner chose dated notes over rewriting decision records.

The change adds `## Amendment 2026-10-11` sections to ADR-101, ADR-109 and ADR-114. ADR-097 gets its amendment inline, in the Impact-table row that flagged the orphan, because a new section would push the file past the 500-line taste limit. It adds a `## Note 2026-10-11` section to the ADR-109 active plan, DESIGN-025, REQ-026 and TASK-034.

## Agent Positions

| Agent | Position | Key finding |
|-------|----------|-------------|
| architect | accept | Heading form matches ADR-054, ADR-057 and ADR-073. Frontmatter stays as is. Asked for the merge commit and for "scripts" instead of "executables". |
| critic | accept | Asked for the current `pull_request_target` count, the `_bootstrap.py` half of the ADR-097 orphan item, and a growth note in the four companion docs. Flagged ADR-100. |

## Resolutions

- **Merge commit cited**: every note now names 44bc741e4 next to PR #6260.
- **Script wording**: notes say "14 `.py` and `.sh` scripts". Of the 14, only one file has the executable mode bit set.
- **Growth from 13 to 14**: every note says the extra script came from separate work, not from PR #6260.
- **ADR-101 count**: the note names the three `pull_request_target` workflows left on main. Those are `label-pr.yml`, `enforcement-closure.yml` and `dependabot-approve-and-auto-merge.yml`.
- **ADR-097 orphan item**: the note settles the config half. It also says `_bootstrap.py` is now a canonical template.
- **Environment claim**: no seat queried GitHub settings. So the notes say only that PR #6260 did not delete the `vendor-provenance` environment, and that no workflow references it.
- **ADR-100 (P1, deferred with reason)**: ADR-100 lines 61 and 119 name the Validate Vendor Provenance check only as past evidence about #4846. They make no claim about the current tree, so ADR-100 gets no note.

## Decision

Both seats accept, and every finding is resolved or deferred above. The amendments record facts that changed after each decision. They do not change any decision.
