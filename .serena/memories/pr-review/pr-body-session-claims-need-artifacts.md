# Skill: A PR body's session-history claims are checked against artifacts (HIGH, correction)

## Statement

When a PR body says "N times this session" or "I re-derived X", a reviewer
verifies that against `.agents/sessions/*.json` and `.agents/retrospective/*.md`.
Your working recollection of the session is not admissible, because the reviewer
cannot open it. An event you did not write down when it happened cannot be cited
as evidence later.

If you intend to cite an event, append it to the session log `workLog` when it
occurs, not when you need it.

## Evidence

2026-08-05, PR #4669. The body claimed five re-derivations of facts that
memories already held: the PR-checks rollup quirk, the `ls-remote` ordering gap,
the memory-index direction, the merge-invalidation coupling, and `gh auth
status` reporting a rate limit as an invalid token.

An adversarial review (grok-4.5) checked each claim against the branch:

> Only two of five are corroborated in session/retro artifacts as this-session
> re-derivations of an already-held memory

The two that held were `ls-remote` (retro line 138, "I had a memory saying
exactly this and did not consult it") and the memory-index direction (retro line
147, "Third retrieval failure of the same shape in one session"). The other
three had memories on disk but no record of a this-session re-derivation.
Whether they happened is beside the point. Unrecorded, they could not be cited.

The body was corrected down to the three the retrospective corroborates.

## What is admissible

| Claim | Verified against |
| --- | --- |
| "N times this session" | `.agents/retrospective/*.md` tables, session `workLog` |
| "this file changed" | the branch diff |
| "the memory already said X" | the memory file, cited with a line number |
| "the fix landed at `<sha>`" | `git show <sha>` |
| "I reasoned my way to X" | nothing. Drop it, or log it first |

## Trap: chronology that undercuts the claim

The same review flagged a second shape. The body cited an instance that occurred
*after* the fix commit as proof that the gap the fix closes is still open. Those
cannot both hold on their face: if the rule was already committed, a later miss
reads as the rule failing rather than as the gap being live. The unstated
premise was that the session's loaded instruction snapshot still held the
pre-change text, which is harness behavior no repository artifact records.

A claim resting on an unstated premise about harness behavior does not belong in
a PR body. Drop it rather than defend it there.

## Related

- `.claude/rules/knowledge-persistence.md`, the evidence bar for absence claims
- `.serena/memories/ci/ci-validate-pr-is-many-gates-only-some-read-the-body.md`,
  for which gates read the body at all
