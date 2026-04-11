# PR Review Batching Strategy

## When to Use

When reviewing more than 5 open PRs at once. Sequential handling is too slow. Tier-based batching enables parallel agent dispatch and fastest path to landing.

## Triage Protocol

Before reviewing any PR, run merge readiness checks on ALL open PRs:

```bash
python3 .claude/skills/github/scripts/pr/test_pr_merge_ready.py --owner rjmurillo --repo ai-agents --pull-request {NUMBER}
```

Classify each PR into a tier based on the output:

| Tier | Criteria | Action | Priority |
|------|----------|--------|----------|
| T1 | CI passing, no unresolved threads | Enable auto-merge immediately | First |
| T2 | CI failures only (no threads) | Diagnose CI, fix or re-run | Second |
| T3 | Threads only (CI passing) | Respond to threads, push code fixes | Third |
| T4 | Both CI failures and threads | Fix CI first, then threads | Fourth |
| T5 | Bot PR with validation failures | See renovate race condition memory | Fifth |

## Execution Pattern

1. Launch one agent per tier (not per PR). Tier agents handle their batch internally.
2. Use `isolation: "worktree"` for any agent making code changes.
3. T1 PRs: just enable auto-merge via `set_pr_auto_merge.py`.
4. T2 PRs: get check logs, diagnose, re-run or fix.
5. T3/T4 PRs: get unresolved threads, post replies, then push fixes in worktrees.
6. Process tiers in order. T1 lands first, reducing the queue and potential conflicts.

## Thread Classification

Not all unresolved threads block merge equally:

- **Blocking**: Reviewer requested changes, thread is open. Must fix.
- **Bot-only**: All threads from review bots (CodeRabbit, Copilot, Gemini). Synthesize feedback, push fixes.
- **Stale**: Thread predates last commit. Resolve with "addressed in latest commit."
- **Nit**: Style or formatting. Fix with code change, no discussion needed.

## Required vs Non-Required Checks

Non-required check failures do NOT block merge. Known non-blocking checks:

- "Respond to @rjmurillo-bot" (bot activity)
- "Verify citations" (documentation)
- "Python Security Checks" (security scan, review output only)

## Merge Ordering

When multiple PRs touch the same file (e.g., two Renovate PRs updating the same action), merge the lower PR number first. After it lands, the other may need a rebase.

## Discovery Date

2026-04-10. Developed while reviewing 16 open PRs across 5 tiers.
