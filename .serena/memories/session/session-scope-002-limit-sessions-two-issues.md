<!-- placement: evidence; reason: the PR #669 co-mingling incident, kept as the observation behind session scope discipline -->

# Session Scope: The PR #669 Co-Mingling Incident

No first-class artifact enforces a session issue count today. This file keeps
the incident that motivated the practice, so a future session can weigh it.

## Observation (PR #669)

One session handled four or more pull requests at once. The result was
cross-PR contamination: commits landed on the wrong branch, and changes
intended for one PR were applied to another.

Reported failure modes from that session:

- Branch confusion, committing to the wrong pull request.
- Context mixing, changes intended for PR A applied to PR B.
- Ambiguity about which pull request was active at any moment.

## Transferable reading

Two issues per session was the limit that session's retrospective proposed.
The number is a judgment, not a measurement. What the incident does show is
that the failure appears as wrong-branch commits, which
`.claude/rules/universal.md` MUST-1 and the branch guards now catch after the
fact rather than before.

## Related

- [pr-review/pr-co-mingling-root-cause-2025-12-31](../pr-review/pr-co-mingling-root-cause-2025-12-31.md)
- [git/git-004-branch-verification-before-commit](../git/git-004-branch-verification-before-commit.md)
- [git/git-worktree-parallel](../git/git-worktree-parallel.md)
