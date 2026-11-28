# The documented pre_pr quick flag saving of 50 to 90 seconds was false when measured

**Atomicity**: 90%
**Category**: CI performance claims
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E004. State checked on main at 1be533c496 (2026-11-26).

## Question

How much wall clock time does the pre_pr quick flag actually save?

## Conventional answer

`.project-toolkit/devops/SHIFT-LEFT.md` said `--quick` saves about 50 to 90 seconds. It cited Path Normalization, Planning Artifacts, and Agent Drift.

## First-principles position

A paired run with and without the flag showed the claim was false. Path Normalization and Planning Artifacts were dead stub skips whether or not the flag was set. The gates the flag really bypasses cost under 2 seconds together.

## Evidence with limits

- Measured 2026-08-06: full run 57.19s, quick run 55.84s, so the flag saved about 1.35s.
- Agent Drift cost 0.09s and YAML Style cost 1.84s. Path Normalization and Planning Artifacts skipped at 0.00s in both modes.
- Limits: One run on one branch on 2026-08-06, n=1 per mode. The stubs were later replaced by real gates. A 2026-08-19 QA note and a later memory measured 1.89s saved of 103.25s, with the same conclusion.
- State on main at 1be533c496 (2026-11-26): still wrong. `.serena/memories/ci/devops-validation-runner-pattern.md:16` still claims a saving of 50 to 90 seconds per run. `.project-toolkit/devops/SHIFT-LEFT.md:46` reports under 2 percent.

## Decision

Measure with and without the flag before documenting any savings. In those runs, `--quick` saved roughly 2 percent of elapsed time.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
- `.serena/memories/ci/devops-validation-runner-pattern.md`
