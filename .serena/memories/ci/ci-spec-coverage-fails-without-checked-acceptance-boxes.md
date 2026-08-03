# Skill: Validate Spec Coverage fails without checked acceptance boxes in the PR body (98%)

## Statement

`Validate Spec Coverage` returns `NEEDS_REVIEW` with reason
`closed-loop:external-signal-inconclusive` when the pull request body has no
acceptance-criteria checkbox list. The quality of the implementation does not
enter into it. Nothing in the job name, the check name, or the pull request
comment says the body is the problem.

`scripts/external_signals/gate_aggregator.py:106` requires at least one signal
of kind `external` whose verdict is passing or warning. The only external signal
the spec gate emits is `acceptance-criteria`, extracted by
`scripts/quality_gate/spec_external_signal_gate.py` from `PR_BODY_FILE`. With no
criteria found it reports `UNKNOWN`, the external set is empty, and the gate
refuses.

Measured 2026-08-02 on PR #4294, whose two model signals were `trace=PASS` and
`completeness=PARTIAL`, both healthy, while the job still exited 1.

## The comment lies

The job posts its verdict as a pull request comment marked
`<!-- AI-SPEC-VALIDATION -->`, and the poster skips when a comment with that
marker already exists:

```text
Comment with marker 'AI-SPEC-VALIDATION' already exists. Skipping.
```

So the visible comment is whatever the first run said. On PR #4294 it read
`Final Verdict: PASS`, `Requirements Traceability PASS`,
`Implementation Completeness PASS`, `5 of 5 covered, no gaps`, while the check
itself was red. Read the job log, never the comment:

```bash
gh run view --job "$JOB_ID" --log | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -P 'VERDICT|"verdict"|"reason"'
```

## Format that parses

The heading regex is `^#{1,6}\s*acceptance(?:\s+criteria)?\s*$`, case
insensitive, and items must be Markdown task list checkboxes. All boxes checked
gives `PASS`, any box unchecked gives `FAIL`, no section at all gives `UNKNOWN`.

```markdown
## Acceptance criteria

- [x] first criterion
- [x] second criterion
```

A numbered list does not parse. Issue #4257 writes its criteria as `1.` through
`5.`, so copying the issue verbatim still yields `UNKNOWN`. The signal reads the
pull request body, not the issue, so putting checkboxes only on the issue does
nothing.

## Reproduce locally in seconds

The gate is deterministic and makes no model calls, so the whole verdict can be
computed offline against a candidate body. This turns a three minute CI round
trip into one command.

```bash
gh pr view "$PR" --json body --jq .body > body.md
PR_BODY_FILE=body.md TRACE_VERDICT=PASS COMPLETENESS_VERDICT=PARTIAL \
  uv run --frozen python scripts/quality_gate/spec_external_signal_gate.py
```

Measured on PR #4294 with the verdicts CI actually produced:

| Body | Exit | Verdict | Reason |
|---|---|---|---|
| as filed | 1 | `NEEDS_REVIEW` | `closed-loop:external-signal-inconclusive` |
| plus checked criteria | 0 | `WARN` | `warnings-present` |

## Generalization

This gate is a closed-loop guard, and its refusal is the intended behavior. Two
signals from the same model agreeing with each other is one measurement, not
two, so the gate declines to decide on model output alone and demands one
deterministic signal it can compute itself. The fix is to supply that signal,
never to argue the model into a better verdict.
