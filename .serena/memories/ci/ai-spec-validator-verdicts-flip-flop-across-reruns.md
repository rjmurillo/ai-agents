# `Validate Spec Coverage` verdicts differed across reruns on one PR's commits

## Observation

On two PRs (#5350, #5356), successive runs of the `Validate Spec Coverage`
check reported different top-line results for a gap that never changed: an
unverified live-CLI probe on #5350, a prompt-only versus enforced-control
distinction on #5356. Measured 2026-08-27.

## What this evidence does and does not show

It does not show that the validator is nondeterministic, and this file used to
say that it did. Two limits on the observation:

1. The runs were on adjacent commits, not on one commit. #5350 carried six
   commits, and its final head `b301b39e2` has exactly one `Validate Spec
   Coverage` check-run. So the validator's inputs changed between the runs
   whose verdicts differed, which is enough on its own to explain them.
2. The recorded sequence was PASS, then FAIL, then PARTIAL, which mixes two
   vocabularies. `.github/scripts/generate_spec_report.py` assigns the final
   verdict from `spec_validation_failed(...)` and can only emit FAIL, WARN, or
   PASS. PARTIAL is a trace or completeness component verdict, not a final one.

Establishing nondeterminism needs two runs against one identical head SHA with
one identical body. Nothing in this incident produced that pair.

## What to do anyway

The operating rule does not depend on the nondeterminism claim.

`.claude/rules/universal.md` requires equivalent evidence before calling a red
remote check cleared, so bind each verdict to the head SHA it ran against and
read that run's own report before concluding it describes the same
already-disclosed gap. Compare the component verdicts, not just the top line,
since only one of them drives the final result.

When the report does describe that gap, comment once on the PR naming the gap
and its tracking issue, and do not chase every re-verdict with a new comment.
When the report names anything else, treat it as a live finding and work it.

## Related

- [ci-linking-an-issue-arms-an-ai-gate-against-your-diff](ci-linking-an-issue-arms-an-ai-gate-against-your-diff.md).
  What arms this gate in the first place: only a closing keyword does, and
  `Refs #N` silently opts out of it.
