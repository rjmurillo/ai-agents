# Memory Management Workflow

> **Status**: Operational Guidance
> **Last Updated**: 2026-01-03
> **Related**: ADR-007 (Memory-First Architecture), SESSION-PROTOCOL.md

This document describes the unified memory management workflow across three memory systems: **Serena**, **Forgetful**, and **Claude-Mem**.

---

## Three-Tier Memory Architecture

| System | Purpose | Scope | Persistence | Export/Import |
|--------|---------|-------|-------------|---------------|
| **Serena** | Project-specific context, code symbols | Single project | `.serena/memories/` (git) | Manual (filesystem) |
| **Forgetful** | Cross-project semantic memory | All projects | PostgreSQL + HNSW | `execute_forgetful_tool` |
| **Claude-Mem** | Session observations, prompts | Claude Code sessions | SQLite | `pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1` |

---

## Memory System Selection Guide

### Use Serena When

- **Project-specific patterns**: Patterns that only apply to ai-agents
- **Code architecture**: File structure, module relationships, symbol locations
- **Cross-session context**: Information needed by next session on this project
- **Integration points**: Where to find specific functionality in codebase

**Example**: "The GitHub skills are located in `.claude/skills/github/scripts/` and use PowerShell modules in `.claude/skills/modules/`"

### Use Forgetful When

- **Cross-project learnings**: Patterns applicable to any project
- **Atomic concepts**: Single, reusable insights (<2000 chars)
- **Relationships**: Linking related concepts across knowledge graph
- **Discovery**: Semantic search for "what have I learned about X"

**Example**: "Trust-based compliance achieves <50% success; verification-based BLOCKING gates achieve 100%"

### Use Claude-Mem When

- **Session history**: Full transcript of what happened in specific session
- **Timeline analysis**: When did we make decision X
- **Debugging context**: Re-trace steps from previous session
- **Sharing recent learnings**: Export this week's observations to teammates

**Example**: "In session 229, we identified five frustration patterns. Here's the full conversation context."

---

## Session Workflow Integration

### Session Start

```markdown
### Phase 1: Serena Initialization (BLOCKING)
1. `mcp__serena__activate_project`
2. `mcp__serena__initial_instructions`

### Phase 2: Context Retrieval (BLOCKING)
1. Read `.agents/HANDOFF.md` (read-only reference)
2. Read `memory-index` from Serena
3. Load task-relevant Serena memories

### Phase 2.1: Import Shared Memories (RECOMMENDED)
1. Check `.claude-mem/memories/imports/` for new exports
2. Import: `npx tsx scripts/import-memories.ts [file].json`
3. Document import count in session log
```

### During Session

**Forgetful**: Create atomic memories for cross-project learnings

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "One concept summary",
    "content": "Detailed explanation (<2000 chars)",
    "context": "Why this matters",
    "keywords": ["keyword1", "keyword2"],
    "tags": ["category"],
    "importance": 7-10,
    "project_ids": [1]
})
```

**Serena**: Update project memories for cross-session context

```python
mcp__serena__write_memory(
    memory_file_name="topic-name",
    content="# Topic\n\n[Markdown content]"
)
```

### Session End

```markdown
### Phase 0.5: Export Session Memories (RECOMMENDED)
1. Export Claude-Mem observations using PowerShell wrapper:
   pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 \
     -Query "session NNN" -SessionNumber NNN -Topic "topic"

2. Security review runs automatically (mandatory gate)
3. Commit export to git if review passes
4. Document export path in session log

### Phase 1: Documentation Update (REQUIRED)
1. Update Serena memory for cross-session context
2. Complete session log
3. DO NOT modify HANDOFF.md (read-only reference)
```

---

## Claude-Mem Export/Import Detailed Workflow

### Export Commands

**By session number** (using PowerShell wrapper):

```powershell
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 `
  -Query "session 229" -SessionNumber 229 -Topic "frustrations"
# Output: .claude-mem/memories/2026-01-03-session-229-frustrations.json
```

**By topic/theme** (using PowerShell wrapper):

```powershell
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 `
  -Query "frustration pattern" -Topic "frustrations"
# Output: .claude-mem/memories/2026-01-03-frustrations.json
```

**All observations** (filtered by plugin):

```powershell
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 `
  -Query "" -Topic "all-memories"
# NOTE: Empty query exports observations matching plugin filters (project, date, session)
# Output: .claude-mem/memories/2026-01-03-all-memories.json
```

**Direct plugin call** (advanced users only):

```bash
# Bypass PowerShell wrapper for project/date filtering
npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts \
  "" output.json --project=ai-agents
```

### Import Commands

**Single file** (direct plugin call):

```bash
npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts \
  .claude-mem/memories/shared-learnings.json
```

**Bulk import** (using PowerShell wrapper):

```powershell
# Auto-imports all .json files from .claude-mem/memories/
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
```

**Manual bulk import** (advanced users):

```bash
for file in .claude-mem/memories/*.json; do
    npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts "$file"
done
```

### Privacy Review Before Export

**CRITICAL**: Security review is MANDATORY and runs automatically during export.

```powershell
# Export script automatically runs security review
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "..." -Topic "..."
# Security review runs automatically after export
# Export blocked if sensitive data detected

# Manual security review (if needed)
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile .claude-mem/memories/[file].json
```

### Naming Conventions

| Export Type | Naming Pattern | Example |
|-------------|----------------|---------|
| Session-specific | `YYYY-MM-DD-session-NNN-topic.json` | `2026-01-03-session-229-frustrations.json` |
| Thematic | `YYYY-MM-DD-theme.json` | `2026-01-03-testing-philosophy.json` |
| Onboarding | `onboarding-YYYY-MM-DD.json` | `onboarding-2026-01-03.json` |

---

## Duplicate Prevention

All three memory systems handle duplicates differently:

### Serena

**Strategy**: Filesystem-based, manual deduplication

- Same filename = overwrite
- Different filename = separate memories
- Responsibility: Agent must check existing memories before writing

### Forgetful

**Strategy**: Semantic similarity + manual linking

- Auto-links similar memories during creation
- Agent should check `similar_memories` in response
- Manually link with `link_memories` tool if needed

### Claude-Mem

**Strategy**: Composite key matching (automatic)

| Record Type | Detection Key |
|-------------|---------------|
| Sessions | `claude_session_id` |
| Summaries | `sdk_session_id` |
| Observations | `sdk_session_id` + `title` + `created_at_epoch` |
| Prompts | `claude_session_id` + `prompt_number` |

**Implication**: Safe to reimport the same file multiple times. Duplicates are automatically skipped.

---

## Memory Atomicity Guidelines

### Forgetful Memory Size

**Rule**: Each memory MUST be <2000 characters and contain ONE concept.

**Good** (atomic):

```markdown
Title: "Trust-Based Compliance Failure (<50% vs 100%)"
Content: "Trust-based guidance achieves <50% compliance. Verification-based
BLOCKING gates achieve 100%. Replace trust with: BLOCKING keyword, MUST language,
verification method, tool output in transcript, clear consequence."
```

**Bad** (non-atomic):

```markdown
Title: "Session 229 Learnings"
Content: "We learned about frustrations, trust-based compliance, branch verification,
skills-first violations, HANDOFF.md conflicts, PR #226 disaster, the 100% rule,
the 5-instance threshold, December 22 timeline, and token economics."
```

### Serena Memory Structure

Serena memories use Markdown with sections:

```markdown
# Memory Title

## Core Insight

[1-2 sentence summary]

## Key Patterns

- Pattern 1: [Description]
- Pattern 2: [Description]

## Integration Points

- Agent: [Which agents need this]
- Protocol: [Which protocols reference this]
- Skills: [Which skills use this]

## References

- Related Serena memories
- Forgetful memory IDs
- ADRs, sessions, issues
```

---

## Team Collaboration Workflows

### Sharing Your Learnings

1. **During session**: Create Forgetful memories for cross-project concepts
2. **End of session**: Export Claude-Mem observations
3. **Privacy review**: Scan export for sensitive data
4. **Commit to git**: Add export to `.claude-mem/memories/exports/`
5. **Notify team**: PR description mentions new shared learnings

### Importing Teammate's Learnings

1. **Pull latest**: `git pull origin main`
2. **Check exports**: Review `.claude-mem/memories/` for new files
3. **Auto-import**: `pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1`
4. **Verify**: Search for imported memories in Claude-Mem

### Onboarding New Team Members

**Step 1**: Bulk export current knowledge

```powershell
# Export all project-related memories using PowerShell wrapper
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "" -Topic "onboarding"
# Output: .claude-mem/memories/YYYY-MM-DD-onboarding.json

# Security review runs automatically
# Commit if review passes
git add .claude-mem/memories/YYYY-MM-DD-onboarding.json
git commit -m "docs(memory): onboarding export for new team members"
```

**Advanced**: Direct plugin call for project filtering

```bash
npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts \
  "" .claude-mem/memories/onboarding.json --project=ai-agents
```

**Step 2**: New team member imports

```powershell
# Clone repo
git clone https://github.com/user/ai-agents.git
cd ai-agents

# Auto-import all memories using PowerShell wrapper
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1

# Verify import
# Use Claude-Mem search tools or check database directly
```

---

## Troubleshooting

### "Database not found" error

**Cause**: Claude-Mem MCP server not initialized

**Solution**:

```bash
# Check if database exists
ls ~/.claude-mem/

# If not, start Claude Code to initialize MCP servers
# Database will be created automatically
```

### Export contains no observations

**Cause**: Query doesn't match any memories

**Solution**:

```bash
# Try broader query
npx tsx scripts/export-memories.ts "" all.json

# Check total count
cat all.json | jq '.totalObservations'

# List recent observations
npx tsx scripts/search-memories.ts "" | head -20
```

### Import seems to do nothing

**Cause**: Observations already exist (duplicate prevention)

**Solution**:

```bash
# Check if memories were already imported
# Compare created_at timestamps in export with database

# Or just search for expected content
npx tsx scripts/search-memories.ts "[expected topic]"
```

### Forgetful tool unavailable

**Cause**: Forgetful MCP server not running

**Solution**:

```bash
# Test Forgetful health
pwsh scripts/forgetful/Test-ForgetfulHealth.ps1

# Check localhost:8020/mcp
curl http://localhost:8020/mcp
```

---

## Best Practices

### Memory Creation

1. **Serena first**: Check existing Serena memories before creating new ones
2. **Atomic Forgetful**: One concept per memory (<2000 chars)
3. **Link related**: Use `link_memories` to connect related Forgetful memories
4. **Tag consistently**: Use established tags for discoverability

### Export Timing

**Export when**:

- Session created 5+ Forgetful memories
- Significant architectural decisions documented
- Frustration patterns identified
- Testing strategies developed

**Skip export when**:

- Trivial session (1-2 file edits)
- No memorable insights
- Pure bug fix with no learnings

### Import Timing

**Import at session start when**:

- New to the project (onboarding)
- Returning after multi-day break
- Teammate shared important learnings
- Working on related feature to exported memories

**Skip import when**:

- No new files in `imports/` directory
- Already imported this week's exports
- Time-sensitive bug fix (defer to next session)

---

## Metrics and Validation

### Track Export Coverage

Add to session log:

```markdown
### Memory Management

**Forgetful memories created**: 9 (IDs 80-88)
**Serena memory updated**: recurring-frustrations-integration
**Claude-Mem export**: .claude-mem/memories/exports/2026-01-03-session-229-frustrations.json
**Privacy review**: Completed (no sensitive data)
**Export committed**: Yes (SHA: abc123)
```

### Validate Memory Quality

Before exporting, verify:

- [ ] Each Forgetful memory is atomic (<2000 chars, one concept)
- [ ] Memories have importance 7+ (only export high-value learnings)
- [ ] Privacy review completed (no secrets, paths, PII)
- [ ] Naming follows convention (YYYY-MM-DD-session-NNN-topic.json)
- [ ] Session log documents export path

---

## Related Documents

- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md) - Session start/end requirements
- [ADR-007: Memory-First Architecture](../architecture/ADR-007-memory-first-architecture.md)
- [.claude-mem/memories/README.md](../../.claude-mem/memories/README.md) - Export/import detailed workflow
- [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import)

---

## Quick Reference

```bash
# Session Start: Import shared memories
npx tsx scripts/import-memories.ts .claude-mem/memories/imports/[file].json

# Session End: Export observations
npx tsx scripts/export-memories.ts "session NNN" \
  .claude-mem/memories/exports/YYYY-MM-DD-session-NNN-topic.json

# Privacy review
grep -i "api_key\|password\|token\|secret" [export-file].json

# Bulk import (onboarding)
for file in .claude-mem/memories/exports/*.json; do
    npx tsx scripts/import-memories.ts "$file"
done
```
