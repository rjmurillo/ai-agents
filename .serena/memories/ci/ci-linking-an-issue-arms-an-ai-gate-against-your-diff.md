# Linking an Issue Arms an AI Gate Against Your Diff

## The contradiction

Conventional reading: linking an issue in a PR body is bookkeeping. It closes the
issue on merge and helps humans navigate.

In this repository it is not bookkeeping. `Fixes #N` or `Refs #N` in the PR body
arms `.github/workflows/ai-spec-validation.yml`, which then holds the diff to that
issue's acceptance criteria and blocks the PR when they are not met.

## Mechanism

1. `scripts/ci/spec_extract_refs.py` reads `PR_BODY_INPUT` and emits the issue and
   spec refs it finds. Every later step is guarded by
   `steps.spec-ref.outputs.has_specs == 'true'`, so no refs means the gate never runs.
2. `spec_load_content.py` fetches the referenced issue and spec bodies.
3. Two AI reviewers run over `context-type: pr-diff` with that content as
   `additional-context`: `agent: analyst` produces a trace verdict, `agent: critic`
   produces a completeness verdict.
4. `.github/scripts/check_spec_failures.py` holds the authoritative verdict. When
   `spec_validation_failed(trace, completeness)` is true it prints
   `::error::Spec validation failed - implementation does not fully satisfy requirements`
   and returns 1. An infrastructure failure in **both** reviewers returns 0 instead,
   so an unavailable Copilot CLI cannot block a merge.

The PR body is passed separately as `PR_BODY`, so claims made in the description
are compared against what the diff actually contains.

## What this changes

The PR description is evidence, not prose. A body that claims tests which are not
in the diff fails CI on that mismatch alone. On PR #4412 the description named
`TestReportBypassHint` and `TestMainBypassHintRouting`; the diff added a single
trailing newline to the test file. The gate caught it and was correct.

The acceptance criteria live in the issue, not the PR. An issue that asks for a
negative test makes that negative test a merge requirement, whether or not the PR
author read that line.

## Consequences

- Read the linked issue's acceptance criteria before writing the PR body. They are
  the rubric the gate scores against.
- Do not describe work in the PR body that is not in the diff. Describing intent
  reads as a claim.
- A PR with no issue reference silently skips this gate. That is a weaker PR, not a
  cheaper one.
- When the gate returns `PARTIAL`, read the gap list. On #4412 it named the exact
  missing test classes and quoted the issue line that required them.

## Not the same as the external-signal gate

`ai-spec-validation.yml` also runs an "External-signal gate (observe)" step through
`scripts/ci/spec_external_signal_wrapper.py`. That step is `continue-on-error: true`
and is reported in the job summary only. It does not decide the check. Reading its
output as the verdict misattributes both passes and failures.

## Related

- `.github/scripts/check_spec_failures.py` (the authoritative verdict)
- `.github/workflows/ai-spec-validation.yml` (gate definition)
- `scripts/ci/spec_extract_refs.py` (the `has_specs` guard)
- [ci-validate-pr-has-four-signals-but-only-one-blocks](ci-validate-pr-has-four-signals-but-only-one-blocks.md).
  A different check with the same trap: most of its output is advisory.
