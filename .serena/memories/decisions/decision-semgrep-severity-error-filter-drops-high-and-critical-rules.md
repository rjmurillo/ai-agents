# The Semgrep ERROR filter drops rules marked HIGH or CRITICAL

**Atomicity**: 90%
**Category**: Security scanning
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E106. State checked on main at 1be533c496 (2026-11-26).

## Question

Does filtering for ERROR keep every rule the Semgrep gate intends to block on?

## Conventional answer

ADR-054 requires `semgrep scan --severity ERROR --json` and treats ERROR as the blocking severity.

## First-principles position

Semgrep 1.171.0 returned rules marked HIGH and CRITICAL with the filter off. With the filter on, it returned only the ERROR rule. The CLI also rejected HIGH and CRITICAL as filter values. The filter cannot enforce a policy that expects either label to block.

## Evidence with limits

- An unfiltered synthetic scan returned rules marked ERROR, HIGH, and CRITICAL (2026-08-05).
- The same test with `--severity ERROR` returned only the ERROR rule (2026-08-05).
- Limits: One synthetic run on Semgrep 1.171.0. The test did not establish whether the automatic registry configuration uses HIGH or CRITICAL labels.
- State on main at 1be533c496 (2026-11-26): still wrong. ADR-054:113 and `scripts/validation/git_hook_policy.py:5438` and `:6771` retain the filter. `scripts/security/run_semgrep.py:16` documents `--severity high`, though `:554` accepts only error, warning, and info.

## Decision

Omit the ERROR filter where HIGH or CRITICAL rules must block. Reconcile ADR-054 and the gate calls with the measured behavior. The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/semgrep-powershell-parser-errors.md`
