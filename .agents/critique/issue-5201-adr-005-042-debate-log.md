# ADR Debate Log: ADR-005 / ADR-042 Reciprocal Status (Issue #5201)

Part 1 of 2. Part 2 (`issue-5201-adr-028-031-056-debate-log.md`) covers
ADR-028, ADR-031, and ADR-056, reviewed in the same round; split into two
files only to fit each commit under the repository's 5-authored-file cap
(`.claude/rules/universal.md` MUST-6), not because the review ran separately.

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final Status**: ADR-005 `superseded` (by ADR-042); ADR-042 `accepted`
  (supersedes ADR-005)

## Context

`.claude/skills/adr-review/scripts/detect_adr_changes.py:_get_adr_status`
reads only a `status:` frontmatter line and defaults absent status to
`proposed`. ADR-005 (prose: "Superseded by ADR-042") and ADR-042 (prose:
"Accepted") both carried no frontmatter and parsed as `proposed`, contradicting
`AGENTS.md` and `.claude/rules/universal.md` SHOULD-3, which cite ADR-042 as
the binding scripting-language policy.

## Round 1: Six-Agent Review

All six seats (architect, critic, independent-thinker, security, analyst,
high-level-advisor) reviewed this pair as part of a combined five-ADR diff
(ADR-005, ADR-028, ADR-031, ADR-042, and, after Phase 3 revision, ADR-056).
Every seat treated ADR-005/ADR-042 as the mechanical half of the change:

- The frontmatter mirrors prose that already existed (superseded-by,
  accepted), so no seat found a judgment call here.
- Reciprocity confirmed: ADR-005 `superseded-by: ADR-042`, ADR-042
  `supersedes: [ADR-005]`.
- **security**: confirmed `status: accepted` on ADR-042 is backed by this
  debate's own evidence trail, satisfying ADR-073's "not a self-asserted
  approval" gate rather than circumventing it.
- **analyst**: traced the parser regex against ADR-005/042's frontmatter and
  confirmed `superseded` / `accepted` resolve correctly.
- **architect, critic, independent-thinker, high-level-advisor**: no findings
  against this pair; all findings and the one Block vote in Round 1 were
  scoped to ADR-028 (see Part 2).

### Agent Positions

| Agent | Position on ADR-005/ADR-042 |
|-------|------------------------------|
| architect | Accept (reciprocity and enum choice correct) |
| critic | Accept (no finding against this pair) |
| independent-thinker | Accept ("genuinely mechanical... mirroring that into YAML is a parser bug fix. Accept without reservation.") |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Accept |

### Next Steps

None. See Part 2 for the substantive debate and its resolution.
