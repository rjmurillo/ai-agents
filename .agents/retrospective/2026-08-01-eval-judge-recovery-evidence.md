# Truncated Evidence Made Four Eval Defects Look Like One

Date: 2026-08-01
Branch: `fix/eval-recovery-evidence-and-gating`
Issues: #3975, #4070, #4031, #3988

## Summary

`scripts/eval/eval-rule-activation.py` stored a 200-character prefix of every
judge payload that failed to parse. Measured failure offsets across the 24
archived failures run 162 to 421, so the window cut the damage out. Re-parsing
the stored prefixes yields "Unterminated string starting at" 19 times while the
real payloads yield "Expecting ',' delimiter" 24 times. The archive recorded
the truncation instead of the judge.

That single storage decision hid three more defects, each filed as its own
issue. Fixing them together was not scope creep; the same record is the input
to all four.

## What the four issues turned out to share

| Issue | Surface defect | Shared root |
|-------|----------------|-------------|
| #3975 | 200-character prefix on the failure record | The record is the only evidence, and it was lossy |
| #4070 | Gates compared display-rounded averages against their floors | The published number and the gated number came from one `round(..., 2)` call |
| #3988 | `judge_salvaged` written twice, read nowhere | The marker never reached a cell result, so no gate could read it |
| #4031 | `_judge_parse_failure` returned `judge_failed: False` | The name described the trigger, not the two branches it takes |

Reading all four issue threads before editing is what surfaced the overlap. The
triage verdict for #3988 explicitly warned against the obvious fix (delete the
recovery path) because the measurement that motivated deletion had already been
retracted in-repo. Acting on the issue title alone would have deleted working
recovery code.

## What went wrong during the work

Two new tests were wrong on the first pass, and both failures had the same
shape: the test asserted the right claim against a fixture that could not
exercise it.

1. The fabricated-parse-error test led its payload with prose. That made the
   200-character prefix fail at character 0 rather than mid-string, so the test
   passed for the wrong reason. A prefix that fails at offset 0 does not
   demonstrate that truncation fabricates a cause.
2. The salvage-gate pass test used a scenario whose verdict was already
   `FAIL_NO_DELTA`. Exit 1 proved nothing about the new
   `--max-salvaged-fraction` bound, because the run would have exited 1 anyway.

Both were caught by asking what the test would do against the pre-fix code.
Every new test on this branch was run against pre-fix code and required to fail
there. That check is cheap and it caught both.

## Tooling defects found on the path

`.claude/skills/session-end/scripts/complete_session_log.py:76` resolves the
repository root with `git rev-parse --git-common-dir`. In a linked worktree
that points at the main checkout, so the script auto-detected an unrelated
session log belonging to another branch and wrote to it. Passing
`--session-path` with a path inside the worktree then failed with
"Session path must be inside '<main checkout>/.agents/sessions'". The stray
write had to be reverted by hand.

This is the issue #3402 class (worktree identity) reaching a skill script. The
rule at `.claude/rules/ci-scripts.md` MUST 7 already requires a script that
resolves a root and writes to it to confirm the current directory is inside
that root. This script does neither.

## What changed

Every failed and salvaged judge record now carries the whole payload under
`judge_raw`, on all three salvage paths, in `eval-rule-activation.py` and in
both sibling scorers. Every judge sample carries `judge_model`, including the
RuntimeError path, so a per-model claim is checkable from the record rather
than the artifact filename. `_mechanism_summary` emits `avg_score_exact` beside
the rounded `avg_score`, and every gate reads the exact value while the table
keeps publishing the rounded one. `judge_salvaged` survives reduction as
`salvaged_sample_count`, reaches the run summary as
`salvaged_sample_fraction`, and `--max-salvaged-fraction` fails the run when
recovery carried more of it than the bound allows.

ADR-091 records the decision to keep the hand-written recovery path, the
round-9 residual it accepts, and provider-enforced structured output as the
exit path.

## What to carry forward

- When several issues name the same file, read all their threads before
  editing. The overlap is usually the root cause and the separate fixes are
  usually symptoms.
- Run every new regression test against pre-fix code. A test that passes there
  is measuring something else.
- Evidence a gate reads must be stored whole. A truncation applied for
  readability turns the archive into a record of the truncation.
- A skill script that resolves a repository root needs the worktree-identity
  check before its first write, not after a stray file lands in another branch.
