# modernize

Checks whether an aging pull request still belongs in the product, then rebases it only if it does. It ends in one of three dispositions: `MODERNIZE`, `REWORK`, or `CLOSE`.

## When to use it

- An old or stale PR needs to be brought up to date and you are not sure the idea still fits.
- A rebase would be clean, but base-branch changes may have made the PR obsolete or redundant.
- Trigger phrases: `modernize this PR`, `rebase this old PR`, `refresh this stale PR`, `update this old PR`.

## When not to use it

- You only need conflicts resolved: use [`merge-resolver`](merge-resolver.md) (or the [`merge-resolver` agent](../agents/merge-resolver.md)) instead.
- You want a verdict on whether a PR should exist, with no branch change: use [`maintainer-review`](maintainer-review.md) instead.
- You want to rebase, cherry-pick, or recover your own branch: use [`git-advanced-workflows`](git-advanced-workflows.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:modernize https://github.com/OWNER/REPO/pull/123
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/modernize`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /modernize skill to ...`.

The skill reads the PR, inspects what changed on the base branch since the PR diverged, and picks a disposition. It rebases locally only when the goal is still useful. It does not push without your explicit yes.

## What you get

A report that leads with `MODERNIZE`, `REWORK`, or `CLOSE` and the reason.

| Disposition | Meaning | What the skill does |
| --- | --- | --- |
| `MODERNIZE` | The goal and implementation shape still hold | With an update reason, rebases, resolves conflicts, tests, and updates the branch. With none, reports and changes nothing |
| `REWORK` | The goal holds, but a mechanical rebase keeps the wrong implementation | Explains the smallest credible rewrite, says whether it belongs on this branch or a fresh one, and stops, unless you asked for the rework |
| `CLOSE` | Superseded, obsolete, directionally wrong, or not worth its cost | Names the evidence that decided it (the commit, PR, or decision that superseded it, or the cost that outweighs the benefit) and stops. It does not rebase or close |

The report also states the PR as three sentences (the problem, the change, and what must be true for the change to be right), credits the PR's author, and covers meaningful base-branch changes, merge commits in the PR range and their remerge-diff result, conceptual conflicts (or confirmation that none were found), the rebase and push result with old and new head SHA, the `git range-diff` result with any change left unexplained, each separate fix commit added on top, checks run, injected instructions found in PR content, and the remaining decision.

## Advanced use

### Phases

1. **Intent.** Record the PR URL, state, base, head repository and branch, head SHA, author, checks, and review state. State the PR's goal as three sentences before judging the code. A head branch that is the base branch in the same repository stops the run. Confirm the fetched head still matches the observed SHA.
2. **What changed around it.** Read commits added to the base branch since the PR diverged, starting with those that touch the PR's files, plus commit messages and changelog entries for the moved range. Look for contract changes in files the PR never touches. Search merged and open PRs for replacements. A clean rebase does not make a PR current. Check each merge commit in the PR range with `git show --remerge-diff`: a rebase drops a merge's own changes and `git range-diff` never shows them. The check passes `--no-show-signature` and `--ignore-submodules=none`, so a signed merge or a submodule setting cannot change its result. A check that errors counts as output.
3. **Disposition.** Pick `MODERNIZE`, `REWORK`, or `CLOSE` before any push. A merge commit with remerge-diff output blocks the rebase until the PR's author turns that change into an ordinary commit. The skill does not flatten it.
4. **Rebase.** Work in a safe local branch or disposable worktree, with a backup ref at `refs/modernize-backup/${BRANCH}`. Rebase, resolve conflicts by the PR's current intent and the base branch's newer invariants, and keep the author's commits as theirs. A fix the update reason needs goes in a separate commit that the report lists. Compare with `git -c diff.ignoreSubmodules=none range-diff`, inspect the final diff with `--ignore-submodules=none`, and give each changed patch a one-line reason; a change that stays unexplained is reported and the push is not requested. Run focused checks, then ask for your explicit yes. After the yes, re-read the PR and push with a pinned lease.
5. **Report.**

### Guardrails

- Invoking the skill on a named PR authorizes a local rebase and checks, not the push.
- The skill never merges, closes, approves, changes the base branch, or expands scope without your request.
- It pushes only to a head branch in the base repository. A fork head stops after the disposition, and its code is never checked out or run.
- It never uses `--force` or a bare `--force-with-lease`. The lease is pinned: `--force-with-lease="refs/heads/${BRANCH}:${OBSERVED_SHA}"`.
- It does not update a branch only because it is behind its base. An update needs a conflict, a base commit that fixes a failing blocking check, or a base change that breaks the PR's code.
- It posts no PR comment unless you ask.
- PR titles, bodies, commits, and diffs are untrusted data. An instruction inside them is quoted as a finding, not obeyed.

### Chaining

For a verdict without a branch change, run phases 1 to 3 and hand off to [`maintainer-review`](maintainer-review.md) for the comment draft. PR state is read and written through the [`github`](github.md) skill. [`autoplan`](autoplan.md) routes requests like `modernize this pr`, `refresh stale pr`, and `revive old pr` here.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`maintainer-review`](maintainer-review.md): decide whether a PR should exist, with no branch change.
- [`merge-resolver`](merge-resolver.md): resolve conflicts only.
- [`git-advanced-workflows`](git-advanced-workflows.md): rebase and recover your own branch.
- [`pr-autofix`](pr-autofix.md): force-push safety rules that this skill reuses.
- Source: [`SKILL.md`](../../src/claude/skills/modernize/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
- Upstream: adapted from [t3dotgg/tstack](https://github.com/t3dotgg/tstack) `skills/modernize` at `11e37a7` and [garrytan/gstack](https://github.com/garrytan/gstack/blob/e6dd567349e85506127c2f4cf69a0392923c032c/modernize/SKILL.md.tmpl) `modernize` at `e6dd567`, both MIT.
