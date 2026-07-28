# GitHub Reports a False Conflict on the Causal Graph

**Category**: Git Operations
**Source**: 2026-07-28, PR #3636

## Statement

GitHub reports `mergeable: CONFLICTING` on any pull request where both the branch
and `main` touched `.agents/memory/causality/causal-graph.json`, even when the merge
is clean locally. GitHub does not run custom merge drivers. The resolution is to
merge `origin/main` into the branch locally and push the merge commit.

## Why it happens

`.gitattributes:541` assigns that file the `causal-graph` merge driver, registered by
`scripts/maintenance/install_merge_drivers.py` and implemented in
`scripts/validation/merge_causal_graph.py`. The driver resolves the two sides by
content union. It runs only in a local clone that has the driver configured, so
GitHub falls back to a plain three way merge, sees two rewrites of one generated JSON
blob, and reports a conflict.

The generator rewrites the graph on essentially every commit, so both sides of any
long lived branch have touched it. The false conflict is therefore the normal state,
not an edge case.

## Diagnosis

The symptom is a contradiction between local git and the GitHub API:

```bash
git merge-tree --write-tree HEAD origin/main   # exits 0, prints a clean tree OID
gh pr view <n> --json mergeable,mergeStateStatus  # CONFLICTING / DIRTY
```

Confirm with a throwaway worktree before concluding anything:

```bash
git worktree add -q --detach /tmp/mtest HEAD
cd /tmp/mtest && git merge --no-commit --no-ff origin/main
```

Exit 0 with `Automatic merge went well` means the driver resolved it and GitHub is
reporting on a merge strategy you are not using. Confirm the driver is actually the
explanation before acting:

```bash
git check-attr merge -- .agents/memory/causality/causal-graph.json
git config --get-regexp '^merge\.causal-graph\.'
```

Polling does not clear it. Measured on PR #3636: four polls at 30 second intervals,
all `CONFLICTING/DIRTY`, on the correct head SHA.

## Resolution

```bash
git merge origin/main --no-edit
git push
```

The driver runs, the branch becomes a descendant of `main`, and GitHub has nothing
left to reconcile. On PR #3636 the status went to `MERGEABLE` within 40 seconds of
the push. Verify the union actually happened rather than trusting the exit code:
compare node counts across `HEAD`, `HEAD^1`, and `HEAD^2`. The merged graph had 2616
nodes against 2575 on the branch and 2586 on `main`, which is a union. A merged count
at or below either parent means a side was discarded.

## Two wrong turns

`git rebase origin/main` produces a clean history and requires a force push, which is
prohibited. Do not reach for it.

`git checkout origin/main -- .agents/memory/causality/causal-graph.json` takes one
side wholesale and discards every node the branch contributed. Rerunning the
generator does not restore them, because it is incremental and processes only
episodes staged in the current commit, of which a merge has none. The driver
docstring records that 41 of 242 episodes on disk had no node in the committed graph
at the time it was written, and the most recent absences arrived through exactly this
path.

## Related

- [git-merge-preflight](git-merge-preflight.md)
- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md)
- [merge-resolver-auto-resolvable-patterns](merge-resolver-auto-resolvable-patterns.md)
