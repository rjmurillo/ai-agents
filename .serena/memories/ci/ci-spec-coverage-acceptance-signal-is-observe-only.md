# Skill: Spec acceptance signal is observed, not authoritative (98%)

## Statement

The `External-signal gate (observe)` step returns `NEEDS_REVIEW` with reason
`closed-loop:external-signal-inconclusive` when a pull request body has no
acceptance-criteria checkbox list. That step is not the `Validate Spec Coverage`
job's authoritative verdict.

`.github/workflows/ai-spec-validation.yml:174-186` sets
`continue-on-error: true` and states that the observed signal does not replace
`.github/scripts/check_spec_failures.py`. The final `Check for Failures` step
passes only the trace and completeness verdicts to that script. It does not pass
the external acceptance result.

Measured 2026-08-03:

- No acceptance section made `spec_external_signal_wrapper.py` exit 1 with
  `NEEDS_REVIEW`.
- The authoritative `check_spec_failures.py` call with both agent verdicts set
  to `COMPLIANT` exited 0.

Missing acceptance criteria alone therefore do not fail the current job.

## Why PR #4294 was red

PR #4294 produced `trace=PASS` and `completeness=PARTIAL`. The authoritative
script exits 1 for that pair because `PARTIAL` is a failing completeness
verdict. The observed acceptance signal also exited 1, but `continue-on-error`
kept that result from deciding the job. The two failures happened together;
the acceptance result did not cause the job failure.

## Stale comment caveat

The job posts its verdict as a pull request comment marked
`<!-- AI-SPEC-VALIDATION -->`, and the poster skips when a comment with that
marker already exists:

```text
Comment with marker 'AI-SPEC-VALIDATION' already exists. Skipping.
```

The visible comment may therefore describe an earlier run. Read the current job
log before diagnosing a red check.

## Format that parses

The heading regex is `^#{1,6}\s*acceptance(?:\s+criteria)?\s*$`, case
insensitive. Items must use `- [x]` or `* [x]` Markdown task-list bullets. A
numbered list does not parse. All boxes checked gives `PASS`, any box unchecked
gives `FAIL`, and no section gives `UNKNOWN`.

The observed signal reads the pull request body, not the linked issue. Checkboxes
on the issue do not satisfy this parser.

## Reproduce locally

Run the observed external signal against a candidate body:

```bash
PR_BODY_FILE=body.md TRACE_VERDICT=PASS COMPLETENESS_VERDICT=PASS \
  uv run --frozen python scripts/quality_gate/spec_external_signal_gate.py
```

Then run the authoritative gate separately:

```bash
uv run --frozen python .github/scripts/check_spec_failures.py \
  --trace-verdict PASS --completeness-verdict PASS
```

Measured results:

| Input | Observed signal | Authoritative gate |
|---|---|---|
| no acceptance section, PASS and PASS | exit 1, `NEEDS_REVIEW` | exit 0 |
| checked criteria, PASS and PASS | exit 0, `PASS` | exit 0 |
| checked criteria, PASS and PARTIAL | exit 0, `WARN` | exit 1 |

## Generalization

The acceptance parser is a canary signal until the workflow removes
`continue-on-error` and feeds its result into the final gate. Checked criteria
are useful input for that signal, but current guidance must not describe them as
a merge blocker.
