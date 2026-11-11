# Install the toolkit on Claude Code

Verified on Claude Code 2.1.319 on 2026-11-11. Main was at `8a8af7bc9d` (2026-11-10).

## Goal

Install `project-toolkit` and see Claude Code list its 105 skills and 29 agents.

## Before you start

- Claude Code with plugin support. Check with `claude --version`.
- Network access to github.com.

## Steps

1. Register the marketplace and install the plugin:

   ```bash
   claude plugin marketplace add rjmurillo/ai-agents
   claude plugin install project-toolkit@ai-agents
   ```

   Inside a Claude Code session, the same steps are `/plugin marketplace add rjmurillo/ai-agents` and `/plugin install project-toolkit@ai-agents`. We ran the shell form.

2. Restart Claude Code so it loads the new agents and skills.

## Check your result

```bash
claude plugin list
claude plugin details project-toolkit@ai-agents
```

You should see:

```text
Installed plugins:
  ❯ project-toolkit@ai-agents
    Version: 8a8af7bc9d45
    Scope: user
    Status: ✔ enabled
```

The details command lists the parts the host loaded:

```text
Component inventory
  Skills (105)  adr-generator, adr-review, ...
  Agents (29)  analyst, architect, ...
  Hooks (1)  Stop  (harness-only ...)
  MCP servers (0)
```

The line is shortened here. The host prints a longer note after `Stop`.

Your `Version` will differ if main has moved. It is the commit SHA.

The tree also holds 23 rule files. The details command lists no rules, so do not expect them to load as a plugin component.

Not run: asking an agent a question. That needs a signed-in session. The steps are in [Verify Installation](../../installation.md#verify-installation).

## Update, and tell if you are stale

Claude Code uses the commit SHA as the version (ADR-092). Compare the two SHAs:

```bash
git ls-remote https://github.com/rjmurillo/ai-agents HEAD
claude plugin list
```

If the first 12 characters of `Version` match the first line, you are current. If not, update:

```bash
claude plugin marketplace update ai-agents
claude plugin update project-toolkit@ai-agents
```

When you are current, the update prints:

```text
✔ project-toolkit is already at the latest version (df19438d94c6).
```

Main moved from `8a8af7bc9d` to `df19438d94` (test files only) between our install and this update run, so the two SHAs on this page differ. Yours will differ too. We did not run an update that moved to a newer commit.

## Uninstall

```bash
claude plugin uninstall project-toolkit@ai-agents
claude plugin marketplace remove ai-agents
```

## If it fails

- `claude plugin` is not recognized: update Claude Code to a build with plugin marketplaces.
- Agents or skills are missing after install: restart Claude Code.
- Agents that name `mcp__github__*` tools run without them: see the [GitHub MCP prerequisite](../../installation.md#github-mcp-prerequisite).
- Other fixes: [Installation troubleshooting](../../installation.md#troubleshooting).

## What Claude Code gets

| Part | Count | Source |
|------|-------|--------|
| Skills | 105 | `src/claude/skills/` |
| Agents | 29 | `src/claude/agents/` |
| Hooks | 1 advisory Stop hook | `src/claude/hooks/` |

## Next

Go to [Getting started](../../getting-started.md), or pick another host from the [install picker](README.md).
