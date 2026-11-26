# ADR Debate Log: ADR-067 stale failure-message quotes

## Summary

- **Records**: ADR-067.
- **Rounds**: 2 of 10.
- **Outcome**: Consensus after round 2 fixes.
- **Final Status**: unchanged. ADR-067 stays accepted.
- **Panel**: reduced panel, architect and critic.
- **Why reduced**: the edit fixes two quotes. No Decision changes and no gate logic changes.
- **Base**: `67899d52d` (2026-11-25).
- **Claims ledger**: `.project-toolkit/critique/ADR-067-claims-ledger.md`.

## Defect

Two lines quoted a `pr_description.py` failure message with the advice "use a bullet/bold".
PR #6414 (`294ce6aec`) scoped every pattern to the change headings when one exists.
That advice is now wrong for any body with a change heading.
PR #7691 added the 2026-11-25 amendment but left both quotes.
Devin Review found this during PR #7691.

## What changed

1. Line 154 keeps the original quote and marks it superseded by the amendment.
   It then quotes the end of the live Check 1 message in `validate_pr_description`.
2. Line 195, Implementation Notes item 5, is marked superseded and kept as history.
   It states the live rule with its condition: a change heading must exist.
3. Frontmatter `date` moved to 2026-11-25.
4. Each edit stays one physical line. The file keeps 234 lines, so line citations hold.

## Round 1

Architect verdict: Accept-with-changes. Critic verdict: Revise.

### Accepted

- Both seats, P1: the first draft set `date` to 2026-11-26, a UTC date. It now reads 2026-11-25, the local date.
- Both seats, P1: line 195 dropped the "when the body has a change heading" condition. It now keeps the condition.
- Architect P2 and critic P1: line 154 lost the original quote, and its wording was muddled. It now quotes the original and states what changed.
- Architect P2: line 154 said the live message "reads", but it quotes one sentence. Round 2 settled the verb.

### Not changed here

- Architect P1 and P2: lines 71, 143, and 158 still say bold and bullet paths count as claims.
  That holds for a body with no change heading. With one, the amendment governs.
  They are outside the two quotes this change targets. The PR body records them.
- Critic P2: the amendment gives PR #6414 the date 2026-10-12. That is the commit date.
  GitHub records the merge at 2026-10-13 UTC. The amendment is not edited here.
- Critic P2: moving the history into the amendment section would shift no lines.
  It would also remove the inline marker a reader sees at each stale line. Kept inline.

## Round 2

Architect verdict: Accept. Critic verdict: Revise.

### Accepted

- Critic P1: round 1 changed "reads" to "ends". The bypass-label sentences follow the quote, so "ends" was false.
  Line 154 now says "includes".
- Critic P1: ledger row 5 claimed the same "ends". It now says "includes" and names what follows.
- Critic P1: this log claimed consensus before a re-review. Round 2 is now recorded.

The critic confirmed the rest: 234 lines, the date, the #6414 commit, and the scoping claim.
The only round 2 change is one verb, which the critic named as the fix.

**Verdict**: Consensus, no BLOCK.
