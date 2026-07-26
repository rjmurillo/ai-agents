---
paths: "**"
priority: high
---

# Worktree Identity Rule

Before writing any file into a repository, confirm the directory you are writing to is the directory git is tracking. These are not the same thing, and when they diverge git reports success while your changes go nowhere.

This rule exists because `~/repos/ai-agents/.git/config` carried `core.worktree` pointing at a Kanban workspace under `~/.hermes/kanban/boards/ai-agents/workspaces/<id>/work`. Files written into `~/repos/ai-agents` were real on disk, correct in content, and permanently invisible to git. `git status` reported a clean tree throughout, because it was faithfully reporting on the *other* directory. Two rule files and 22 generated outputs landed before the mismatch surfaced, and only then via an unrelated observation.

## The check

Run before the first write, from the directory you intend to edit:

```bash
[ "$(git rev-parse --show-toplevel)" = "$(pwd -P)" ] || echo "MISMATCH"
git config --local core.worktree     # must be empty, or equal to pwd
```

A mismatch means every write from here is invisible to version control. `cd` to the reported toplevel and write there.

## Why `git status` cannot be the confirmation

A clean `git status` is consistent with two states: nothing changed, or git is not observing this directory at all. It cannot distinguish them, so it cannot serve as evidence that a write landed. When a write is expected to produce a diff and `git status` shows none, treat that as a failed probe and investigate the tree identity before re-writing or concluding the write succeeded.

The positive control is a throwaway file:

```bash
: > .probe-$$ && git status --porcelain --untracked-files=all -- .probe-$$ ; rm -f .probe-$$
```

Empty output means git does not see writes in this directory.

## Positive control on the target artifacts

Confirm the files you intend to modify already exist in the tree before editing. A skill, rule, or script that is absent usually means a stale branch or the wrong worktree, not a greenfield. Creating it fresh in that state produces a duplicate that diverges from the real one on `main`.

## Relationship to path resolution

This is the same defect class as a script resolver probing a bare relative path such as `.claude/skills/...`: both assume the current working directory is the repository root, both silently operate on a different tree when that assumption breaks, and both fail open with no diagnostic. See `harness-path-resolution.md`. Anchor on `git rev-parse --show-toplevel` in both cases.
