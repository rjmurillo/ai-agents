# Right after a push, the first guarded thread reply can go stale

## What happens

You push a fix, then reply to review threads with `add_pr_review_thread_reply.py --expected-head-sha <new full SHA>`.
The first reply can fail with `pull_request_identity_changed: head SHA`.
The script made no mutation, so nothing was posted.
The next replies in the same batch succeed with the same SHA.

The guard compares your value to the PR's `headRefOid` (`_thread_decision`, `add_pr_review_thread_reply.py` line 228).
INFERRED cause: GitHub updates `headRefOid` a moment after the push lands, so the first call still sees the old head.
No captured `headRefOid` read confirms this. The pattern of a failed first call and a clean retry is the only evidence.

## Practice

- Read the result of every reply call, not only the last one.
- On `pull_request_identity_changed` right after your own push, retry that one thread with the same full SHA.
- If the retry still fails, someone else moved the head. Fetch it and recheck before replying.

## Evidence

- [2026-11-16] [orchestrator session, PRs #7384 and #7387]: Seen four times in one session, each time right after a push.
- Example: push `32d081b32..05bd034c8`, then thread `PRRT_kwDOQoWRls63uxHw` returned `pull_request_identity_changed`.
- The three threads after it posted fine. A retry of the failed thread posted fine.
- The value passed was the full 40-character SHA from `git rev-parse HEAD`.

## Relations

- **related_to**: [github/github-expected-head-sha-must-be-the-full-sha](github-expected-head-sha-must-be-the-full-sha.md)
