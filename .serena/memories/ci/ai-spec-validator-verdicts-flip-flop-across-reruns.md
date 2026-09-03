# The AI-Spec-Validator's verdict flip-flops across reruns of the same disclosed gap

## Observation

On two different PRs (#5350, #5356), successive re-runs of the `Validate Spec
Coverage` check against the same or adjacent commits produced different
top-line verdicts (PASS, then FAIL, then PARTIAL) for the identical
underlying, already-disclosed gap: an unverified live-CLI probe on #5350, a
prompt-only versus enforced-control distinction on #5356. The gap itself never
changed. Only the validator's characterization of its severity did.

Measured 2026-08-27.

## What to do with that

The flip-flop is evidence that this validator is nondeterministic. It is not
license to dismiss it.

`.claude/rules/universal.md` requires equivalent evidence before calling a red
remote check cleared, so bind each verdict to the head SHA it ran against and
read that run's own report before concluding it describes the same
already-disclosed gap.

When the report does describe that gap, comment once on the PR naming the gap
and its tracking issue, and do not chase every re-verdict with a new comment.
When the report names anything else, treat it as a live finding and work it.

## Related

- [ci-linking-an-issue-arms-an-ai-gate-against-your-diff](ci-linking-an-issue-arms-an-ai-gate-against-your-diff.md).
  What arms this gate in the first place: only a closing keyword does, and
  `Refs #N` silently opts out of it.
