# Pattern: Agent Generation (Three Platforms)

## Context
The ai-agents repository generates agent files for multiple platforms from shared templates.

## Key Learnings

### Platform Architecture
1. **Claude Code** (`src/claude/`) - Manually maintained, NOT auto-generated
2. **VS Code Agents** (`src/vs-code-agents/`) - Auto-generated from templates
3. **Copilot CLI** (`src/copilot-cli/`) - Auto-generated from templates

### Why Claude is Separate
- Different frontmatter: `name` + `model` vs `description` + `tools_*`
- Different handoff syntax: `Task(subagent_type, prompt)` vs `runSubagent(...)`
- Different memory prefix: `mcp__cloudmcp-manager__*` vs `cloudmcp-manager/`
- Platform-specific sections like "Claude Code Tools"

### Generator Commands
```powershell
# Regenerate VS Code and Copilot CLI files
pwsh build/Generate-Agents.ps1

# Validate without overwriting
pwsh build/Generate-Agents.ps1 -Validate
```

### Sync Strategy
1. Edit shared content in templates first
2. Run Generate-Agents.ps1 to update VS Code/Copilot
3. Manually port relevant changes to Claude if needed
4. Claude-only content stays in Claude files only

## Evidence
Session: 2024 agent synchronization task
Files: `.agents/analysis/claude-vs-template-differences.md`

## Atomicity Score: 95%
Specific, measurable, actionable guidance for agent file management.
