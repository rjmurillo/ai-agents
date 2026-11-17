# merge-resolver

Resolves merge conflicts on a PR or branch by reading git history and commit intent. It auto-resolves known file patterns, flags the rest for manual work, checks that no conflict markers remain, then commits and pushes.

## When to use it

- A PR has conflicts with its base branch and you want them resolved.
- A branch will not merge because of conflicts.
- Trigger phrases: `resolve merge conflicts`, `fix conflicts on this branch`, `PR has conflicts with main`, `can't merge due to conflicts`, `resolve PR conflicts`.

## When not to use it

- You need a rebase, a cherry-pick, or a history rewrite: use [`git-advanced-workflows`](git-advanced-workflows.md) instead.
- You want to decide whether an old PR still belongs before you update it: use [`modernize`](modernize.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:merge-resolver`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the merge-resolver skill to resolve the conflicts on PR 123 (branch fix/my-feature) against main.
```

The skill checks that it has shell access first. If it does not, it returns `BLOCKED` and routes the work back to the orchestrator. It does not write a plan in place of doing the work. Otherwise it fetches the PR, attempts the merge, resolves what it can, validates, commits, and pushes. You see a JSON result listing resolved and blocked files.

## What you get

`resolve_pr_conflicts.py` prints JSON:

```json
{
  "success": true,
  "message": "Successfully resolved conflicts for PR #<number>",
  "files_resolved": [".agents/governance/PROJECT-CONSTRAINTS.md"],
  "files_blocked": []
}
```

| Exit code | Meaning |
| --- | --- |
| 0 | No conflicts, or conflicts auto-resolved (and pushed, unless `--dry-run`) |
| 1 | Conflicts could not be auto-resolved, a git command failed, or the repo lookup failed |
| 2 | No plugin lib directory carries `github_core` |

With `--dry-run`, exit 0 means the conflicts were fully auto-resolvable. Nothing was changed.

`verify_no_conflict_markers.py` checks for unmerged files and leftover markers:

| Exit code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Markers remain or unmerged files exist |
| 2 | Not inside a git working tree |
| 3 | A git command failed |

## Advanced use

### Phases

1. **Capability check (blocking).** Confirm shell access. A phase counts as complete only when a tool result in this run proves it ran.
2. **Context gathering.** Fetch PR metadata, check out the branch, attempt a merge with `--no-commit`, list conflicted files.
3. **Analysis and resolution.** Classify files, auto-resolve known patterns, run `git blame` on manual files, apply resolutions, stage.
4. **Validation (blocking).** Run `verify_no_conflict_markers.py`, the session validator, and markdown lint. Commit and push.

### Intent priority

When two sides conflict, the higher-priority intent wins and the other change is reapplied around it. Security is never dropped.

| Intent | Priority |
| --- | --- |
| Security | 1 (highest) |
| Bugfix | 2 |
| Feature or refactor | 3 |
| Style | 4 (lowest) |

Within one tier, combine the changes if you can. Otherwise prefer the better-tested change, then the more recent one.

### Auto-resolved paths

The script accepts the target branch version for paths such as `.project-toolkit/*`, `.agents/*`, `.serena/*`, `templates/*`, `src/claude/*`, `.claude/agents/*`, `.github/agents/*`, `.github/prompts/*`, and the lock files `package-lock.json`, `yarn.lock`, and `pnpm-lock.yaml`. Plugin manifests (`*/.claude-plugin/plugin.json`) get a special rule. When the sides differ only in `version`, the script resolves it. Any other difference blocks auto-resolution.

> [!WARNING]
> An add/add conflict on an append-only record (session logs, QA reports, retrospectives) is never auto-resolved. The file lands in `files_blocked` and the run exits 1. Keep both files: accept the base version at the original name and rename your branch's version with a distinguishing suffix. Never merge the contents of two such records into one file.

### Scripts

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py --help
uv run python .claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py --help
```

`resolve_pr_conflicts.py` takes `--owner`, `--repo`, `--pr-number`, `--branch-name`, `--target-branch`, `--worktree-base-path`, and `--dry-run`. `--pr-number` and `--branch-name` are required. `verify_no_conflict_markers.py` takes `--cwd` and `--json`. Branch name validation blocks command injection, and worktree path validation blocks path traversal.

To add an auto-resolvable pattern, edit `AUTO_RESOLVABLE_PATTERNS` in `resolve_pr_conflicts.py`. To add a strategy for a domain-specific conflict, add an entry to `references/strategies.md`.

### Chaining

[`pr-autofix`](pr-autofix.md) sends `DIRTY` PRs here. The `merge-resolver` agent runs the same workflow. [`modernize`](modernize.md) does not hand its rebase conflicts to this skill, because this skill merges, commits, and pushes without modernize's consent and pinned-lease steps.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | No |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`merge-resolver` agent](../agents/merge-resolver.md): the agent form of this workflow.
- [`git-advanced-workflows`](git-advanced-workflows.md): rebases, cherry-picks, and history rewrites.
- [`modernize`](modernize.md): decide whether an aging PR should be updated at all.
- [`pr-autofix`](pr-autofix.md): triages PRs and routes `DIRTY` ones here.
- Source: [`SKILL.md`](../../src/claude/skills/merge-resolver/SKILL.md)
- Reference: [`strategies.md`](../../src/claude/skills/merge-resolver/references/strategies.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
