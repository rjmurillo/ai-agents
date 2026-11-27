# A count ratchet baseline counted the ratchet's own self referencing lines as debt

**Atomicity**: 90%
**Category**: CI ratchets
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E006. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a passing count ratchet prove its baseline equals the true debt?

## Conventional answer

A merged ratchet baseline equals the true type-ignore debt. A passing gate means the number is accurate.

## First-principles position

A passing ratchet shows only that the count did not grow. The baseline was set from a count that included the ratchet's own code and tests. About 20 percent of that count described the pattern instead of using it.

## Evidence with limits

- Measured 2026-08-01: the merge base had 44 type-ignore lines. After PR 4093 the total was 56, including 11 self references in the ratchet implementation and its test.
- The baseline was set to 55. The true count excluding self references was 45. The 11 of 56 self references were 20 percent of the total.
- Quote from the run: "Total (including self-refs): 56 | Self-reference count (ratchet impl + tests): 11 | True count (excluding self-refs): 45"
- Limits: One ratchet, measured 2026-08-01. PR 4142 fixed it with `_SELF_REFERENTIAL_FILES`. Main also excludes generated lib mirrors.
- State on main at 1be533c496 (2026-11-26): fixed. scripts/ci/type_ignore_count_ratchet.py:78 defines `_SELF_REFERENTIAL_FILES`, which excludes the ratchet and its test.

## Decision

Before setting a count ratchet baseline, exclude files that only describe or test the pattern. A passing gate shows the count did not grow, not that the number is true.

## Related

- `.serena/memories/ci/ci-count-ratchets-require-branch-freshness.md`
- `.serena/memories/feedback-self-referential-test-anti-pattern.md`
