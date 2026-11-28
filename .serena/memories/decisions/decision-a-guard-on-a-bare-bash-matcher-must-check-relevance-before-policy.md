# A guard on every Bash call denied 15 of 22 unrelated commands because it applied policy before relevance

**Atomicity**: 90%
**Category**: Hook guard design
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E066. State checked on main at 1be533c496 (2026-11-26).

## Question

Should a guard on a bare Bash matcher check relevance before it applies policy?

## Conventional answer

The guard treated shell wrappers as in scope before checking what they ran. A reviewer also prescribed an allowed-tools Python pattern. ADR-068 stated 6 events and 8 registrations in its settings inventory (2026-08-10).

## First-principles position

A review round drove the push-pr identity guard with the real host payload shape. The guard ran policy before it checked relevance, so ordinary commands were denied. The same round probed the prescribed pattern and measured the inventory. Both claims failed against the probes.

## Evidence with limits

- Drove the guard with 22 unrelated commands and 11 new_pr.py attempts (2026-08-10). 15 of 22 unrelated commands were denied before the fix and 0 of 22 after.
- Plain `ls` and `git status` passed with exit 0. A `bash -c echo` wrapper was denied with exit 2.
- A probe of the allowed-tools pattern showed the colon form grants nothing and the space form granted a lookalike command.
- The ADR-068 settings inventory measured 5 events and 7 registrations, not 6 and 8 (2026-08-10).
- A file_digest call broke the Python 3.10 floor, and the gate failed open.
- Limits: One guard, one hook host (Copilot dispatch), 2026-08-10. The allowed-tools colon-form claim rests on a 2026-08-08 probe recorded elsewhere, not measured in this transcript. The 5 and 7 count was not re-run here.
- State on main at 1be533c496 (2026-11-26): superseded. No guard file exists on main. ADR-084:367 records the issue 5013 blast radius of 127 unrelated Bash denies.

## Decision

A PreToolUse guard on a bare Bash matcher must test relevance first and deny only inside its own scope. Drive it with 20 or more unrelated commands before merge.

## Related

- `.serena/memories/copilot-hook-generation-invariants.md`
- `.serena/memories/root-cause-pretooluse-bash-hook-wedge.md`
