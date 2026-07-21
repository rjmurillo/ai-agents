# Lefthook has no finally step in piped jobs

## Question
Can pre-push create a suppression sentinel in the first Lefthook job and reliably remove it in the last job?

## Conventional answer
Issue #2327 used start and end sentinel steps around long pre-push validation. Commit 820f38769a restored that shape in `lefthook.yml`.

## First-principles position
No. Lefthook 2.1.10 stops a `piped: true` chain after the first failure. A cleanup job at the end is skipped, so the sentinel can remain and suppress later Stop-hook behavior.

## Evidence
An isolated Lefthook 2.1.10 probe ran `start`, failed the next job, and reported `cleanup (skip) broken pipe`; the trace contained only `start`. The repository regression in `tests/test_lefthook_integration.py` forbids the sentinel commands and policy string.

## Decision
Keep `lefthook.yml` framework-native. Do not add start/end cleanup sentinels as separate piped jobs. Removed the sentinel commands and policy helpers after merging commit 820f38769a.