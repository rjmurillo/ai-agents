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
already-disclosed gap. Compare both component verdicts, not just the top line.
`spec_validation_failed` in `scripts/ai_review_common/verdict.py` blocks on
either one: `return trace_upper in _TRACE_FAILURES or completeness_upper in
_COMPLETENESS_FAILURES`. The two sets differ by one entry, `PARTIAL`, which
only the completeness set counts as a failure.

When the report does describe that gap, comment once on the PR naming the gap
and its tracking issue, and do not chase every re-verdict with a new comment.
When the report names anything else, treat it as a live finding and work it.

## Related

- [ci-linking-an-issue-arms-an-ai-gate-against-your-diff](ci-linking-an-issue-arms-an-ai-gate-against-your-diff.md).
  What arms this gate in the first place. A closing keyword is one of two
  arming paths, not the only one: `run` in `scripts/ci/spec_extract_refs.py`
  sets `has_specs` true when either extractor returns something.
  `_extract_issue_refs` matches `Closes|Fixes|Resolves|Implements` alone, so
  `Refs #N` yields no issue ref, but `_extract_spec_refs` still arms the gate
  off a `REQ`, `DESIGN`, or `TASK` id, or an `.agents/specs/` or
  `.agents/planning/` markdown path, in the same title and body text:
  `req_ids = re.findall(r"(?:REQ|DESIGN|TASK)-\d+", combined)`. `Refs #N` opts
  out only when the body carries none of those, which is the case issue #5489
  reports.
