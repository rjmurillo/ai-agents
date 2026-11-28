# implementer agent

The `implementer` agent writes production-quality code from an approved plan. It writes tests alongside the code, commits in small steps with conventional messages, and hands back a status, a confidence level, the files changed, and the tests added.

## When to use it

- You have an approved plan, a task list, or acceptance criteria and need the code written.
- You want a fix with a clear root cause applied.
- You want tests written first, then the minimum code that passes them.
- A planner needs the code impact of a feature.

## When not to use it

- Design decisions are still open: use [`architect`](architect.md) instead.
- The cause of a bug is unknown: use [`debug`](debug.md) or [`analyst`](analyst.md) first.
- You want post-implementation polish on code that already works: use [`code-simplifier`](code-simplifier.md) instead.
- You want a slice-by-slice build workflow: use the [`build`](../skills/build.md) skill instead.

## Quick start

> [!WARNING]
> This agent commits as it works. Create a feature branch before you start, so the commits do not land on your default branch.

In Claude Code, start your prompt with the agent name:

```text
implementer: implement the dry-run flag for scripts/export_report.py per .project-toolkit/planning/TASKS-dry-run.md
```

In GitHub Copilot CLI:

```bash
copilot --agent implementer --prompt "implement the dry-run flag for scripts/export_report.py per .project-toolkit/planning/TASKS-dry-run.md"
```

In VS Code or Visual Studio Copilot Chat:

```text
@implementer implement the dry-run flag for scripts/export_report.py per .project-toolkit/planning/TASKS-dry-run.md
```

## What you get

Commits on your branch, plus a handoff to the orchestrator with:

1. A completion status.
2. A confidence level of HIGH, MEDIUM, or LOW with reasoning.
3. The files changed, each with a short description.
4. The tests added, with a count and the coverage change.
5. A recommended next step when an orchestrator delegated the task: `qa` for validation, `critic` for pre-merge review, `security` for sensitive changes, or `architect` if patterns emerged.

| Status | Meaning |
| --- | --- |
| `[COMPLETE]` | The plan tasks are done, tests pass, and commits are made. |
| `[BLOCKED]` | There are no acceptance criteria in the plan or brief, or constraints conflict and need a human. |
| `[SECURITY_FLAG]` | The work meets a stop condition on a security surface. `security` must review first. |
| `[NEEDS_DECOMPOSITION]` | The task is XL or touches more than five files. The agent lists the remaining steps. |
| `[NEEDS_DESIGN_REVIEW]` | A pattern conflict or ADR ambiguity appeared. The agent escalates and does not guess. |

Every completion states `Security Flag: YES` or `NO` with a reason. A YES lists the triggers and files that need review, and the agent records them in `.project-toolkit/planning/implementation-notes-[feature].md`.

## Advanced use

Process for each task:

1. Read the plan, not the chat history.
2. Validate that the task matches the acceptance criteria.
3. Read related files for patterns.
4. Write a failing test, when a test framework exists.
5. Write the minimum code to pass.
6. Refactor toward quality.
7. Commit atomically as `<type>(<scope>): <desc>`.

Before it writes code the agent answers four questions: what the plan specifies, what adjacent code it touches, the top two failure modes, and the smallest implementation that satisfies the criteria. It asks first when the change grows beyond the plan's files.

Evidence rules: every claim in code, comments, tests, or PR text rests on tool output from the session first, then files read in the session, then fetched docs. Training knowledge is only a starting hypothesis. When a docstring says it "matches" or "mirrors" another component, the agent opens that source before the first commit and backs the claim with an import, a conformance test, a generator, or a cited path.

Mirror obligation: before it writes a fix it names the inverse case the fix could break and closes it in the same diff. If the change broadens detection, it adds a no-over-fire check. If it changes a contract, it flips the tests that asserted the old contract.

Quality standards: cyclomatic complexity of 10 or less, methods of 60 lines or less, and no nested code. Test coverage targets are 100 percent for security-critical code, 80 percent for business logic, and 60 percent for docs and glue. It follows SOLID, DRY, and YAGNI, and it does not add features, error handling for impossible cases, or speculative abstractions. It fixes a defect it finds on its path in the same work, and it keeps taste changes out.

Security flagging: the agent runs CWE-22, CWE-78, authorization, and secret-handling checks before coding and before handoff. It stops and returns `SECURITY_FLAG` when a change would weaken or bypass a safeguard, widen a trust boundary, handle credential values, or add path, command, auth, or secret-handling mechanisms. When a change only touches a sensitive surface, it finishes the work and flags it in the handoff.

Project documents: when `.agents/AGENT-INSTRUCTIONS.md` exists, the agent reads the root `AGENTS.md`, that file, `.agents/CLAUDE.md`, and the binding ADRs before it writes code. In a consumer install without that scaffold, it skips the scaffold gates and still reads the root `AGENTS.md` and `CLAUDE.md` when they exist. It stops with `[BLOCKED] Conflicting requirements` when two files disagree.

It commits each verified atomic unit right away. A placeholder such as `TODO` or an empty body counts as unfinished work.

Optional references live in the `build` skill's `references/` folder: `implementer-design-and-errors.md`, `implementer-impact-analysis.md`, and `implementer-estimation.md`. In impact analysis mode, when `milestone-planner` asks, it saves `.project-toolkit/planning/impact-analysis-code-[feature].md`.

A multi-step prompt:

```text
implementer: read .project-toolkit/planning/TASKS-dry-run.md, name the inverse case for each task, write the failing tests first, commit each task separately, and report the security flag and files changed.
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

- [`qa`](qa.md): verifies the implementation with fresh context.
- [`critic`](critic.md): reviews before merge.
- [`security`](security.md): reviews security-flagged changes.
- [`code-simplifier`](code-simplifier.md): refines code after it works.
- [`task-decomposer`](task-decomposer.md): supplies the tasks you implement.
- [`build`](../skills/build.md): the slice-by-slice build workflow.
- Source template: [`implementer.shared.md`](../../templates/agents/implementer.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
