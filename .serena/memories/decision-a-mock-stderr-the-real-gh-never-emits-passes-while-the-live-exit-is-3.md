# The missing PR test passed with mocked stderr while the live command exited 3

**Atomicity**: 90%
**Category**: Test mock fidelity
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E116. State checked on main at 1be533c496 (2026-11-26).

## Question

Do passing mocks prove that a wrapper returns exit 2 for a missing PR?

## Conventional answer

The mock suite was treated as proof that the wrapper returned exit 2 for missing PRs.

## First-principles position

The test fed the wrapper a generic missing-item message. The real client returned a GraphQL error without the words `not found`. The live wrapper returned exit 3, so the passing test missed the documented behavior.

## Evidence with limits

- `test_pr_not_found_exits_2` passed with mocked stderr `not found` (2026-08-08).
- The live probe for nonexistent PR 999999 returned exit 3 (2026-08-08). The error said GraphQL could not resolve the pull request number.
- Limits: One live probe on one missing PR. The session record cites gh v2.97.0, but the quoted output does not confirm the version.
- State on main at 1be533c496 (2026-11-26): fixed. `src/claude/skills/github/scripts/pr/get_pr_context.py:168` uses `is_pr_not_found` to return exit 2. `tests/test_get_pr_context.py:221` mocks the GraphQL message shape and expects exit 2.

## Decision

Base mocked stderr on a captured CLI run. Probe each documented exit code against the real client before claiming it works.

## Related

- `.serena/memories/testing/testing-mock-fidelity.md`
