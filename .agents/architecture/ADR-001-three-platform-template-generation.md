# ADR-001: Three-Platform Template Generation

## Status

Accepted

## Context

The agent system has 18 agents deployed across 3 platforms:
- **Claude Code**: `src/claude/*.md` (18 files, 5,449 lines)
- **VS Code**: `src/vs-code-agents/*.agent.md` (18 files, generated)
- **Copilot CLI**: `src/copilot-cli/*.agent.md` (18 files, generated)

The prior 2-variant consolidation approach failed because:
1. It kept Claude agents as source of truth, generating only VS Code/Copilot
2. Data showed 88-98% divergence between Claude and templates (2-12% similarity)
3. The approach created ongoing drift rather than eliminating it

The user directive is clear: "Templates must be the source of truth. Generate ALL THREE platforms from templates."

## Decision

Adopt **Three-Platform Template Generation** where:

1. **Single source of truth**: `templates/agents/*.shared.md`
2. **Three generated outputs**:
   - `src/claude/*.md` - GENERATED
   - `src/vs-code-agents/*.agent.md` - GENERATED
   - `src/copilot-cli/*.agent.md` - GENERATED
3. **Platform configurations**: `templates/platforms/*.yaml` define transforms

### Claude Platform Configuration

Create `templates/platforms/claude.yaml`:

```yaml
# Claude Platform Configuration
# Used by Generate-Agents.ps1 to transform shared sources

platform: claude
outputDir: src/claude
fileExtension: .md

# Frontmatter settings
frontmatter:
  # Claude uses simple model identifier
  model: "opus"
  # Claude requires name field
  includeNameField: true

# Agent handoff syntax (no specific syntax needed for Claude)
handoffSyntax: null

# Tool syntax style - MCP function calls
toolSyntax: mcp

# Memory protocol prefix - full MCP path
memoryPrefix: "mcp__cloudmcp-manager__"

# Section injection - Claude needs tools section in body
sections:
  injectClaudeCodeTools: true
```

### Template Modifications

Templates require:

1. **New frontmatter field**: `tools_claude` for Claude-specific tool list
2. **Section markers**: `{{CLAUDE_CODE_TOOLS}}` placeholder for section injection
3. **Memory syntax placeholders**: `{{MEMORY_PREFIX}}` already exists

Example template frontmatter:

```yaml
---
description: Agent description
tools_vscode: ['vscode', 'read', 'search', 'cloudmcp-manager/*']
tools_copilot: ['shell', 'read', 'edit', 'search', 'agent', 'cloudmcp-manager/*']
tools_claude: ['Read', 'Grep', 'Glob', 'Bash', 'WebSearch', 'WebFetch', 'mcp__cloudmcp-manager__*']
---
```

### Generate-Agents.ps1 Extensions

The generation script requires:

1. **Claude platform support**: Read `claude.yaml` and generate to `src/claude/`
2. **Section injection**: Insert `## Claude Code Tools` section with tool documentation
3. **MCP syntax transform**: Convert path-style tool references to MCP syntax in prose
4. **File extension handling**: `.md` for Claude (not `.agent.md`)

#### Section Injection Implementation

When `sections.injectClaudeCodeTools: true`:

1. After frontmatter, inject:

```markdown
## Claude Code Tools

You have direct access to:

- **Read/Grep/Glob**: [purpose based on agent]
- **Bash**: [purpose based on agent]
- **WebSearch/WebFetch**: [purpose based on agent]
- **cloudmcp-manager memory tools**: Cross-session context
```

2. The specific tools listed depend on the `tools_claude` array in frontmatter

#### MCP Syntax Transform

| Template Syntax | Claude Output |
|-----------------|---------------|
| `cloudmcp-manager/memory-search_nodes` | `mcp__cloudmcp-manager__memory-search_nodes` |
| `cognitionai/deepwiki/ask_question` | `mcp__deepwiki__ask_question` |
| `{{MEMORY_PREFIX}}` | `mcp__cloudmcp-manager__` |

### Transform Pipeline

```text
templates/agents/*.shared.md
    |
    +-- Read frontmatter + body
    |
    +-- For each platform in [claude, vscode, copilot-cli]:
        |
        +-- Transform frontmatter (model, name, tools)
        +-- Inject sections (if configured)
        +-- Transform syntax (MCP, handoff, memory)
        +-- Write to outputDir
```

## Consequences

### Positive

- **Single source of truth**: One place to edit agent definitions
- **No drift by design**: All platforms generated from same source
- **Consistent behavior**: Agents behave identically across platforms (semantically)
- **Reduced maintenance**: Change once, regenerate all
- **CI validation**: Script can validate generated files match source

### Negative

- **Migration effort**: Must merge Claude content into templates (~4-8 hours)
- **Learning curve**: Contributors must understand template system
- **Build step required**: Changes require regeneration before commit
- **Loss of platform flexibility**: Platform-specific optimizations must fit template model

### Neutral

- **54 files in output**: Same as before, but all generated
- **Drift detection obsolete**: No longer needed when source is unified
- **Template complexity increases**: Must handle 3 platform variants

## Alternatives Considered

### Alternative 1: Keep 2-Variant Approach

- **Pros**: Less migration effort, preserves Claude agents as-is
- **Cons**: Failed approach, perpetuates drift, wrong source of truth
- **Why rejected**: Data showed 88-98% divergence, approach is fundamentally flawed

### Alternative 2: Runtime Platform Detection

- **Pros**: No build step, single file per agent
- **Cons**: Platform schemas differ (VS Code/Copilot require specific frontmatter), complex runtime logic
- **Why rejected**: Platform frontmatter requirements make this impossible

### Alternative 3: Accept Intentional Divergence

- **Pros**: No work needed
- **Cons**: Divergence is NOT intentional (proven by PR #43 issues), maintenance burden grows
- **Why rejected**: Drift is accidental, not strategic

## References

- Context: `.agents/analysis/three-platform-templating-context.md`
- Independent-thinker review: `.agents/analysis/independent-thinker-review-three-platform.md`
- High-level-advisor verdict: `.agents/analysis/high-level-advisor-verdict-three-platform.md`
- Prior failure: Memory entity `epic-2-variant-consolidation`
- User directive: Conversation context (2025-12-15)
