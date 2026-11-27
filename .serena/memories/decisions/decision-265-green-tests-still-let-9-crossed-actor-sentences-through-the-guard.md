# Passing targeted tests missed crossed actor sentences that the retrieval guard accepted

**Atomicity**: 90%
**Category**: Guard verification
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E171. State checked on main at 1be533c496 (2026-11-26).

## Question

Do passing tests show that a guard rejects the inputs it claims to block?

## Conventional answer

Passing targeted tests and lint were taken as proof that the guard rejected crossed actor sentences.

## First-principles position

The stated goal was to reject sentences that mix actions by different actors. An independent probe through the production wrapper found that the guard still accepted such sentences. It also rejected some inputs the probe expected it to accept.

## Evidence with limits

- At the PR head, 265 tests passed (2026-08-10).
- The production wrapper admitted 9 crossed actor sentences using connectors such as until, so, and before (2026-08-10).
- The same probe found 2 false rejects (2026-08-10).
- Limits: One PR head. PRs 4787 and 4817 later changed the guard. The session did not repeat the probe on those changes.
- State on main at 1be533c496 (2026-11-26): no repo artifact confirms the current behavior. The history of `tests/test_analyst_skill_resolution.py` shows later changes, not whether the probe would still fail.

## Decision

Test the claimed bad input class through the production entry point. Use the probe outcome to judge the guard rather than relying on a passing test count.

## Related

- `.serena/memories/governance/trust-damage-false-claims.md`
