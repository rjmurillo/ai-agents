---
paths: ["**"]
priority: high
---

# Lossless Work-Queue Reads

A work queue is any list where each row is an obligation to act on or decline: PR review threads, review comments, assigned issues, notifications, a feedback file. Browsing carries no obligation, so sampling is fine there.

A limit or `head` is a guess about how many rows matter. A dropped row is a dropped obligation, such as an unaddressed review thread. Advice to page in small batches suits browsing and loses rows in triage.

- MUST page by cursor or page number until the API reports no next page, and see every row before acting on any row.
- MUST NOT pass a limit or per-page value as a completeness bound. Page size tunes fetch size. It is never a stopping rule.
- MUST NOT pipe queue output through `head`, `tail`, or `sed` before the full set has been seen.
- MUST fail loud when pagination cannot complete (missing cursor, page cap hit) and state what was not read. Never present a partial read as the full set.

Canonical implementation: `.claude/skills/pr-comment-responder/scripts/cluster_threads.py:448-456` fails with `missing pagination info`, `missing pagination cursor`, and `pagination exceeded 50 pages`.
