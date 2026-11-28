# The default Semgrep timeout can leave a batch scan incomplete

**Atomicity**: 90%
**Category**: Security scanning
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E105. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a pre-push scan count a Semgrep timeout as a pass?

## Conventional answer

A Semgrep scan without findings was treated as a pass even if it reported a timeout.

## First-principles position

The default 5-second rule timeout interrupted a batch scan. The run with a 30-second timeout completed without scan errors. A timeout leaves a rule incomplete for the affected file, regardless of the finding count.

## Evidence with limits

- Semgrep 1.171.0 returned 1 timeout error in 23.2 seconds with the default timeout on a 24-file batch (2026-08-05).
- The same batch returned 0 errors in 34.5 seconds with `--timeout 30` (2026-08-05).
- Limits: One batch and one machine on 2026-08-05. The default run reported 2 findings from compatibility rules excluded from later runs. The comparison did not isolate machine load. The no-timeout and single-file runs were not verified in the transcript.
- State on main at 1be533c496 (2026-11-26): fixed. `scripts/validation/git_hook_policy.py:5447` sets `--timeout=30`. The comment at `:5429` explains the default timeout failure.

## Decision

Treat a Semgrep timeout as incomplete scan coverage. Keep the gate's 30-second setting.
