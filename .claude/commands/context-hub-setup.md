---
description: Configure Context Hub dependencies (Forgetful MCP + plugin prerequisites)
---

# Context Hub Setup

Configure Context Hub's dependencies: Forgetful MCP server and prerequisite plugins.

## Prerequisites

Context Hub requires these plugins to be installed:

1. **Serena** - Symbol-level code analysis (required for `/encode-repo-serena`)
2. **Context7** - Framework documentation (recommended for `/context_gather`)

## Step 1: Check Plugin Prerequisites

First, check if the required plugins are installed:

```bash
claude plugins list
```

Look for:
- `serena` or similar (for code analysis)
- `context7` or similar (for framework docs)

**If Serena is not installed:**
```
To use /encode-repo-serena, install the Serena plugin:

  claude plugins install serena

Or search for it in the marketplace:

  claude plugins search serena
```

**If Context7 is not installed:**
```
For framework documentation in /context_gather, install Context7:

  claude plugins install context7 --marketplace pleaseai/claude-code-plugins

Or search for it:

  claude plugins search context7
```

## Step 2: Configure Forgetful MCP

Check if Forgetful is already configured:

```bash
claude mcp list | grep -i forgetful
```

If already configured:
- Ask user if they want to reconfigure
- If no, skip to Step 3
- If yes, remove existing first: `claude mcp remove forgetful`

### Setup Options

Ask the user which setup they prefer:

**Question**: "How would you like to configure Forgetful?"

**Options**:
1. **Standard (Recommended)** - Zero config, uses uvx with SQLite storage
2. **Custom** - Remote HTTP server, PostgreSQL, custom embeddings, etc.

### Standard Setup

```bash
claude mcp add forgetful --scope user -- uvx forgetful-ai
```

Confirm success:
```bash
claude mcp list | grep -i forgetful
```

Report: "Forgetful is now configured! Your memories will persist in `~/.forgetful/` using SQLite."

### Custom Setup

If user chose Custom:

1. Fetch configuration docs:
```
WebFetch: https://github.com/ScottRBK/forgetful/blob/main/docs/configuration.md
```

2. Guide through options:
   - **Remote HTTP server** - Connect to Forgetful running elsewhere
   - **PostgreSQL backend** - Use Postgres instead of SQLite
   - **Custom embeddings** - Different embedding model/provider

3. Build appropriate command based on choices.

## Step 3: Verify Complete Setup

Report status of all components:

```
Context Hub Setup Status:
-------------------------
Forgetful MCP:  [Configured / Not configured]
Serena Plugin:  [Installed / Not installed - run: claude plugins install serena]
Context7 Plugin: [Installed / Not installed - run: claude plugins install context7 --marketplace pleaseai/claude-code-plugins]

Commands available:
- /context_gather - Multi-source context retrieval
- /encode-repo-serena - Repository encoding (requires Serena)
- /memory-search, /memory-list, /memory-save, /memory-explore - Memory management
```

## Step 4: Quick Test (Optional)

Offer to test the setup:

**Test Forgetful:**
```
/memory-list
```

**Test Serena (if installed):**
```
Ask Claude to use Serena's get_symbols_overview on a file in your project
```

**Test Context7 (if installed):**
```
Ask about a framework: "How does FastAPI dependency injection work?"
```

## Troubleshooting

**Forgetful issues:**
- Check if `uvx` is installed: `which uvx`
- For HTTP: verify server is running
- Check Claude Code logs for MCP errors

**Plugin issues:**
- Re-run: `claude plugins install <plugin-name>`
- Check marketplace: `claude plugins search <name>`

## Notes

- Forgetful MCP config stored in `~/.claude.json` (persists across updates)
- Serena and Context7 are plugins, not MCPs - install via `claude plugins install`
- SQLite database location: `~/.forgetful/forgetful.db`
