---
id: ADR-095
status: rejected
date: 2026-08-15
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-095: Scoped re-review runs only the axes that flagged (rejected)

## Status

Rejected. Recorded so the proposal is findable and does not return.

Drafted as ADR-094 and renumbered on merge: `ADR-094` is taken on `main` by
`.agents/architecture/ADR-094-govern-copilot-cli-compatibility.md`, accepted in
PR #5024, which also owns `.agents/critique/ADR-094-debate-log.md`. This
record's debate log is `.agents/critique/ADR-095-debate-log.md`.

## What was proposed

A `/review --axes=<comma-separated-list>` flag. A scoped run would execute the
Stage-1 `spec-compliance` gate plus only the named Stage-2 and chained axes,
mark every other axis `SKIPPED`, and write no SHA-bound `Reviewed-By` marker.
Full runs would stay the default and remain the only thing that satisfies
`/ship`. The intended workflow was one full run to find the flagged axes, then
scoped fix rounds re-running only those, then a final full run to earn the
marker.

The target was the re-review multiplier: `/ship` requires a marker whose parent
is HEAD's parent, so every fix commit invalidates it.

## Why it was rejected

Five findings from the debate. Each is reproducible from the commands given.

1. **The motivating evidence predates the mechanism.** `/review` became a skill
   in `c3ddc571a` on 2026-05-24 and the SHA-bound marker landed in `16c960418`
   on 2026-06-04. The three incidents the draft cited as its cost evidence
   merged before both: PR #1887 on 2026-05-05, PRs #1965 and #1979 on
   2026-05-10. None of those rounds contained a marker-forced full re-review,
   because the marker did not exist. The draft's `18 x 15 = 270` figure sat
   under a heading reading "What the cost is, measured" and was a projection
   onto a period that lacked the thing being measured. The ADR's motivating
   evidence does not support it.

2. **The signal figure was spliced from two rollups of one source.**
   `.agents/analysis/009-phase1-agent-comment-baseline.md:163` reports 182
   comments over 120 runs at a 52% aggregate signal ratio.  `:178` reports 24%
   over a different 173-unit first-pass rollup. The draft paired the 182 count
   from the first with the 24% ratio from the second, taking the lower of two
   figures the same document reports.

3. **Every proposed validator change targeted a mirror.** The draft named
   `.claude/skills/review/scripts/validate_review_marker.py`. The canonical file
   is `scripts/validation/validate_review_marker.py`, registered as a sync pair
   in `scripts/sync_plugin_lib.py` and pinned by
   `tests/validation/test_review_marker_packaging.py`. Editing the mirror fails
   the packaging test and is overwritten on the next sync. The draft also
   omitted the two push-blocking consumers of that validator,
   `scripts/validation/git_hook_policy.py` and
   `scripts/validation/checks_coverage.py`, so it priced a new exit-1 condition
   as touching `/ship` alone when it lands on every contributor's pre-push hook.

4. **The no-marker safety property did not hold as claimed.** `/ship` in
   contributor mode skips the marker validator entirely and accepts a logged
   `/review` result as the attestation. A scoped run's output is exactly that
   shape, so the marker prohibition protected nothing on that path. The draft
   asserted `ship.md` needed no change. Separately, no marker-writer script
   exists: the marker is written by prose instructing
   `git commit --allow-empty --trailer`, so "a scoped run MUST NOT write a
   marker" was an instruction to the same agent that chose the scoped mode to
   save work, not a structural guarantee.

5. **The scoping key was structurally wrong.** The draft scoped round N+1 to the
   axes that flagged in round N. Round N+1's defects live in round N's fix, in
   code that did not exist when the flagged set was computed. Scoping by past
   findings selects against exactly the defects a fix introduces.

## The counter-evidence that made finding 5 concrete

On PR #5059 the full review fan-out caught a defect nothing else did. A
`pr-autofix` round-cap gate was wired behind
`TIER=$(echo "$LIVE" | jq -r '.Data.tier // "UNKNOWN"')`, reading a `Data.tier`
field that `check_pr_live_state.py` never emits. The guard never opened, so the
gate never executed once. Twenty-six unit tests passed throughout, because they
exercised the script in isolation and never the wiring. Four axes (Architect,
Reliability, Agent Safety, Spec Coverage) converged on it independently.

The defect was introduced by the fix for an earlier defect in the same PR, and
the four axes that caught it are not axes a caller correcting a `jq` field name
would have named. A scoped re-review keyed on previously-flagged axes would have
returned clean for four rounds while the silent no-op accumulated. That is
finding 5 as a measured instance rather than an argument.

## What addresses the real need instead

PR #5010 merged to `main` at `458028d2b` as "feat(review): select axes by change
risk". `/review` now evaluates the canonical axes by change risk rather than by
blind fan-out: `spec-compliance` and `analyst` always run, callers can pin
additional always-on axes, and the remaining axes are selected from verified
changed paths and diff effects using each axis prompt's own applicability
guidance. A skipped axis records its selection reason and is not treated as
`PASS`. An explicit deep review, or a change that cannot be classified with
confidence, runs the full canonical set, and `/review` remains a strict superset
of CI in that mode only.

That solves the same cost problem on a sound key. It selects on the properties
of the change in front of it, not on what a previous round happened to flag, so
it does not have finding 5. It keeps an always-on core rather than allowing the
caller to scope everything away, and it distinguishes a skip from a pass rather
than folding unevaluated axes into a green verdict.

## Debate

`.agents/critique/ADR-095-debate-log.md`. Six roles, one round, no consensus:
two Block, three Accept-with-changes, one Disagree-and-Commit. That log also
records what survived scrutiny, which is worth keeping: all six roles held that
a run which skipped axes must not refresh the ship marker, because an axis that
did not run has no verdict.

One finding in that log is live and independent of this rejection. Fourteen
`Reviewed-By: /review@` marker commits exist across all refs; three name the
full 15-axis set and eleven name a subset, four of those naming a `code-review`
axis for which no `references/code-review.md` exists.
`validate_review_marker.py` parses the axis list and never checks membership or
completeness, so a subset marker passes today. That is a gap in the existing
gate, not in this rejected proposal, and it wants its own issue.

## References

- `.agents/critique/ADR-095-debate-log.md`. The debate.
- PR #5010, `458028d2b`. Risk-based axis selection, the approach that shipped.
- `.agents/analysis/009-phase1-agent-comment-baseline.md`. The signal baseline finding 2 refers to.
- Issue #1938. The SHA-bound marker design.
- Issue #5090. The inert-hooks incident that let the draft skip its debate gate.
