# Verify orphaned pr-autofix commits before reuse

When a prior pr-autofix session leaves local commits unpushed after a round-cap
or lease-driven stop, treat those commits as untrusted input. Verify each one
against an independent test run before reusing it. Do not trust the commit
message alone.

## Why

PR #5344 carried three orphaned local commits from an earlier automated
session. Two were valid and one was not. Commit `26683e981` claimed the
`zero-collection-tests` lefthook job was a duplicate, but its diff deleted both
the job and the test that would have caught that deletion. The wiring suite
passed identically with and without the commit, so the claimed rationale was
never verified.

## Practice

1. Create a preservation branch or tag pointing at the current local tip
   before resetting; a SHA written only in prose is not a git ref and does
   not stop those commits from becoming eligible for garbage collection.
2. Reset or branch from the live remote head only after that ref exists.
3. Inspect each orphaned commit diff in isolation.
4. Run the smallest independent test that can disprove the commit's claim.
5. Reuse only the commits that pass that check.

## Evidence

- PR `rjmurillo/ai-agents#5344`
- Orphaned commits `77691c852`, `26683e981`, `418f9595d`
- The dropped commit contradicted the PR's own gate-wiring table and removed
  the test that checked the job it deleted.
- Recording those SHAs identifies them for review, but text alone does not
  keep the commit objects reachable; only a branch, tag, or other ref does
  that, and none was created here before the branch tip moved.
