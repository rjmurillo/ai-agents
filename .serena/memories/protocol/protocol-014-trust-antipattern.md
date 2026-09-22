<!-- placement: evidence; reason: three dated compliance failures, kept as the record behind enforcement that runs in hooks rather than in prose -->

# Protocol: Three Failures That Trust-Based Wording Did Not Prevent

Authoritative owners: `lefthook.yml` and `.claude/rules/push-lock.md` carry the
live commit and push gates. `.agents/architecture/ADR-014-distributed-handoff-architecture.md`
carries the handoff decision. This file keeps the three observations.

## Observations (PR #669 retrospective and earlier)

| Requirement, as written | Wording | Outcome |
|---|---|---|
| Check for an existing skill before running raw `gh` | "Remember to check" | 5+ violations in Session 15 |
| Keep handoff context current | "Update HANDOFF.md with session context" | the file reached 35 KB, with merge conflicts on about 80% of pull requests |
| Confirm the branch before committing | "Verify you are on the right branch" | wrong-branch commits, four pull requests contaminated in PR #669 |

## The shared shape

Each requirement was documentation-heavy, had no command that could be run to
check it, and surfaced its violations during review rather than preventing
them. The same mistake repeated, which is the signal that separates a missing
gate from a one-off error.

## Related

- [protocol-001-verificationbased-gates](protocol-001-verificationbased-gates.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [git/git-004-branch-verification-before-commit](../git/git-004-branch-verification-before-commit.md)
