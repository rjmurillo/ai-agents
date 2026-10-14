# Read-only reviewers need a pinned diff file, and a marker needs an independent pass

## What happened

[2026-10-14] Security reviews handed to the `security` agent came back with "scope not pinned". The agent has no shell. Its `tools:` list in `.claude/agents/security.md` (line 30 onward) names Read, Grep, Glob, web tools, Write, GitHub MCP reads, and Serena. It has no Bash, so it cannot run `git diff` and cannot tell which head it is reviewing.

## Rule 1: hand over the diff as a file

Before a read-only reviewer starts, write the diff to a file and name the exact head SHA in the prompt:

```bash
git diff origin/main...<head-sha> > ~/.cache/ai-agents-tmp/review-<pr>-<head-sha>.diff
```

Tell the reviewer the file path and the head SHA. A diff pasted from memory or a branch name is not pinned. The branch can move while the review runs.

## Rule 2: only an independent pass writes a security marker

Write a security review marker only after a reviewer other than the author passed that exact head. An author who writes its own marker is the closed loop the marker exists to break.

PR #6418 shipped with a marker the author wrote for itself. Its dispatch closure check failed open on stale branches. Issue #6472 tracked it, and PR #6488 fixed it.

## Sources

- `.claude/agents/security.md`, `tools:` block.
- PR #6418, PR #6488 (body names three fail-open paths), issue #6472.
- 2026-10-14 post-merge security audit (see `pr-review/triage-004-single-pass-close-verdicts-need-skeptic`).
- Related: `decision-agent-self-assessment-does-not-survive-review`.
