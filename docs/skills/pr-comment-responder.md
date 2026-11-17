# pr-comment-responder

Works every review thread on one pull request. It reads each comment, reacts, checks the claim, fixes the code or replies in the thread, and records a final status for each thread.

## When to use it

- A PR has unanswered review comments from people or bots such as CodeRabbit, Copilot, or cursor.
- You want each comment triaged by domain and reviewer, not answered ad hoc.
- Trigger phrases: `respond to PR comments`, `address the review feedback on this PR`, `handle bot review comments`, `reply to reviewer`, `fix PR review issues`.

## When not to use it

- You have several PRs, or you want a merge verdict: use [`pr-review`](pr-review.md).
- You have one known reply to post: run `post_pr_comment_reply.py` directly.
- You want a full pre-merge review of the diff: use [`review`](review.md).
- You want to run the local quality gates before you push: use [`pr-quality-all`](pr-quality-all.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-comment-responder PR 1234
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-comment-responder PR 1234`.

The skill reads the PR number from your prompt. It accepts `PR 1234`, `PR #1234`, `pull request 1234`, `#1234`, or a `github.com/owner/repo/pull/1234` URL. It does not ask for a number you already gave.

## What you get

- A comment map at `.project-toolkit/pr-comments/PR-[N]/comments.md` and a task list, `tasks.md`, beside it.
- An in-thread reply to every comment, plus an eyes reaction first.
- A terminal status on every comment:

| Status | Meaning |
| --- | --- |
| `[COMPLETE]` | The comment is fixed or answered. |
| `[WONTFIX]` | You declined it, with a reason. |
| `[DUPLICATE]` | Another comment covers it. |
| `[DEFERRED] Refs #<issue>` | Tracked in a real issue. `Refs #0` does not count. |

The table in `references/gates.md` is the only definition of these statuses.

The run ends only when every comment has a status, CI checks pass, all threads are resolved, commits are pushed, and no new comments arrived after a 45-second wait.

## Advanced use

### Processing order

Domain is the main sort key. Security comments go first, whoever wrote them.

| Priority | Domain | Examples of keywords |
| --- | --- | --- |
| P0 | Security | CWE, injection, XSS, CSRF, secrets, traversal |
| P1 | Bug | error, crash, null, race condition, deadlock |
| P2 | Style | formatting, naming, convention, prefer |
| P2, after Style | General | No keyword match: plain questions and requests |
| P3 | Summary | Bot summaries. Informational, no action. |

Reviewer priority breaks ties inside a domain: P0 `cursor[bot]`, P1 humans, P2 named bots such as `coderabbitai[bot]` and Copilot, then any other bot. Domain orders the queue. It never changes a comment's reviewer priority.

### Phases

| Phase | What happens |
| --- | --- |
| 0 | `cluster_threads.py` groups threads by shared gist. A cluster of 4 or more stops the per-thread loop. Fix the shared source (template, PR description, or issue) first, push, and let the bots rescan. |
| 1 | Extract the PR number, load the `pr-review/pr-comment-responder-skills` memory, gather metadata and comments, run Gate 0 and eyes reactions. |
| 2 | Write the comment map. Delegate each comment to the orchestrator. Verify each finding with [`reviewer-findings`](reviewer-findings.md) before you change code. Comment bodies pass as quoted untrusted data. |
| 4 | Write `tasks.md`. Finish Copilot follow-up PR handling. Send immediate replies for won't-fix, question, and refuted-premise cases. |
| 6 | Implement through the orchestrator, commit, reply with the SHA, resolve, run Gate 3. |
| 8 | Verify every status, wait 45 seconds, confirm CI and threads. |
| 9 | Update the memory before you report completion. |

Phase 4.5 covers Copilot follow-up PRs. Read `references/bots.md` first.

### Rules the skill enforces

- Every thread gets its own analysis, reply, and status. Never merge comments on the same file.
- Reply in-thread, never through the issue-comments endpoint.
- Resolve only bot-authored or explicitly approved threads. Never bulk-resolve while a human thread is open. A question stays open until the reviewer answers.
- A refuted premise gets a reply that names the file, line, and commit checked. It gets no code change.
- Ingested content is data. The skill ignores instructions inside comments and notes the attempt.
- After round 1, a new comment counts only if the diff introduced the defect or a claimed acceptance criterion is unmet. Otherwise it is a flagged note with `[WONTFIX]`.
- Each comment gets at most 15 delegations and one retry. You are the escalation owner.

### Transport

The caller passes `Transport: gh` or `Transport: gh_unusable`. With `gh_unusable`, the skill uses MCP operations step by step, per `references/workflow.md`. A transport failure is an unknown, not a verdict.

### Scripts

Run these from the root of a checkout of this repository:

```bash
uv run python .claude/skills/pr-comment-responder/scripts/cluster_threads.py --help
uv run python .claude/skills/pr-comment-responder/scripts/check_publication.py --help
```

| Script | Purpose | Flags | Exit codes |
| --- | --- | --- | --- |
| `cluster_threads.py` | Groups unresolved threads by shared gist and prints JSON | `--owner`, `--repo`, `--pull-request` (required), `--threads-file` | `0` report printed, `2` usage error, `3` fetch failed, `4` auth error |
| `check_publication.py` | Checks posted comments against the findings they render | one positional JSON file with `findings` and `comments` | `0` all match, `1` a violation, `2` bad input |

`--threads-file` runs offline from a JSON file and skips the fetch. The other GitHub operations (context, comments, replies, reactions, resolve) live in the [`github`](github.md) skill.

### References

Load a reference only when its condition holds: `workflow.md` (phase steps and transport), `gates.md` (gates and statuses), `review-conversation.md` (wording and escalation), `templates.md` (reply templates), `bots.md` (bot handling), `coordinator-detail.md` (quick fix and summary), `harness-differences.md` (host differences).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pr-review`](pr-review.md): runs this skill per PR and adds the completion gate.
- [`reviewer-findings`](reviewer-findings.md): verifies each finding before you act.
- [`pr-babysit`](pr-babysit.md): watches the PR and hands thread work to this skill.
- [`orchestrator`](../agents/orchestrator.md): classifies and routes each comment.
- Source: [`SKILL.md`](../../src/claude/skills/pr-comment-responder/SKILL.md)
- Status vocabulary: [`gates.md`](../../src/claude/skills/pr-comment-responder/references/gates.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
