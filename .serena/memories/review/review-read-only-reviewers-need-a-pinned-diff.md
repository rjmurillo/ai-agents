# Read-only reviewers need a pinned scope, and a marker needs an independent pass

## What happened

[2026-10-14] Security reviews handed to the `security` agent came back with "scope not pinned". The agent has no shell. Its `tools:` list in `.claude/agents/security.md` has no Bash, so it cannot run `git diff` itself. It does have GitHub reads, including `pull_request_read` with `get_diff`. The failures came from prompts that named neither a PR and head SHA nor a diff file.

## Rule 1: pin the scope before the reviewer starts

`security.md` "Review Scope Enumeration" gives two paths. Use the first one that fits:

1. Open PR: name the PR number and the exact head SHA. The agent fetches the diff through its GitHub tools. No local file is needed.
2. No PR, or GitHub reads unavailable: write the diff to a file and name the file and the head SHA.

For a pushed head, path 2 looks like this:

```bash
git diff origin/main...<head-sha> > ~/.cache/ai-agents-tmp/review-<pr>-<head-sha>.diff
```

For uncommitted local work, `security.md` path 2 wants a full worktree snapshot instead: `git diff HEAD` plus the untracked files. The three-dot recipe misses both.

A branch name alone is not pinned. The branch can move while the review runs.

## Rule 2: only an independent pass writes a security marker

Write a security review marker only after a reviewer other than the author passed that exact head. An author who writes its own marker is the closed loop the marker exists to break.

PR #6418 shipped with a marker the author wrote for itself. Its dispatch closure check failed open on stale branches. Issue #6472 tracked it, and PR #6488 fixed it.

## Sources

- `.claude/agents/security.md`, `tools:` block and "Review Scope Enumeration".
- PR #6418, PR #6488 (body names three fail-open paths), issue #6472.
- The self-written marker on #6418 comes from the 2026-10-13 post-merge security audit report. It is not restated in a public artifact.
- Related: `decision-agent-self-assessment-does-not-survive-review`.
