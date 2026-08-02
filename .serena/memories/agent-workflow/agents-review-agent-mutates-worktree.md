# A Review Agent Pointed At A Live Worktree Will Change Its Branch

**Atomicity**: 95%
**Category**: Agent Orchestration
**Source**: 2026-08-02 fleet session, worktree `wt-pushmsg`

## Statement

A sub-agent given a worktree path as its review target treats that worktree as
its own sandbox. It will check out other branches, stage files, and leave scratch
behind. Re-read `git branch --show-current` and `git status` in any worktree you
handed to an agent before you commit in it again.

## Context

Adversarial review works best when the reviewer can run the code, so the natural
prompt hands over a real path. The reviewer then does exactly what it was asked:
to test whether a snippet behaves correctly when run from a different branch, it
checks out that different branch.

Nothing warns you. The agent reports its findings, not its side effects, and the
findings are usually good enough that you act on them immediately, which is the
moment you are least likely to re-check the tree.

The dangerous shape is committing next. The worktree is sitting on `main` with
staged files you did not stage. A `git add -A` and commit there puts a reviewer's
scratch onto `main`, in a repo whose branch policy forbids committing to `main`.

## Evidence

Measured 2026-08-02. A `code-review` agent was given `/home/richard/wt-pushmsg`
and the branch `docs/push-success-message`. On completion:

```
$ git branch --show-current
main
$ git status --short
A  non_md_file.txt
A  test.md
$ git reflog -2
05a4a5677 HEAD@{0}: checkout: moving from docs/push-success-message to main
4b538ef1f HEAD@{1}: commit: docs(memory): record that pre_pr success is not a push
```

The agent's own report named the cause without flagging it as a mutation: "I ran
this sequence while checked out on `main`, pushing the branch `$b`". That
experiment produced a correct BLOCKING finding. It also left the tree switched.

Nothing was lost. The branch ref and the commit both survived, and `git checkout`
restored the state. The cost is entirely in what happens if you do not look.

## Remedy

After any agent that was given a worktree path, before touching it:

```bash
cd "$WT" && git branch --show-current && git status --short
```

Restore with `git checkout <branch>`, then clear reviewer scratch with
`git rm --cached` plus `rm` for anything you did not create. Confirm
`git status --porcelain` is empty before staging your own work.

Prefer giving reviewers a throwaway worktree at the same commit when the review
involves running state-changing git commands. The branch under review is
recoverable, but a clean separation removes the check entirely.

## Scope

Applies to any sub-agent with shell access and a path, not only review agents.
The trigger is handing over a live working tree, not the agent's role.
