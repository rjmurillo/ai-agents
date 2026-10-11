# Plan, implement, and review code with a team of AI agents in Claude Code and Copilot CLI

In Claude Code, you can use built-in subagents or the experimental Agent Teams feature, or install a toolkit that defines planner, implementer, and reviewer roles for you. In GitHub Copilot CLI, you define custom agents as `.agent.md` files and pick them with `/agent` or `--agent`. AI Agents packages both: an orchestrator routes work from analyst and architect through implementer to critic, QA, and security, in both CLIs.

This page shows three ways to set that up. Pick one with the [comparison table](#which-to-use).

Facts on this page were checked on 2026-10-11 against the linked vendor docs, Claude Code 2.1.296, and Copilot CLI 1.0.95. Agent Teams changes often. Trust the vendor page over this one when they differ.

## Option 1: Claude Code Agent Teams (built in, experimental)

An agent team is several Claude Code sessions that work together. One session is the lead. The others are teammates. Each teammate has its own context window, and teammates message each other directly. The [Agent Teams documentation](https://code.claude.com/docs/en/agent-teams) is the authority for everything in this section.

Agent Teams differ from [subagents](https://code.claude.com/docs/en/sub-agents). By default, a subagent does a task in its own context and returns the result to the caller, and the main agent manages all the work. Teammates message each other directly and coordinate through a shared task list.

### Enable it

Agent Teams are off by default. Set one environment variable in your shell or in `settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Teammates only spawn in an interactive session. With the `-p` flag, Claude Code runs a named helper as an ordinary subagent.

### Spawn a planner, an implementer, and a reviewer

Describe the team in plain language. Name each teammate so you can address it later.

```text
Spawn three teammates. Name them planner, implementer, and reviewer.
The planner writes a plan for adding rate limiting to the API. It edits no code.
The implementer waits for the plan, then writes the code and the tests.
The reviewer reads the diff for missing tests and security problems. It edits no code.
```

Teammates do not see the lead's conversation history. Put the task details in the spawn prompt.

### Hold a teammate to a plan first

Switch the lead into [plan mode](https://code.claude.com/docs/en/permission-modes#analyze-before-you-edit-with-plan-mode) before you ask for a teammate. A teammate spawned that way works read-only until its plan is ready.

Know one limit. Claude Code approves the teammate's plan in the lead's session as soon as the request arrives. The lead does not review it. The teammate's edits and commands still go through permission prompts in the lead session. Those prompts are your gate.

You cannot set a permission mode per teammate at spawn time. You can change one teammate's mode after it starts.

### Add review gates

Three [hooks](https://code.claude.com/docs/en/hooks) let you block work that is not done. Each one blocks when your script exits with code 2.

| Hook | Fires when |
|------|------------|
| `TeammateIdle` | A teammate is about to go idle |
| `TaskCreated` | A task is being created |
| `TaskCompleted` | A task is being marked complete |

### Limits

The documentation lists these limits, among others:

- `/resume` and `/rewind` do not restore in-process teammates.
- A session has one team. You cannot share a team across sessions.
- Teammates cannot spawn their own teammates.
- Task status can lag, which blocks dependent tasks.

Cost is a separate point. The same page says a team uses more tokens than a single session, because each teammate is a separate Claude instance.

## Option 2: Copilot CLI custom agents

A Copilot CLI custom agent is a Markdown file with the `.agent.md` extension. You write one file per role. When Copilot delegates to a custom agent, the work runs in a subagent with its own context window.

### Where the files go

| Scope | Location |
|-------|----------|
| One repository | `.github/agents/` |
| All your projects | `~/.copilot/agents/` |

Source: [Creating custom agents for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli).

### Write a reviewer agent

Save this as `.github/agents/reviewer.agent.md`:

```markdown
---
name: reviewer
description: Reviews a diff for missing tests and security problems. Read-only. Use after the implementer finishes a change.
tools: ["read", "search"]
---

You review code changes. You did not write them.

Read the diff and the files it touches. Report each problem with a file path, a line number, and the reason it matters. Check that new behavior has a test. Check input handling, secrets, and authorization paths.

Do not edit files. If the change is clean, say what you checked.
```

`description` is the only required field. `name` and `tools` are optional. Leave `tools` out and the agent gets every tool. The `read` and `search` aliases keep this reviewer from editing files. The [custom agents configuration reference](https://docs.github.com/en/copilot/reference/custom-agents-configuration) lists every field and tool alias.

Write a planner and an implementer the same way. Restart the CLI to load new agent files.

### Run the agents

Pick an agent in an interactive session:

```text
/agent
```

Or name the agent at launch. Use the file name without `.agent.md`:

```shell
copilot --agent reviewer --prompt "Review the changes on this branch"
```

You can also name the agent in your prompt, for example "Use the reviewer agent on src/api".

### Plan first, then run agents in parallel

Copilot CLI has two built-in features that turn single agents into a team.

- **Plan mode.** Press `Shift`+`Tab` to cycle modes, or start with `copilot --plan`. In plan mode, Copilot builds a plan before it writes code.
- **Fleet mode.** The `/fleet` command breaks a plan into subtasks and runs them on subagents, in parallel where the subtasks allow. Name a custom agent for a subtask with `@AGENT-NAME`.

```text
/fleet Implement the plan. Use @implementer for the code and tests. Use @reviewer to review the diff when the code is done.
```

Fleet mode helps when subtasks are independent. The [fleet documentation](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet) says a task that is sequential by nature may see no benefit, and that subagents can use more GitHub AI Credits.

## Option 3: a ready-made team with AI Agents

AI Agents ships the roles so you do not write them. One install gives you 30 agents in either CLI, including orchestrator, analyst, architect, milestone-planner, implementer, critic, qa, and security.

### Install

Run these inside the CLI session.

**Claude Code:**

```text
/plugin marketplace add rjmurillo/ai-agents
/plugin install project-toolkit@ai-agents
```

**GitHub Copilot CLI:**

```text
/plugin marketplace add rjmurillo/ai-agents
/plugin install project-toolkit@ai-agents
```

The same commands work from a regular shell as `claude plugin ...` and `copilot plugin ...`. The plugin's hooks need Python 3.10 or newer. Without it, hooks are skipped with a warning. See the [installation guide](installation.md) for other install paths.

### The flow in Claude Code

Six lifecycle skills cover the path from idea to pull request: spec, plan, build, test, review, and ship. Claude Code [namespaces a plugin's skills](https://code.claude.com/docs/en/plugins) with the plugin name. After a marketplace install, type the full form:

```text
/project-toolkit:plan Add rate limiting to the API
/project-toolkit:build
/project-toolkit:review
```

`plan` writes milestones, sized tasks, a dependency graph, and a risk register. `build` works test-first and commits in small slices. `review` returns a final verdict, a verdict per review axis, and findings with file and line locations. The [workflow commands reference](workflow-commands.md) covers all six.

### The flow in Copilot CLI

The same six skills ship in the Copilot bundle. The [README](../README.md#what-you-get) documents the lifecycle slash commands for Claude Code only. In Copilot CLI, select agents by name. The README lists three ways: the `--agent` flag, `/agent`, or the agent's name in your prompt. Start with the orchestrator and let it route:

```shell
copilot --agent orchestrator --prompt "Implement rate limiting on the API, with tests and a security review"
```

Or run `/agent` and pick `milestone-planner`, `implementer`, or `critic` for one step at a time.

### How the agents hand off

The orchestrator coordinates specialists through explicit handoffs. The typical flow from the [README](../README.md#how-agents-work-together):

1. You describe a task to the orchestrator.
2. The orchestrator routes to the analyst for research and feasibility.
3. The architect designs the solution. The milestone-planner breaks it into work packages.
4. The implementer writes code and tests.
5. QA and security validate. The critic stress-tests the approach.
6. On approval, work is complete. On failure, it loops back for fixes.

The loop in step 6 depends on who rejects. A failed QA run returns to the orchestrator with a recommendation to route to the implementer. A critic verdict of `NEEDS_REVISION` goes back to the milestone-planner or task-decomposer, whichever wrote the plan. `BLOCKED` goes to the orchestrator.

## Which to use

| Need | Agent Teams | Copilot custom agents | AI Agents |
|------|-------------|-----------------------|-----------|
| Setup | Set one environment variable | Write one `.agent.md` file per role | Run two install commands per CLI |
| Works in Claude Code | Yes | Not documented. Claude Code's documented subagent locations are `.claude/agents/`, `~/.claude/agents/`, and plugins | Yes |
| Works in Copilot CLI | Not documented. Agent Teams is a Claude Code feature | Yes | Yes |
| Reusable roles | Yes, through subagent definitions | Yes, one file per role | Yes, 30 roles included |
| Plan before code | A teammate spawned from a lead in plan mode stays read-only until its plan is ready | Plan mode, with `Shift`+`Tab` or `--plan` | The plan skill in Claude Code. The milestone-planner and critic agents in both CLIs |
| Parallel work | Yes. Teammates run as separate sessions | Yes, with `/fleet` or the `--fleet` flag | The orchestrator delegates to specialists |
| Review gates | Hooks you write: `TeammateIdle`, `TaskCreated`, `TaskCompleted` | A reviewer agent you write. Copilot CLI also has a built-in code review agent | Critic, QA, and security agents, plus hooks that need Python 3.10 or newer |
| Status | Experimental and off by default | The `--agent`, `--plan`, and `--fleet` flags are in Copilot CLI 1.0.95 | MIT licensed. Both installs ran clean on 2026-10-11 |

Sources, by column:

- **Agent Teams:** [Agent Teams documentation](https://code.claude.com/docs/en/agent-teams).
- **Copilot custom agents:** [Using Copilot CLI](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli), [Creating custom agents for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli), [fleet](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet), [About Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-copilot-cli), and `copilot --help` on version 1.0.95. The Claude Code row cites the [subagents documentation](https://code.claude.com/docs/en/sub-agents).
- **AI Agents:** the [README](../README.md), the agent templates under `templates/agents/`, and an install of `project-toolkit@ai-agents` in each CLI.

The options are not exclusive. AI Agents installs as subagents in Claude Code and as custom agents in Copilot CLI.

## Tips that apply to all three

The first three draw on the [Agent Teams documentation](https://code.claude.com/docs/en/agent-teams): file ownership from its best practices, plan-first from its section on planning before implementing, and one lens per reviewer from its parallel code review example.

- **Give each agent its own files.** Two agents editing one file overwrite each other. Split the work so each agent owns a different set of files.
- **Plan read-only first.** Let the planner finish before any agent can edit.
- **Give each reviewer one lens.** One reviewer for security, one for tests, one for performance. A single reviewer tends to fix on one kind of problem.
- **Keep the reviewer out of the author's context.** In AI Agents, the critic sees the diff, the plan, and the spec. QA sees the diff and the spec. Neither sees the implementer's reasoning. The templates give the reason: a reviewer that shares the author's context tends to confirm the author's framing.
- **Start small.** The Agent Teams documentation suggests 3 to 5 teammates for most work. Every extra agent adds token cost and coordination.

## FAQ

### What is the difference between Claude Code subagents and agent teams?

By default, a subagent returns its result to the caller, and the main agent manages all the work. Teammates are separate sessions that message each other directly and coordinate through a shared task list. Use subagents for focused tasks where only the result matters. Use a team when the agents need to discuss and challenge each other. Source: the comparison table in the [Agent Teams documentation](https://code.claude.com/docs/en/agent-teams#compare-with-subagents).

### Are Claude Code agent teams production ready?

The documentation calls them experimental. They are off by default, and the page lists limits around session resumption, task coordination, and shutdown. Read the [limitations](https://code.claude.com/docs/en/agent-teams#limitations) before you depend on them.

### Can GitHub Copilot CLI run multiple agents?

Yes. The model can delegate a task to a subagent on its own. The `/fleet` command splits a plan into subtasks and runs them on subagents in parallel where it can. You can assign a custom agent to a subtask with `@AGENT-NAME`.

### How do I make one agent review another's code?

Give the reviewer its own role and a read-only tool list. Hand it the diff, not the author's reasoning. In AI Agents, QA reports failures to the orchestrator and recommends the implementer. The critic sends a plan that needs revision back to its planner.

### Does AI Agents need Agent Teams enabled?

No. The agents are Claude Code subagents and Copilot CLI custom agents. No file under `src/` or `templates/` reads `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. The plan, build, and review skills ran on 2026-10-11 with the variable unset.
