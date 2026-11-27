# Inherited Git settings can redirect a ship script after it drops GH_REPO

**Atomicity**: 90%
**Category**: Script environment safety
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E127. State checked on main at 1be533c496 (2026-11-26).

## Question

Is stripping `GH_REPO` from the child environment enough to keep the target repository fixed?

## Conventional answer

ADR-127 draft 3 item 6 bars environment variables that change the target or host. Dropping `GH_REPO` was thought sufficient.

## First-principles position

Git children still inherited `GIT_DIR`. They consulted the repository it named instead of the intended checkout. Removing `GH_REPO` alone therefore did not enforce the ADR's target rule.

## Evidence with limits

- The Git child processes returned the second repository's origin and a different HEAD (2026-11-25).
- Limits: The probe covered `GIT_DIR` only. Other Git environment settings were identified by inspection and were not tested.
- State on main at 1be533c496 (2026-11-26): no repo artifact. `src/claude/skills/ship/scripts` is absent on main, so the implementation state is unknown. ADR-127:88 still states the target rule.

## Decision

Strip or pin repository selection settings in the Git child environment. Verify the target with a second repository in a local test.

## Related

- `.serena/memories/decision-worktree-identity-guard-scope.md`
- `.serena/memories/ci/git-dir-from-a-linked-worktree-push-outranks-git-c.md`
