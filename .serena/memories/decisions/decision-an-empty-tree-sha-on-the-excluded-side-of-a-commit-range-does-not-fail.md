# Git accepts an empty tree as the excluded side of a commit range

**Atomicity**: 90%
**Category**: Git range semantics
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E109. State checked on main at 1be533c496 (2026-11-26).

## Question

Does an empty tree as the base of a commit range break the commit walk?

## Conventional answer

A review finding claimed that the empty tree base would make the range walk fail.

## First-principles position

Git 2.43 accepted the empty tree on the excluded side of `A..B`. It counted both commits and exited 0. The check also passed with a nonempty tree or blob on the excluded side.

## Evidence with limits

- `git rev-list --count` returned 2 and exited 0 with the empty tree excluded (2026-08-06).
- The count remained 2 with a nonempty tree or blob excluded (2026-08-06).
- The object walk with `--objects` returned a count of 6 when it excluded the empty tree (2026-08-06).
- Limits: One two-commit scratch repository on Git 2.43. The record did not verify the reported object counts for the nonempty exclusion.
- State on main at 1be533c496 (2026-11-26): no repo artifact is wrong. `scripts/validation/git_hook_policy.py:6864-6874` still builds the range from an empty tree when needed.

## Decision

Keep the empty tree base for diffs. Probe the exact Git command before restructuring the code. Test object walks separately from commit counts.
