# generator-pipeline

Holds the rules for editing generated files and their templates. Agents, rules, skills, hooks, and settings render from `templates/` through `build_all.py`. You edit the source, never the output.

## When to use it

- You are about to edit a file under `templates/`.
- You are about to change a generator under `build/scripts/`.
- You found a file that a generator writes and want to change it.

## When not to use it

- You want to run Azure DevOps pipelines: use [`pipeline-validator`](pipeline-validator.md).
- You want to write a skill's content: use [`skillforge`](skillforge.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:generator-pipeline`. To ask for it by name, say:

```text
Use the generator-pipeline skill before I edit the build skill template.
```

## What you get

The source file to edit, the build command, and a check that the output is current. A second `build_all.py` run must leave `git status` clean.

## Advanced use

[`rule-generated-artifacts.md`](../../src/claude/skills/generator-pipeline/references/rule-generated-artifacts.md) holds the full rule for customer-facing artifacts and their runtime contract. Template grammar stays in the `templates` path rule.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`build`](build.md): routes here when an edit touches a template.
- [`skillforge`](skillforge.md): skill authoring.
- Source: [`SKILL.md`](../../src/claude/skills/generator-pipeline/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
