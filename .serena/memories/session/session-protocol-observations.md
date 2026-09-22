<!-- placement: evidence; reason: dated PR #908 measurements, kept as the evidence behind the pre-PR and commit-count gates rather than as the gates themselves -->

# Session Sidecar Learnings: PR #908

**Last Updated**: 2026-01-21
**Sessions Analyzed**: 2 (Session 07, PR #908 retrospective)

Authoritative owners: `scripts/validation/pr_commit_count.py` holds the commit
thresholds, and the pre-PR validation gates enforce the rest. This file keeps
the measurements that motivated them.

## Measurements (PR #908, 2026-01-15)

| Signal | Value | Consequence |
|---|---|---|
| Comments on the pull request | 228+ | created despite an unresolved architect P1 BLOCKING review in `DESIGN-REVIEW-skill-reflect.md` |
| Commits on the branch | 59 | three times the limit, with no in-session visibility of the count |
| Memory files reformatted | 53 | `markdownlint --fix **/*.md` touched files unrelated to the change |

Repository responses that followed: pre-PR validation (Issue #934), the commit
thresholds in `scripts/validation/pr_commit_count.py` (block above 20 per pull
request, above 40 once the branch merges main, warn at 10), and scoping
markdownlint to `git diff --name-only '*.md'` rather than the whole tree.

## Transferable reading

Each of the three failures was invisible from inside the session. The agent
could not see the comment count climbing, the commit count, or which files a
glob had touched. A limit nobody can read during the work is not a limit.

See `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`.

## Related

- [session-observations](session-observations.md)
- [../protocol/protocol-001-verificationbased-gates](../protocol/protocol-001-verificationbased-gates.md)
