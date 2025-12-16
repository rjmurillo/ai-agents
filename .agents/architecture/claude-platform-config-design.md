# Claude Platform Config Design Specification

**Date**: 2025-12-15
**ADR Reference**: ADR-001-three-platform-template-generation.md
**Purpose**: Technical specification for Claude platform generation

---

## 1. Platform Configuration File

**Location**: `templates/platforms/claude.yaml`

```yaml
# Claude Code Platform Configuration
# Used by Generate-Agents.ps1 to transform shared sources

platform: claude
outputDir: src/claude
fileExtension: .md

# Frontmatter settings
frontmatter:
  # Claude uses simple model identifier in frontmatter
  model: "opus"
  # Claude requires name field (agent name)
  includeNameField: true

# Agent handoff syntax - Claude doesn't use specific syntax markers
handoffSyntax: null

# Tool syntax style - MCP function call format
toolSyntax: mcp

# Memory protocol prefix - full MCP path
memoryPrefix: "mcp__cloudmcp-manager__"

# Section injection configuration
sections:
  # Inject Claude Code Tools section after frontmatter
  injectClaudeCodeTools: true
  # Position: after frontmatter, before Core Identity
  insertPosition: afterFrontmatter
```

---

## 2. Template Frontmatter Schema Extension

### Current Schema

```yaml
---
description: Agent description
tools_vscode: ['tool1', 'tool2']
tools_copilot: ['tool1', 'tool2']
---
```

### Extended Schema (with Claude support)

```yaml
---
description: Agent description
tools_vscode: ['vscode', 'read', 'search', 'web', 'cloudmcp-manager/*']
tools_copilot: ['shell', 'read', 'edit', 'search', 'web', 'agent', 'cloudmcp-manager/*']
tools_claude: ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit', 'WebSearch', 'WebFetch']
claude_tools_section: |
  You have direct access to:

  - **Read/Grep/Glob**: Deep code analysis
  - **Bash**: Git commands, shell operations
  - **WebSearch/WebFetch**: Research best practices
  - **cloudmcp-manager memory tools**: Cross-session context
---
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | Yes | Shared description for all platforms |
| `tools_vscode` | string[] | Yes | VS Code agent tools array |
| `tools_copilot` | string[] | Yes | Copilot CLI agent tools array |
| `tools_claude` | string[] | Yes | Claude Code tools (for frontmatter) |
| `claude_tools_section` | string | Optional | Custom Claude Code Tools section content |

---

## 3. Claude Code Tools Section Injection

### Purpose

Claude agents require a `## Claude Code Tools` section in the body (not just frontmatter tools) that explains available capabilities in prose format.

### Default Template

If `claude_tools_section` is not specified in template frontmatter, generate default based on `tools_claude`:

```markdown
## Claude Code Tools

You have direct access to:

- **Read/Grep/Glob**: Analyze codebase
- **Write/Edit**: Modify files
- **Bash**: Execute shell commands
- **WebSearch/WebFetch**: Research and fetch web content
- **cloudmcp-manager memory tools**: Cross-session context
```

### Tool Category Mapping

| Tool in `tools_claude` | Description for section |
|------------------------|------------------------|
| `Read`, `Grep`, `Glob` | Deep code analysis (read-only) |
| `Write`, `Edit` | Modify files |
| `Bash` | Execute shell commands, git operations |
| `WebSearch`, `WebFetch` | Research best practices, API docs |
| `mcp__cloudmcp-manager__*` | Cross-session memory tools |
| `mcp__deepwiki__*` | Repository documentation |
| `mcp__context7__*` | Library documentation |

### Injection Position

Insert after frontmatter closing `---`, before the first `## Core` section:

```markdown
---
name: analyst
description: ...
model: opus
---
## Claude Code Tools  <-- INJECTED

You have direct access to:
...

# Analyst Agent  <-- EXISTING

## Core Identity  <-- EXISTING
...
```

---

## 4. Syntax Transformations

### 4.1 Memory Prefix Transformation

The `{{MEMORY_PREFIX}}` placeholder is already implemented. For Claude:

| Template | Claude Output |
|----------|---------------|
| `{{MEMORY_PREFIX}}memory-search_nodes` | `mcp__cloudmcp-manager__memory-search_nodes` |
| `{{MEMORY_PREFIX}}memory-add_observations` | `mcp__cloudmcp-manager__memory-add_observations` |
| `{{MEMORY_PREFIX}}memory-create_entities` | `mcp__cloudmcp-manager__memory-create_entities` |

### 4.2 Tool Path to MCP Transformation

For inline tool references in prose and code blocks:

| Template Path Syntax | Claude MCP Syntax |
|---------------------|-------------------|
| `cognitionai/deepwiki/ask_question` | `mcp__deepwiki__ask_question` |
| `cognitionai/deepwiki/read_wiki_contents` | `mcp__deepwiki__read_wiki_contents` |
| `cloudmcp-manager/upstashcontext7-mcp-*` | `mcp__cloudmcp-manager__upstashcontext7-mcp-*` |
| `cloudmcp-manager/memory-*` | `mcp__cloudmcp-manager__memory-*` |
| `cloudmcp-manager/perplexity-*` | `mcp__cloudmcp-manager__perplexity-*` |

### 4.3 Handoff Syntax (Not Applicable)

Claude agents don't use `#runSubagent` or `/agent` syntax. The `handoffSyntax: null` setting means no transformation is applied.

### 4.4 Code Block Transformations

Code blocks with tool invocation examples should be transformed:

**Template**:

```text
cognitionai/deepwiki/ask_question with repoName="owner/repo" question="how does X work?"
```

**Claude Output**:

```text
mcp__deepwiki__ask_question with repoName="owner/repo" question="how does X work?"
```

---

## 5. Frontmatter Output Format

### Claude Frontmatter Schema

```yaml
---
name: {agent_name}
description: {description}
model: opus
---
```

**Note**: Claude agents do NOT include the `tools:` array in frontmatter. Tools are documented in the `## Claude Code Tools` section.

### Field Order

1. `name` (required)
2. `description` (required)
3. `model` (required, always "opus")

---

## 6. Generate-Agents.ps1 Implementation Changes

### New Functions Required

```powershell
function Get-ClaudeToolsSection {
    <#
    .SYNOPSIS
        Generates Claude Code Tools section from template data.
    #>
    param(
        [hashtable]$Frontmatter,
        [string]$AgentName
    )

    # If custom section provided, use it
    if ($Frontmatter.ContainsKey('claude_tools_section')) {
        return $Frontmatter['claude_tools_section']
    }

    # Generate default section from tools_claude array
    # Map tools to descriptions
    # Return formatted markdown section
}

function Convert-PathToMcpSyntax {
    <#
    .SYNOPSIS
        Transforms path-style tool references to MCP syntax.
    #>
    param(
        [string]$Body
    )

    # Replace cognitionai/deepwiki/* with mcp__deepwiki__*
    # Replace cloudmcp-manager/* patterns
    # Return transformed body
}

function Insert-ClaudeToolsSection {
    <#
    .SYNOPSIS
        Injects Claude Code Tools section at correct position.
    #>
    param(
        [string]$Body,
        [string]$ToolsSection
    )

    # Find position after # Agent Name header
    # Insert section before ## Core Identity
    # Return modified body
}
```

### Modified Platform Processing Loop

```powershell
foreach ($platform in $platforms) {
    $platformName = $platform['platform']

    # Existing transformations
    $transformedFrontmatter = Convert-FrontmatterForPlatform ...
    $transformedBody = Convert-HandoffSyntax ...
    $transformedBody = Convert-MemoryPrefix ...

    # NEW: Claude-specific transformations
    if ($platformName -eq 'claude') {
        # Generate and inject Claude Code Tools section
        $toolsSection = Get-ClaudeToolsSection -Frontmatter $frontmatter -AgentName $agentName
        $transformedBody = Insert-ClaudeToolsSection -Body $transformedBody -ToolsSection $toolsSection

        # Convert path syntax to MCP syntax
        $transformedBody = Convert-PathToMcpSyntax -Body $transformedBody
    }

    # Continue with output...
}
```

---

## 7. Validation Requirements

### CI Validation (Generate-Agents.ps1 -Validate)

1. All 54 files regenerated
2. Compare to committed files
3. Exit 1 if any differences

### Claude-Specific Validation

1. Claude output files have `.md` extension (not `.agent.md`)
2. Claude output files have `name:` and `model: opus` in frontmatter
3. Claude output files have `## Claude Code Tools` section
4. No path-style tool references remain in Claude output

---

## 8. Migration Checklist

### Template Updates

- [ ] Add `tools_claude` to all 18 templates
- [ ] Add `claude_tools_section` where custom content needed
- [ ] Verify no hardcoded platform-specific content in shared sections

### Script Updates

- [ ] Create `templates/platforms/claude.yaml`
- [ ] Add `Get-ClaudeToolsSection` function
- [ ] Add `Convert-PathToMcpSyntax` function
- [ ] Add `Insert-ClaudeToolsSection` function
- [ ] Update platform processing loop

### Validation

- [ ] Run `Generate-Agents.ps1` and verify 54 files generated
- [ ] Compare generated Claude agents to current Claude agents
- [ ] Verify semantic equivalence
- [ ] Run CI validation

---

**Design By**: Architect (methodology applied by orchestrator)
**Date**: 2025-12-15
