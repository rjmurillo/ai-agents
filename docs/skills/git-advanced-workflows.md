# git-advanced-workflows

Guides you through rebasing, cherry-picking, bisecting, worktrees, and reflog recovery. It puts a safety branch in place first, so a failed history rewrite is recoverable.

## When to use it

- You manage a complex Git history, work on a shared feature branch, or recover from a repository problem.
- You say `rebase my branch`, `cherry-pick a commit`, `find the breaking commit`, `recover lost commits`, `triage stale worktrees`, or `sync or publish a dirty checkout`.

## When not to use it

- You have merge conflicts against a base branch to resolve: use [`merge-resolver`](merge-resolver.md) instead. It points back here for rebase, cherry-pick, bisect, or worktree work.
- You want to commit, push, and open a PR: use [`push-pr`](push-pr.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:git-advanced-workflows`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the git-advanced-workflows skill to squash the fixup commits on feature/user-auth and push with a pinned lease.
```

The agent checks `git status` and the recent log, creates a `backup-<timestamp>` branch, runs the workflow, and verifies the result. You end with a clean tree and a history that matches what you asked for.

## What you get

Git commands run against your repository and a checked result. The skill confirms:

- The working tree is clean.
- `git log --oneline` matches what you expect.
- Tests pass after any history rewrite.
- A force push used `--force-with-lease=<ref>:<sha>` pinned to an observed SHA.
- Worktrees it created are removed.

## Advanced use

The skill works in three phases: assess the situation, run the workflow, verify and clean up. Phase 1 creates the safety branch before any destructive step.

| Workflow | What the skill covers |
| --- | --- |
| Rebase | Interactive rebase, `--autosquash` with `git commit --fixup`, splitting a commit, and a force push pinned to the remote SHA you recorded before rewriting. |
| Cherry-pick | Apply a hotfix to several release branches, and pick only specific files with `git restore --source`. |
| Bisect | Manual `git bisect`, and `git bisect run ./test.sh` (exit `0` good, `125` skip, other non-zero bad). |
| Worktrees | Add, remove, and prune worktrees. Move a worktree and repair its `.venv`. |
| Publish from a dirty checkout | Move only the requested paths to a clean topic branch in a new worktree, byte-compare them, and push the topic branch. |
| Sync a dirty checkout | Commit local work, measure divergence with `git rev-list --left-right --count`, and rebase a private branch or merge a shared one. |
| Recovery | `git reflog`, `git reset`, `git restore`, and the `--abort` commands. |
| Worktree triage | Decide whether a dirty worktree is live or abandoned, and anchor an unreachable tip before removal. |

Key rules from the skill:

- Do not rebase shared branches. Merge them.
- Never use bare `--force` or bare `--force-with-lease`. A fetch can move the lease's expected value.
- Do not use `git stash` with several live worktrees. Every worktree shares one stash. Commit WIP on your own branch.
- Do not use `--autostash`, for the same reason.
- During a rebase, `--ours` is the branch you rebase onto and `--theirs` is your commit. This is the reverse of a merge.
- Anchor a worktree tip with `git update-ref refs/salvage/<slug> <sha>` and a bundle before `git worktree remove`.

After you move a worktree, `uv` launchers in `.venv` keep stale paths. Repair them from the root of a checkout of this repository:

```bash
uv run python scripts/maintenance/repair_worktree_venv.py --help
```

The skill has no scripts of its own. The worktree triage procedure lives in [`worktree-triage.md`](../../src/claude/skills/git-advanced-workflows/references/worktree-triage.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`merge-resolver`](merge-resolver.md): resolves merge conflicts, and points here for rebase and worktree work.
- [`push-pr`](push-pr.md): commits, pushes, and opens a PR.
- [`github`](github.md): GitHub PR and issue operations.
- Source: [`SKILL.md`](../../src/claude/skills/git-advanced-workflows/SKILL.md)
- Reference: [`worktree-triage.md`](../../src/claude/skills/git-advanced-workflows/references/worktree-triage.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
