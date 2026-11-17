# Agents and skills

The toolkit gives you two kinds of building blocks: agents and skills. This page explains what each one is, how they differ, and how they work together. For the syntax to call them, see [Call agents and skills](call-agents-and-skills.md).

## Agents are specialists

An agent is a role with its own instructions, such as `analyst`, `architect`, or `qa`. When you hand an agent a task, the host runs it as a subagent with its own context window. The agent does the work and returns one result to you or to the agent that called it.

Agents are good at judgment within a role. The `critic` agent reads a plan and returns a verdict. The `security` agent threat-models a change. The `orchestrator` agent splits a large job and hands each part to the right specialist.

Some agents can use only a fixed list of tools. For example, `analyst` reads and searches but does not edit files. This keeps a research agent from changing your code.

Browse them in [Agents](agents/README.md).

## Skills are workflows

A skill is a folder with a `SKILL.md` file. The file holds steps, checks, and stop conditions for one kind of task. Many skills also ship scripts and reference files.

A skill runs in the current conversation. It does not get a new context window. It tells the agent that is already working what to do, in what order, and how to prove it worked.

Skills start in one of two ways:

- **By slash command.** Some skills, such as `spec` and `review`, start when you type their name. Their `SKILL.md` sets `user-invocable: true`. Claude Code takes `/project-toolkit:spec` after a plugin install. In Copilot CLI, you name it with a slash in your prompt, such as `Use the /spec skill to ...`.
- **By match.** The host shows the agent each skill's name and description. When your request matches, the agent loads the full skill. You can also name the skill in your request to make sure it loads. In Claude Code, any plugin skill also starts with `/project-toolkit:<name>`.

Browse them in [Skills](skills/README.md).

## How they differ

| | Agent | Skill |
| --- | --- | --- |
| What it is | A role with its own instructions | A workflow with steps, checks, and often scripts |
| Where it runs | In its own context window | In the current conversation |
| How it starts | You name it, or another agent calls it | A slash command, a match on its description, or you name it |
| What it returns | One result, such as a verdict, plan, or report | Whatever its steps produce: files, a pull request, a report |
| Best for | Judgment from one point of view | Repeating a task the same way every time |

## How they work together

Agents use skills, and skills call agents.

- The `review` skill picks review axes for your branch, then hands them to agents such as `analyst` and `security`.
- The `orchestrator` agent can route a lifecycle request through the `spec` skill, then through agents like `milestone-planner`, `critic`, `implementer`, and `qa`.
- The `autoplan` skill reads a request that names no skill and picks the destination: a skill, a lifecycle command, or an agent chain.

If you are not sure which to use, start with `autoplan` (in Claude Code, `/project-toolkit:autoplan`). It makes the choice and tells you what it picked.

## The lifecycle

Six skills form the path from an idea to a pull request:

```text
/spec -> /plan -> /build -> /test -> /review -> /ship
```

Each one calls the agents it needs. You can run them in order, skip the ones a small change does not need, or let `autoplan` decide. See [Lifecycle commands](workflow-commands.md) and the walk-through in [Take one change from /spec to /ship](training/lifecycle-and-autoplan.md).

## Shipped and repository-only skills

Most skills ship in the `project-toolkit` plugin and work in any repository. The skills that exist only under `.claude/skills/` in a checkout of `rjmurillo/ai-agents` do not ship. These are the `repository-*` skills and every `ai-agents-*` skill except `ai-agents-external-claims`, which ships in the plugin. They help people who maintain the toolkit itself. The [Skills](skills/README.md) index lists them in their own section.

## Where they come from

You do not edit the agent or skill files a host loads. The build renders them from sources:

- Agents come from `templates/agents/<name>.shared.md`.
- A skill's `SKILL.md` comes from `templates/skills/<name>.SKILL.md.tmpl`. Its scripts and reference files live in `src/claude/skills/<name>/`.

The reference pages under `docs/agents/` and `docs/skills/` are written by hand. When you change a `SKILL.md`, an agent template, or a script's flags, update the matching page in the same pull request.

The build writes a copy for each host, such as Claude Code, Copilot CLI, Codex, Cursor, and Muse. See [Change a rule and a skill through templates](training/template-first-authoring.md) to make a change.

## Next

- [Call agents and skills](call-agents-and-skills.md): the syntax for your host.
- [When to use the lifecycle commands](when-to-use.md): which lifecycle steps a task of your size needs.
