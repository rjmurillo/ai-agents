# Call agents and skills

This page shows the exact text to type to start an agent or a skill on each host. Use it when a reference page gives you a name and you need the syntax for your tool.

## Before you start

- Install the toolkit on your host. See [Install the toolkit on your host and check it loaded](training/install-on-every-host.md).
- Know the name of the agent or skill you want. Browse [Agents](agents/README.md) or [Skills](skills/README.md).
- Check whether the skill has a short slash command. The **Slash command** column in [Skills](skills/README.md) shows a command such as `/spec`, `match` for skills the agent loads on its own, or `by name` for skills you must start yourself.

Examples on these pages use PR `123`, issue `42`, and sample file paths. Replace them with your own numbers and paths.

## Call a skill

### Claude Code

After a marketplace install, Claude Code puts each plugin skill under the plugin's name, as `/plugin-name:skill-name` ([Claude Code skills](https://code.claude.com/docs/en/skills)). Type the full form, then any argument:

```text
/project-toolkit:spec Add rate limiting to the API
```

Inside a checkout of `rjmurillo/ai-agents`, the skills also load from the repository itself. There you can type the short form:

```text
/spec Add rate limiting to the API
```

Claude Code accepts a slash command for every plugin skill, not only the ones with a short slash command, because `user-invocable` defaults to `true` there ([Claude Code skills](https://code.claude.com/docs/en/skills)). For example, `/project-toolkit:threat-modeling` starts the `threat-modeling` skill.

### GitHub Copilot CLI

Name the skill in your prompt, with a slash before its name. GitHub's [Copilot CLI skills docs](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-skills) use this form:

```text
Use the /spec skill to add rate limiting to the API.
```

Run `/skills list` to see the skills Copilot CLI loaded.

### Skills the agent loads on match

Most skills have no short slash command. The agent reads each skill's description and loads the skill when your request matches. To be sure it loads, name it in your request:

```text
Use the threat-modeling skill to threat-model the upload endpoint in src/api/upload.py.
```

### Skills you start by name

A few skills have explicit-only routing, shown as `by name` in [Skills](skills/README.md). The `autoplan` router never picks them, so name them in your request, or in Claude Code type `/project-toolkit:<name>`.

This works on every host, including Codex, Cursor, and Muse.

## Call an agent

### Claude Code

Start your prompt with the agent's name and a colon:

```text
analyst: find why the /api/users endpoint returns 500 when the email has a plus sign
```

You can also ask in plain words, such as `Use the analyst agent to ...`.

### GitHub Copilot CLI

Pass the agent with `--agent` from your shell:

```bash
copilot --agent analyst --prompt "Find why /api/users returns 500 when the email has a plus sign"
```

Inside a Copilot CLI session, run `/agent` to pick from the installed agents, or name the agent in your prompt.

### VS Code and Visual Studio

In Copilot Chat, mention the agent with `@`:

```text
@analyst Find why /api/users returns 500 when the email has a plus sign
```

This needs the agent files in your repository's `.github/agents/` folder. See [VS Code and Visual Studio](installation.md#vs-code-and-visual-studio).

### Codex, Cursor, and Muse

Ask for the agent by name in your prompt:

```text
Use the analyst agent to find why /api/users returns 500 when the email has a plus sign.
```

Not every agent ships to every host. Each agent page has a **Where it runs** table.

## Let the toolkit choose

You do not have to pick. Two front doors route the work for you:

- `autoplan` picks one skill, lifecycle command, or agent chain for a request and runs it. See [`autoplan`](skills/autoplan.md).
- The `orchestrator` agent splits a multi-step job across several agents and merges the results. See [`orchestrator`](agents/orchestrator.md).

```text
/project-toolkit:autoplan add retry with backoff to the webhook sender
```

```text
orchestrator: add retry with backoff to the webhook sender, with tests and a security review
```

## Run a skill's script yourself

Many skills ship Python scripts. The agent runs them for you, but you can run them directly from the root of a checkout of `rjmurillo/ai-agents`. Start with `--help`:

```bash
uv run python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --help
```

Then run the script for real:

```bash
uv run python .claude/skills/security-scan/scripts/scan_vulnerabilities.py --directory .claude/skills/security-scan/scripts
```

```text
=== Security Vulnerability Scan ===

Files scanned: N
No vulnerabilities found.
```

Each skill page lists its scripts under **Advanced use**. For the `github` skill scripts, see [Do GitHub work with the skill scripts, not raw gh](training/github-skill-scripts.md).

## Check that it worked

- In Claude Code, type `/project-toolkit:` and look for the skill list. If nothing appears, the plugin is not installed or not enabled.
- In Copilot CLI, run `/agent` and look for the agent names.
- If a name is missing on your host, open its reference page and check **Where it runs**.

For install checks per host, see [Verify Installation](installation.md#verify-installation).

## Next

- [Agents and skills](agents-and-skills.md): how the two differ and when each one runs.
- [Take one change from /spec to /ship](training/lifecycle-and-autoplan.md): a full walk through the lifecycle skills.
