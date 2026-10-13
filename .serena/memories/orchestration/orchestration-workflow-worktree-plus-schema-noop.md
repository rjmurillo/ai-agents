# Isolated Worktree Agent With A Schema Can No-Op (Observed)

## Statement

In the Workflow tool, `agent({isolation: 'worktree', schema})` can complete as a
no-op. No worktree is created, and the forced StructuredOutput returns without
the work done.

## Do this instead

- Preferred: have the agent create its own worktree under
  `~/worktrees/ai-agents/<branch-slug>`, with `/` in the branch replaced by `-`
  (`feat/login-redirect` becomes `feat-login-redirect`). Start the agent prompt
  with `git rev-parse --show-toplevel`. If the path is not under `/worktrees/`,
  the agent creates its branch and worktree immediately. This guard catches the
  no-op before the report does.
- Alternative: call the direct Agent tool with `isolation: "worktree"` and no
  schema, and ask for a plain-text report between `=== REPORT ===` and
  `=== END ===` lines. Parse that block. This puts worktrees under
  `.claude/worktrees/agent-*`, inside the checkout, which
  `git/git-never-place-worktrees-inside-the-checkout.md` warns against. Clean up
  after each wave with `git worktree remove .claude/worktrees/agent-* --force`
  and `git worktree prune`, scoped to the run's own prefix.

## Check before trusting a result

A schema-valid return is not proof of work. Confirm the worktree is listed by
`git worktree list`. Confirm the branch has commits: `git log --oneline main..<branch>`
must print at least one line. A worktree can exist with zero commits after a
partial run.

## Evidence

Observed in a prior session, not re-run for this memory. It is runtime behavior
of the Workflow tool, so no repository file proves it.

- Source: Hindsight page "Multi-agent run playbook"
  (kp-5ad73a597d6a4cb69a6a3dd731fad139), bank `coding-agent::rjmurillo::ai-agents`.
  The page ID does not resolve in the default bank.
- No-op claim: REF-IDs d2634227, 9da94c81.
- Direct Agent tool with no schema and the report block: REF-ID 88a75954.
- Worktree root `~/worktrees/ai-agents/`: REF-ID 89c57505.
- Start-of-agent toplevel guard: REF-ID 41f6c6e7.
- Cleanup command for `.claude/worktrees/agent-*`: REF-ID f66c487c.
- Verified 2026-10-13: the cited REF-IDs appear on the page. The page does not tie
  any of this to the 2026-10-12 sweep, so this memory does not claim that.
