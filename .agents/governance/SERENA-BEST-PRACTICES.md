# Serena Best Practices for Token Efficiency

> **Status**: Active
> **Created**: 2025-12-20
> **Purpose**: Maximize token efficiency when using Serena MCP tools
> **References**: [Serena Configuration](https://oraios.github.io/serena/02-usage/050_configuration.html), [Additional Usage](https://oraios.github.io/serena/02-usage/999_additional-usage.html)

## Why Serena Matters for Cost

Serena's symbolic tools are **critical for token efficiency**:

| Approach | Token Usage | Cost Impact |
|----------|-------------|-------------|
| Read entire file | 100% of file | High - full file in context |
| Serena `get_symbols_overview` | ~5% of file | Low - just structure |
| Serena `find_symbol` with `include_body=True` | ~10-20% of file | Low - targeted read |

**Rule**: ALWAYS prefer Serena symbolic tools over raw file reads.

---

## CLI Reference

### Main Commands

```bash
serena --help                    # Main help
serena config --help             # Configuration management
serena context --help            # Context management
serena mode --help               # Mode management
serena project --help            # Project management
serena prompts --help            # Prompt customization
serena tools --help              # Tool information
serena start-mcp-server --help   # MCP server options
```

### Project Commands

```bash
# Create a new project
serena project create

# Index project for faster symbol lookup
serena project index [PROJECT_PATH]

# Health check (verify LSP and tools work)
serena project health-check [PROJECT_PATH]

# Check if path is ignored
serena project is_ignored_path <path>
```

### Context Commands

```bash
# List available contexts
serena context list

# Create custom context (or override internal)
serena context create -n my-context
serena context create --from-internal claude-code -n my-claude-code

# Edit custom context
serena context edit my-context

# Delete custom context
serena context delete my-context
```

### Mode Commands

```bash
# List available modes
serena mode list

# Create custom mode (or override internal)
serena mode create -n my-mode
serena mode create --from-internal planning -n my-planning

# Edit/delete custom modes
serena mode edit my-mode
serena mode delete my-mode
```

### Prompt Customization

```bash
# List prompt templates
serena prompts list
# Output: simple_tool_outputs.yml, system_prompt.yml

# List existing overrides
serena prompts list-overrides

# Create override for customization
serena prompts create-override system_prompt.yml

# Edit/delete overrides
serena prompts edit-override system_prompt.yml
serena prompts delete-override system_prompt.yml
```

### Tool Information

```bash
# List all tools with descriptions
serena tools list

# Get detailed description of a tool
serena tools description find_symbol
serena tools description get_symbols_overview
```

---

## Available Contexts

| Context | Description | Use When |
|---------|-------------|----------|
| `claude-code` | **Recommended** - Disables duplicate capabilities | Claude Code CLI |
| `desktop-app` | Default for desktop apps | Claude Desktop |
| `ide` | For IDE integrations | VS Code, Cursor |
| `agent` | Autonomous agent scenarios | Automated workflows |
| `codex` | OpenAI Codex compatibility | Codex-based tools |
| `oaicompat-agent` | OpenAI-compatible local servers | Local LLM servers |
| `chatgpt` | ChatGPT compatibility | ChatGPT integrations |

---

## Available Modes

Modes can be combined. Default: `interactive, editing`

| Mode | Effect | Use When |
|------|--------|----------|
| `interactive` | Enables user interaction prompts | Default |
| `editing` | Enables code editing tools | Default |
| `planning` | Emphasis on planning before implementation | Complex tasks |
| `one-shot` | Single response, no follow-up | Quick queries |
| `onboarding` | Enables onboarding prompts | New projects |
| `no-onboarding` | Disables onboarding | Known projects |
| `no-memories` | Disables memory tools | One-off queries |

---

## Available Tools

### Symbolic Navigation (Token-Efficient)

| Tool | Purpose | Efficiency |
|------|---------|------------|
| `get_symbols_overview` | File structure overview | ⭐⭐⭐ |
| `find_symbol` | Find by name/pattern | ⭐⭐⭐ |
| `find_referencing_symbols` | Find usages | ⭐⭐⭐ |
| `rename_symbol` | Refactor across codebase | ⭐⭐⭐ |

### File Operations

| Tool | Purpose | Efficiency |
|------|---------|------------|
| `list_dir` | Directory listing | ⭐⭐ |
| `find_file` | Find files by pattern | ⭐⭐ |
| `read_file` | Full file read | ⭐ Use sparingly |
| `search_for_pattern` | Regex search | ⭐⭐ Scope it |

### Code Editing

| Tool | Purpose |
|------|---------|
| `create_text_file` | Create/overwrite file |
| `replace_content` | Replace with regex support |
| `replace_symbol_body` | Replace entire symbol |
| `insert_before_symbol` | Insert before symbol |
| `insert_after_symbol` | Insert after symbol |

### Memory Management

| Tool | Purpose |
|------|---------|
| `list_memories` | List all memories |
| `read_memory` | Read specific memory |
| `write_memory` | Save memory |
| `edit_memory` | Modify memory |
| `delete_memory` | Remove memory |

### Thinking Tools

| Tool | Purpose |
|------|---------|
| `think_about_collected_information` | Verify context completeness |
| `think_about_task_adherence` | Check still on track |
| `think_about_whether_you_are_done` | Verify task completion |

### Session Management

| Tool | Purpose |
|------|---------|
| `activate_project` | Switch projects |
| `initial_instructions` | Get Serena instructions |
| `check_onboarding_performed` | Verify onboarding status |
| `onboarding` | Perform project onboarding |
| `prepare_for_new_conversation` | Create continuation summary |
| `get_current_config` | Show active config |

---

## Configuration

### Global Configuration (`~/.serena/serena_config.yml`)

**Token efficiency settings:**

```yaml
# Maximum characters for tool outputs (default: 150000)
# Lower = fewer tokens, but may truncate results
default_max_tool_answer_chars: 50000

# Token count estimator for usage stats
# Options: CHAR_COUNT, TIKTOKEN_GPT4O, ANTHROPIC_CLAUDE_SONNET_4
token_count_estimator: ANTHROPIC_CLAUDE_SONNET_4
```

| Setting | Default | Recommendation | Impact |
|---------|---------|----------------|--------|
| `default_max_tool_answer_chars` | 150000 | 50000-75000 | Limits tool output size |
| `token_count_estimator` | CHAR_COUNT | ANTHROPIC_CLAUDE_SONNET_4 | Accurate token tracking |

### Project Configuration (`.serena/project.yml`)

```yaml
# Languages for LSP (first is default/fallback)
languages:
  - bash
  - yaml
  - python
  - markdown

# File encoding
encoding: "utf-8"

# Use .gitignore rules
ignore_all_files_in_gitignore: true

# Additional paths to ignore (gitignore syntax)
ignored_paths:
  - "**/node_modules/**"
  - "**/.git/**"

# Read-only mode (disables editing tools)
read_only: false

# Tools to exclude (not recommended)
excluded_tools: []

# Project name
project_name: "my-project"

# Initial prompt (shown on project activation)
initial_prompt: ""
```

### Recommended MCP Configuration for Claude Code

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/oraios/serena",
        "serena", "start-mcp-server",
        "--context", "claude-code",
        "--mode", "interactive",
        "--mode", "editing",
        "--project-from-cwd"
      ]
    }
  }
}
```

### MCP Server Options

| Flag | Description |
|------|-------------|
| `--context TEXT` | Built-in or custom context (default: `desktop-app`) |
| `--mode TEXT` | Built-in or custom mode (repeatable) |
| `--project PATH` | Activate project at startup |
| `--project-from-cwd` | Auto-detect project from CWD |
| `--tool-timeout FLOAT` | Override tool execution timeout |
| `--log-level LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `--transport TYPE` | stdio, sse, streamable-http |

---

## Token-Efficient Patterns

### 1. Use Symbolic Tools First (MUST)

```text
❌ AVOID: Read("src/large-file.ts")  # 2000 tokens
✅ PREFER: get_symbols_overview("src/large-file.ts")  # 100 tokens
           find_symbol("ClassName", include_body=True)  # 200 tokens
```

### 2. Never Read What You Already Have

Once a file is read, do NOT re-analyze with symbolic tools:

```text
❌ AVOID: Read file → then get_symbols_overview of same file
✅ PREFER: Start with get_symbols_overview → read specific symbols only
```

### 3. Read Memories Before Work (MUST)

Memories enable LLM prompt caching (90% cost reduction):

```text
1. mcp__serena__list_memories()  # See available context
2. mcp__serena__read_memory("relevant-memory")  # Load into context
3. Start work  # LLM caches the context prefix
```

### 4. Use `find_symbol` with Patterns

```text
# Find all methods starting with "get"
find_symbol("get", substring_matching=True)

# Find specific method in class
find_symbol("MyClass/myMethod")

# Find with path restriction (reduces search scope)
find_symbol("Config", relative_path="src/config/")

# Get overview without body (minimal tokens)
find_symbol("ClassName", include_body=False, depth=1)
```

### 5. Restrict Search Scope (SHOULD)

Always use `relative_path` when you know where to look:

```text
❌ AVOID: search_for_pattern("TODO")  # Searches entire codebase
✅ PREFER: search_for_pattern("TODO", relative_path="src/")  # Scoped search
```

### 6. Pre-Index Projects

```bash
# Index project for faster symbol lookup
serena project index /path/to/project

# Verify setup
serena project health-check /path/to/project
```

### 7. Limit Tool Output

Use `max_answer_chars` parameter on tools:

```text
# Limit output for large codebases
get_symbols_overview("src/", max_answer_chars=50000)
find_symbol("Config", max_answer_chars=30000)
```

---

## Serena's Internal Caching

Serena uses a two-tier caching system to reduce LSP overhead:

| Cache Layer | Contents | Benefit |
|-------------|----------|---------|
| `_raw_document_symbols_cache` | Raw LSP JSON responses | Avoids LSP round-trips |
| `_document_symbols_cache` | Parsed `DocumentSymbols` | Avoids re-parsing |

**Benefit**: Repeated queries to the same file are near-instant.

**Cache persistence**: The `.serena/cache/` directory stores index data across sessions.

---

## Managing Long Sessions

### When Approaching Token Limits

1. Use `mcp__serena__prepare_for_new_conversation` to create a summary
2. Store summary in memory: `mcp__serena__write_memory`
3. Start new session
4. Read memory to continue: `mcp__serena__read_memory`

### Git Worktrees

For parallel branch work, copy the cache:

```bash
# After creating worktree
cp -r $ORIG_PROJECT/.serena/cache $GIT_WORKTREE/.serena/cache
```

This avoids redundant indexing.

---

## Custom Prompts for Cost Reduction

Override default prompts to reduce token usage:

```bash
# Create a lighter system prompt
serena prompts create-override system_prompt.yml

# Edit to remove verbose sections
serena prompts edit-override system_prompt.yml
```

The override file uses Jinja2 template syntax and is stored in `~/.serena/prompt_templates/`.

---

## Troubleshooting

### Health Check

```bash
serena project health-check /path/to/project
```

This verifies:
- LSP connectivity
- Tool availability
- Project configuration

### Restart Language Server

If edits outside Serena cause issues:

```text
mcp__serena__restart_language_server
```

---

## Related Documents

- [COST-GOVERNANCE.md](./COST-GOVERNANCE.md) - Overall cost policy
- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md) - Session requirements
- [Serena Documentation](https://oraios.github.io/serena/) - Official docs
