# Linking an Issue Arms an AI Gate Against Your Diff

## The contradiction

Conventional reading: linking an issue in a PR body is bookkeeping. It closes the
issue on merge and helps humans navigate.

In this repository it is not bookkeeping. A **closing keyword** in the PR body arms
`.github/workflows/ai-spec-validation.yml`, which then holds the diff to that
issue's acceptance criteria and blocks the PR when they are not met.

Only four keywords arm it. `scripts/ci/spec_extract_refs.py:85` matches
`Closes|Fixes|Resolves|Implements` and nothing else:

```python
r"(?:Closes|Fixes|Resolves|Implements)\s+((?:[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)?#\d+)",
```

**`Refs #N` does not arm this gate.** It matches no pattern, so `has_specs` stays
false and every AI check is skipped. That matters because `Refs #N` is the form
`.claude/rules/universal.md` offers for a PR that should not close its issue: it
satisfies the issue-linkage rule while silently opting out of spec validation.
Reaching for `Refs` to avoid auto-closing also buys you a skipped gate, whether or
not you wanted one.

## Mechanism

1. `scripts/ci/spec_extract_refs.py` reads `PR_BODY_INPUT` and emits the issue and
   spec refs it finds. The two AI checks, the observe-only external-signal step, and
   the authoritative `Check for Failures` step are all guarded by
   `steps.spec-ref.outputs.has_specs == 'true'`, so no refs means nothing can fail.
   Be precise about the scope: `Generate Validation Report`, `Post PR Comment`, and
   `Set Job Summary` are **not** guarded and run either way, so a comment appearing on
   the PR is not evidence the gate evaluated anything.
2. `spec_load_content.py` fetches the referenced issue and spec bodies.
3. Two AI reviewers run over `context-type: pr-diff` with that content as
   `additional-context`: `agent: analyst` produces a trace verdict, `agent: critic`
   produces a completeness verdict.
4. `.github/scripts/check_spec_failures.py` holds the authoritative verdict. When
   `spec_validation_failed(trace, completeness)` is true it prints
   `::error::Spec validation failed - implementation does not fully satisfy requirements`
   and returns 1. An infrastructure failure in **both** reviewers returns 0 instead,
   so an unavailable Copilot CLI cannot block a merge.

## What the reviewers actually see

Not the PR body. `scripts/ci/spec_prepare_context.py:48` builds the
`additional-context` payload as `["## Specification Content", "", spec_content]`,
sourced from `SPEC_FILE` alone. Steps 6 and 7 pass that payload with
`context-type: pr-diff`.

So the comparison is **diff against the issue and spec acceptance criteria**. The
PR description is not in the reviewers' context at all. `PR_BODY` is referenced in
exactly one place in this workflow: step 8, `External-signal gate (observe)`, which
is `continue-on-error: true` and decides nothing.

Description-versus-diff is a different gate entirely:
`scripts/validation/pr_description.py`, inside `pr-validation.yml`. The two are
routinely confused because both can red a PR that overclaims. They fail for
different reasons, in different workflows, and their fixes are different: this gate
wants code that satisfies the issue; that one wants a body that matches the diff.

## What this changes

The acceptance criteria live in the issue, not the PR. An issue that asks for a
negative test makes that negative test a merge requirement, whether or not the PR
author read that line. Writing a persuasive PR body does not help here, because the
reviewers never see it. Only the diff can satisfy this gate.

The two verdicts do not block symmetrically. From
`scripts/ai_review_common/verdict.py:215`:

```python
_TRACE_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "NEEDS_REVIEW"})
_COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})
```

`PARTIAL` is in the completeness set and absent from the trace set. A trace verdict
of `PARTIAL` passes; a completeness verdict of `PARTIAL` blocks. Read which reviewer
returned it before deciding whether you are actually red.

## Consequences

- Read the linked issue's acceptance criteria before writing the code. They are the
  rubric the gate scores the diff against.
- Use a closing keyword when you want the gate. Use `Refs` only when you have
  decided you do not, and know you are skipping spec validation to get there.
- A PR with no closing keyword silently skips this gate. That is a weaker PR, not a
  cheaper one.
- When the verdict is `PARTIAL`, check which reviewer produced it. Completeness
  `PARTIAL` is a merge blocker; trace `PARTIAL` is not.

## Not the same as the external-signal gate

`ai-spec-validation.yml` also runs an "External-signal gate (observe)" step through
`scripts/ci/spec_external_signal_wrapper.py`. That step is `continue-on-error: true`
and is reported in the job summary only. It does not decide the check. Reading its
output as the verdict misattributes both passes and failures.

## Related

- `.github/scripts/check_spec_failures.py` (the authoritative verdict)
- `.github/workflows/ai-spec-validation.yml` (gate definition)
- `scripts/ci/spec_extract_refs.py` (the `has_specs` guard)
- [ci-validate-pr-is-many-gates-only-some-read-the-body](ci-validate-pr-is-many-gates-only-some-read-the-body.md).
  A different check with the same trap: most of its output is advisory.
