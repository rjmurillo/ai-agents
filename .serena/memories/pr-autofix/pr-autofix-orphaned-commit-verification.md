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

1. Reset or branch from the live remote head first.
2. Inspect each orphaned commit diff in isolation.
3. Run the smallest independent test that can disprove the commit's claim.
4. Reuse only the commits that pass that check.

## Evidence

- PR `rjmurillo/ai-agents#5344`
- Orphaned commits `77691c852`, `26683e981`, `418f9595d`
- The dropped commit contradicted the PR's own gate-wiring table and removed
  the test that checked the job it deleted.
