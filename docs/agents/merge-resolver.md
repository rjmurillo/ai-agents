# merge-resolver agent

The `merge-resolver` agent resolves git merge conflicts by reading commit history, code intent, and pull request metadata. It hands back resolved, staged files and a report with a confidence score for each file.

## When to use it

- A pull request has conflicts with its base branch.
- A rebase failed on conflicts.
- Conflicts need a systematic, per-file strategy instead of a manual pass.

## When not to use it

- Your session cannot run shell commands: the agent returns `[BLOCKED]` because it needs `git`, worktree creation, and `git push`. Run it where the orchestrator has shell access.
- You want the workflow as a skill: use the [`merge-resolver`](../skills/merge-resolver.md) skill instead.
- You want a code change, not a conflict resolution: use [`implementer`](implementer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
merge-resolver: resolve the conflicts on PR 123 against main
```

In GitHub Copilot CLI:

```bash
copilot --agent merge-resolver --prompt "resolve the conflicts on PR 123 against main"
```

In VS Code or Visual Studio Copilot Chat:

```text
@merge-resolver resolve the conflicts on PR 123 against main
```

## What you get

After shell-backed resolution finishes, the agent writes a report that lists:

- Files resolved, split into auto and manual.
- The strategy applied per file.
- A confidence score: High, Medium, or Low.
- The resolution rationale.
- Files flagged for manual review.

| Confidence | Criteria | Action |
| --- | --- | --- |
| High | Auto-resolvable pattern, or a single-side change | Resolve automatically |
| Medium | Both sides changed, clear intent difference | Resolve with rationale |
| Low | Both sides changed the same logic, unclear intent | Flag for manual review |

## Advanced use

Phase 0 is a blocking check. If the run cannot execute shell commands, the agent returns `[BLOCKED]` with a one-line reason and stops. It does not write a plan. It marks a phase complete only when a tool result in the run proves it ran.

The agent sorts each conflicted file into one of three classes:

| Class | Files | Handling |
| --- | --- | --- |
| Auto-resolvable | `.agents/*` (modify/modify only), `.serena/*`, `templates/*`, lock files, generated `src/copilot-cli/*` and `src/vs-code-agents/*`. Claude Code also adds `.claude/skills/*`, `.claude/agents/*`, and `src/claude/*`. Copilot CLI and VS Code add all of `.claude/*`. | Accept the base branch version |
| Rename, never content-merge | Add/add conflicts in `.project-toolkit/sessions/*`, `.project-toolkit/qa/*`, `.project-toolkit/retrospective/*` | Keep both files. Accept base at the original name, rename the head version with a suffix, and update references. |
| Manual | Source code, configuration with semantic meaning, tests, documentation with substantive changes | Analyze intent, then resolve |

For manual files it ranks intent from `git blame` and commit messages: security patch, bugfix, breaking change, change with tests, recent change, then style. Resolution rules include: different sections combine both, a superset wins, a bugfix beats a feature, and the more tested logic wins.

Constraints: session files from main are immutable audit records, lock files take the base version and are regenerated, generated files are fixed in their source and regenerated, and files outside the conflict scope stay unchanged.

A multi-step prompt:

```text
merge-resolver: fetch PR 123 metadata, list every conflicted file by class, resolve them, verify no conflict markers remain, and report confidence per file.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`merge-resolver`](../skills/merge-resolver.md): the skill form of this workflow.
- [`orchestrator`](orchestrator.md): routes conflict work to this agent and supplies shell access.
- [`implementer`](implementer.md): handles code changes beyond conflict resolution.
- Source template: [`merge-resolver.shared.md`](../../templates/agents/merge-resolver.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
