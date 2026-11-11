# --expected-head-sha takes the full SHA, and one help example shows a short one

## What happens

The `--expected-head-sha` flag compares the value to the PR's `headRefOid` by equality. A short prefix never matches, so the guard reports a head SHA mismatch and stops all mutation, even when the PR head did not move.

- `add_pr_review_thread_reply.py` passes the value to `auto_merge_guard.identity_mismatches`, which compares `want != actual` (`auto_merge_guard.py` line 156). `--resolve` requires at least one of the three expected-identity flags.
- `merge_pr.py` rejects anything that is not 40 hex characters up front (`_SHA_PATTERN` at line 203, checked at line 1586).
- `update_pr_branch.py` and `set_pr_ready.py` lower-case both sides and still compare whole strings.

## Defect noticed

The help example at `add_pr_review_thread_reply.py` line 113 shows `--expected-head-sha 0123456789abcdef`. That is 16 hex characters. Copied as written, it fails against any real head. Not fixed here.

## Practice

Read the head with `git rev-parse HEAD` after the push, or `headRefOid` from `get_pr_context.py`. Pass all 40 characters.

## Evidence

- OBSERVED 2026-11-11: the line references above, read on `origin/main` at `c4550d9ee`.
- A sweep child reported on 2026-11-11 that the reply script needs the full SHA. The code reading above confirms it; no live mutation was run to reproduce it.
- The linked memory shows a 10-character value armed with `merge_pr.py --auto` on 2026-10-24. Current code rejects that form. Why the two differ was not investigated. Treat the current code as authoritative.

## Relations

- **related_to**: [github/github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head](github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head.md)
