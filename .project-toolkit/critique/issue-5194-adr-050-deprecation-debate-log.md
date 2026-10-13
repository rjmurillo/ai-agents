# ADR Debate Log: ADR-050 Deprecation and ADR-073 Dead Row (Issue #5194)

## Summary

- **Rounds**: 1
- **Panel**: reduced (architect and critic), per the AGENTS.md trigger. The ADR
  edits are prose and metadata only. The executable gate (`cited-paths-exist`)
  lives in `scripts/validation/check_adr_lifecycle.py`, not in either ADR.
- **Outcome**: Consensus after one revision
- **Final Status**: ADR-050 `deprecated`; ADR-073 stays `accepted`

## Context

ADR-050 read `status: accepted` while both halves of its decision were gone.
Commit `ba541c21` (PR #5179, 2026-08-20) deleted `scripts/sync_adr_protocol.py`
and `.agents/SESSION-PROTOCOL.md`. The repo owner delegated the lifecycle choice
on issue #5194, whose comment recommends option A (`status: deprecated`).

The change under review:

- ADR-050: `status: deprecated`, a new `## Status` section with rationale.
- ADR-073: the Impact on Dependent Components row for the deleted script is removed.

Both seats were given the diff and the facts above, not this author's reasoning.
Each ran as a separate read-only Claude session and verified claims with
`git show`, `git log`, `ls`, and `git grep`.

## Round 1: Reduced Panel

### Agent Positions

| Agent | Position | Findings |
|-------|----------|----------|
| architect | Needs revision | P1: "(issue #5138)" is wrong. P1: debate log owed. P2: ADR-073 date bump. |
| critic | Accept | P2: ADR-069 line 167 is stale. P2: ADR-073 date bump is optional. P2: debate log owed. |

### Claims Verified

- Commit `ba541c21` deleted both files on 2026-08-20 and is PR #5179. VERIFIED.
- The removal was deliberate: the PR body says the protocol document is retired. VERIFIED.
- `deprecated` is a valid enum value, and ADR-039 sets precedent for it with no
  successor edge. VERIFIED.
- A `## Status` section is allowed when it carries more than the enum word.
  VERIFIED, and `check_adr_lifecycle.py` reports `prose-frontmatter-agree` at 0.
- "Issue #5138" in the ADR-050 text. REFUTED. Issue 5138 is an unrelated
  dependency update PR. Commit `ba541c21` says "Refs #5138", which is a
  mis-reference in that commit.

### Major Changes Made

- Dropped "(issue #5138)" from the ADR-050 Status text. It now cites only PR #5179.
- Added one sentence stating the frontmatter `date` is the deprecation date and
  the `## Date` section stays the original decision date (the ADR-039 pattern).
- Reverted the ADR-073 `date` bump. The row removal is cleanup, not a content
  change, and commit `103bf2a69` amended ADR-073 without bumping `date`.
- Added this debate log.

### Disposition of Remaining Findings

- ADR-069 line 167 says ADR-050 "governs how this ADR is propagated". That is
  stale. Editing ADR-069 is outside this issue, so it is flagged in the PR body.
- ADR-050 References still list the deleted protocol. The Status section says
  the Decision text is kept as written, so the notice covers it.

### Next Steps

None. Consensus: both seats accept the revised text.
