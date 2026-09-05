---
description: Use when setting up a new development environment or troubleshooting MCP connectivity. Checks the Serena and Context7 plugin prerequisites and reports what is missing.
---

# Context Hub Setup

Check the plugins the context commands depend on, and report what is missing.

## Prerequisites

Context Hub requires these plugins to be installed:

1. **Serena** - Symbol-level code analysis and the `.serena/memories/` store (required for `/encode-repo-serena`)
2. **Context7** - Framework documentation (recommended for `/context-gather`)

## Step 1: Check Plugin Prerequisites

First, check if the required plugins are installed:

```bash
claude plugins list
```

Look for:

- `serena` or similar (for code analysis)
- `context7` or similar (for framework docs)

**If Serena is not installed:**

```text
To use /encode-repo-serena, install the Serena plugin:

  claude plugins install serena

Or search for it in the marketplace:

  claude plugins search serena
```

**If Context7 is not installed:**

```text
For framework documentation in /context-gather, install Context7:

  claude plugins install context7 --marketplace pleaseai/claude-code-plugins

Or search for it:

  claude plugins search context7
```

## Step 2: Verify Complete Setup

Report status of all components:

```text
Context Hub Setup Status:
-------------------------
Serena Plugin:  [Installed / Not installed - run: claude plugins install serena]
Context7 Plugin: [Installed / Not installed - run: claude plugins install context7 --marketplace pleaseai/claude-code-plugins]

Commands available:
- /context-gather - Multi-source context retrieval
- /encode-repo-serena - Repository encoding (requires Serena)
```

Memory search reads committed files rather than querying a server:

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "topic"
```

It reads the markdown under `.serena/memories/`, so it works whether or not the
Serena MCP server is reachable. The plugin-root prefix resolves the script in a
vendored install, where a bare `.claude/` path does not exist.

## Step 3: Quick Test (Optional)

Offer to test the setup:

**Test Serena (if installed):**

```text
Ask Claude to use Serena's get_symbols_overview on a file in your project
```

**Test Context7 (if installed):**

```text
Ask about a framework: "How does FastAPI dependency injection work?"
```

## Troubleshooting

**Plugin issues:**

- Re-run: `claude plugins install <plugin-name>`
- Check marketplace: `claude plugins search <name>`

## Notes

- Serena and Context7 are plugins, not MCPs - install via `claude plugins install`
- Serena memories are committed markdown under `.serena/memories/`. They stay readable when the MCP layer is down.

## Completion Criteria

The Context Hub setup is **complete** when ALL of the following are true:

| Criterion | Verification |
|-----------|------------|
| Serena plugin status reported | Output shows "Installed" or explicit "Not installed" message |
| Context7 plugin status reported | Output shows "Installed" or explicit "Not installed" message |
| Setup status block printed | Step 2 status block has been emitted to the user |

### Stop Condition

After printing the Step 2 status block, the command is complete. Do not continue polling, re-checking, or offering additional tests unless the user explicitly requests a re-run with `/context-hub-setup` again.

If the user chooses to run the optional Step 3 quick tests, those are supplementary and do not affect completion status.
