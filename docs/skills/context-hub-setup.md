# context-hub-setup

Checks whether the Serena and Context7 plugins are installed. It reports each one that is missing, with the exact install command.

## When to use it

- You set up the context skills for the first time.
- A context or memory skill cannot reach Serena or Context7.
- Trigger phrases: `set up context hub`, `check my plugin prerequisites`, `troubleshoot MCP connectivity`, `what plugins am I missing`.

## When not to use it

- You want to gather context for a task: use [`context-gather`](context-gather.md).
- You want to search memory: use [`memory-search`](memory-search.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:context-hub-setup
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/context-hub-setup`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /context-hub-setup skill to ...`.

The skill lists your plugins with `claude plugins list`, then prints a status block and stops.

## What you get

A status block like this:

```text
Context Hub Setup Status:
-------------------------
Serena Plugin:  [Installed / Not installed - run: claude plugins install serena]
Context7 Plugin: [Installed / Not installed - run: claude plugins install context7 --marketplace pleaseai/claude-code-plugins]
```

Each missing plugin appears with its install line. The task is complete once this block prints. The skill does not poll or re-check afterward.

## Advanced use

Serena supplies symbol-level code analysis and the `.serena/memories/` store. The `using-serena-symbols` skill and the memory skills depend on it. Context7 supplies framework documentation and is recommended for [`context-gather`](context-gather.md).

Memory search reads committed markdown under `.serena/memories/`, so it keeps working when the Serena MCP server is down. A missing Serena does not block [`memory-search`](memory-search.md). The skill reports the gap and notes this.

Serena and Context7 install as plugins, not MCP servers. Use `claude plugins install <name>`, and `claude plugins search <name>` to look in the marketplace.

After the status block, you can run two optional checks:

- Serena: ask Claude to use Serena's `get_symbols_overview` on a file in your project.
- Context7: ask a framework question, such as how FastAPI dependency injection works.

The install commands belong to Claude Code. A harness with a different plugin manager changes those lines and nothing else.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`context-gather`](context-gather.md): uses Context7 once it is installed.
- [`memory-search`](memory-search.md): reads `.serena/memories/` without the MCP layer.
- [`using-serena-symbols`](using-serena-symbols.md): depends on the Serena plugin.
- Source: [`SKILL.md`](../../src/claude/skills/context-hub-setup/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
