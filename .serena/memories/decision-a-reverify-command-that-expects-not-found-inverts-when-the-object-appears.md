# A knowledge pack check for missing commits failed when the clone held extra refs

**Atomicity**: 90%
**Category**: Knowledge pack verification
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E056. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a re-verify command whose pass condition is "not found" stay valid over time?

## Conventional answer

Knowledge-pack rows stamped "verified 2026-07-03" were trusted as current. Retro-cited SHAs were said to possibly not resolve.

## First-principles position

On 2026-08-01, the agent ran the recorded checks and found four stale rows. One row expected two commits to be missing. Both existed in that clone because it carried extra refs. Squash-only merge policy describes the repo without relying on which objects a clone holds.

## Evidence with limits

- Re-ran the commands in nine skill files stamped "verified 2026-07-03" (2026-08-01). Four rows failed.
- The allowlist row said 9 patterns. The command returned 8 (2026-08-01).
- The ADR-034 row said 5 patterns. The command returned 8 (2026-08-01).
- ADR-068 status: the row said Proposed, the command showed Accepted.
- The `cat-file` check expected "Not a valid object name". Both objects exist and neither is an ancestor of main.
- Limits: Memory count figures differ inside the transcript (122 to 158 top-level in the PR, 879 recursive in a later probe). The other three rows are already fixed on main. Resolution of those SHAs depends on the clone, so the claim is clone-dependent rather than flatly false.
- State on main at 1be533c496 (2026-11-26): still wrong. `.claude/skills/ai-agents-failure-archaeology/SKILL.md:22` says some retro-cited short SHAs do not resolve locally. Both `cat-file` calls print "commit" in the pinned worktree.

## Decision

Do not write a re-verify check whose pass condition is "not found". Prefer a check on a stable policy, such as squash-only merge or `merge-base --is-ancestor`. Date-stamp counts.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/git/git-absence-and-case-in-plumbing.md`
- `.serena/memories/quality/verify-squash-merge-by-content-not-ancestry.md`
