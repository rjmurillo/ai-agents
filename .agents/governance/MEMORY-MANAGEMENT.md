<!-- # taste-lint: ignore file-size  single memory-management policy; splitting scatters one decision procedure -->
# Memory Management Workflow

> **Status**: Operational Guidance
> **Last Updated**: 2026-10-24
> **Related**: ADR-106 (Serena-Only Memory Architecture), `AGENTS.md` Retrieval gate

This document describes the unified memory management workflow across two memory systems: **Serena** and **Claude-Mem**.

---

## Two-Tier Memory Architecture

| System | Purpose | Scope | Persistence | Export |
|--------|---------|-------|-------------|--------|
| **Serena** | Project-specific context, code symbols | Single project | `.serena/memories/` (git) | Manual (filesystem) |
| **Claude-Mem** | Session observations, prompts | Claude Code sessions | SQLite | `python3 .claude-mem/scripts/export_claude_mem_memories.py` |

---

## Memory System Selection Guide

### Use Serena When

- **Project-specific patterns**: Patterns that only apply to ai-agents
- **Code architecture**: File structure, module relationships, symbol locations
- **Cross-session context**: Information needed by next session on this project
- **Integration points**: Where to find specific functionality in codebase

**Example**: "The GitHub skills are located in `.claude/skills/github/scripts/` and use Python modules in `.claude/skills/modules/`"

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
1. `mcp__serena__initial_instructions` (Serena starts active via `.mcp.json --project`)
2. `mcp__serena__activate_project` only when a Serena tool reports no active project

### Phase 2: Context Retrieval (BLOCKING)
1. Read the current per-issue handoff under `.project-toolkit/sessions/handoffs/`, when one exists
2. Read `memory-index` from Serena
3. Load task-relevant Serena memories
```

### During Session

Update Serena project memories for cross-session context.

```python
mcp__serena__write_memory(memory_file_name="topic-name", content="# Topic\n\n[Markdown content]")
```

### Session End

```markdown
### Phase 0.5: Export Session Memories (RECOMMENDED)
1. Export Claude-Mem observations using Python CLI:
   python3 .claude-mem/scripts/export_claude_mem_memories.py \
     "session NNN" --session-number NNN --topic "topic"

2. Security review runs automatically (mandatory gate)
3. Commit export to git if review passes
4. Document export path in the transcript or per-issue handoff

### Phase 1: Documentation Update (REQUIRED)
1. Update Serena memory for cross-session context
2. Do not create a session log; creation is discontinued (`.claude/rules/session-logs.md` MUST 1)
3. DO NOT modify HANDOFF.md (read-only reference)
```

---

## Claude-Mem Export Detailed Workflow

### Export Commands

**By session number** (using Python CLI):

```bash
python3 .claude-mem/scripts/export_claude_mem_memories.py \
  "session 229" --session-number 229 --topic "frustrations"
# Output: .claude-mem/memories/2026-01-03-session-229-frustrations.json
```

**By topic/theme** (using Python CLI):

```bash
python3 .claude-mem/scripts/export_claude_mem_memories.py \
  "frustration pattern" --topic "frustrations"
# Output: .claude-mem/memories/2026-01-03-frustrations.json
```

**All observations** (filtered by plugin):

```bash
python3 .claude-mem/scripts/export_claude_mem_memories.py \
  "" --topic "all-memories"
# NOTE: Empty query exports observations matching plugin filters (project, date, session)
# Output: .claude-mem/memories/2026-01-03-all-memories.json
```

**Direct plugin call** (advanced users only):

```bash
# Bypass Python CLI for project/date filtering
npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts \
  "" output.json --project=ai-agents
```

### Importing

This repository no longer ships a Claude-Mem import procedure (issue #5583, owner decision D21 (2026-10-24)). The bulk import wrapper and its tests are removed. To load an export into a Claude-Mem installation, follow the upstream [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import).

### Privacy Review Before Export

**CRITICAL**: Security review is MANDATORY and runs automatically during export.

```bash
# Export script automatically runs security review
python3 .claude-mem/scripts/export_claude_mem_memories.py "..." --topic "..."
# Security review runs automatically after export
# Export blocked if sensitive data detected

# Manual security review (if needed)
python3 scripts/review_memory_export_security.py .claude-mem/memories/[file].json
```

### Naming Conventions

| Export Type | Naming Pattern | Example |
|-------------|----------------|---------|
| Session-specific | `YYYY-MM-DD-session-NNN-topic.json` | `2026-01-03-session-229-frustrations.json` |
| Thematic | `YYYY-MM-DD-theme.json` | `2026-01-03-testing-philosophy.json` |
| Onboarding | `onboarding-YYYY-MM-DD.json` | `onboarding-2026-01-03.json` |

---

## Duplicate Prevention

Serena handles duplicates through the filesystem. Claude-Mem import deduplication is out of scope now that the import procedure is retired (see Importing above).

### Serena

**Strategy**: Filesystem-based, manual deduplication

- Same filename = overwrite
- Different filename = separate memories
- Responsibility: Agent must check existing memories before writing

---

## Memory Atomicity Guidelines

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
- ADRs, sessions, issues
```

---

## Team Collaboration Workflows

### Sharing Your Learnings

1. **During session**: Update Serena memories for project concepts
2. **End of session**: Export Claude-Mem observations
3. **Privacy review**: Scan export for sensitive data
4. **Commit to git**: Add export to `.claude-mem/memories/exports/`
5. **Notify team**: PR description mentions new shared learnings

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

### A CLAUDE.md stub appears under `.claude/agents/`

**Cause**: The claude-mem plugin writes a `CLAUDE.md` into a folder when that
folder holds tracked files and an observation names one of its direct children.
`.claude/agents/` meets both tests. The Claude Code plugin loader then registers
the stub as a dispatchable agent (issue #5493).

**Measured** (issue #5499): The upstream `generate` command was run from source
in a scratch git repo. The repo had one tracked file, `.claude/agents/analyst.md`,
and one observation that read it. The command logged zero errors and wrote
`.claude/agents/CLAUDE.md`. It wrote the file again after the file was removed
and `CLAUDE_MEM_FOLDER_MD_EXCLUDE` named that folder. The setting
`CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED` was `false` for both runs. The run used
source, not a marketplace install, because no install exists on the machine that
ran it.

External source, pinned: `github.com/thedotmack/claude-mem` at commit
`b3e036fa1341c8ee0e6380e7bbec3b5004001f64` (package version 13.35.0).

- `src/cli/claude-md-commands.ts` line 65, `getTrackedFolders`, takes its folder
  list from `git ls-files`.
- `src/cli/claude-md-commands.ts` line 363, `generateClaudeMd`, reads one
  setting, `CLAUDE_MEM_CONTEXT_OBSERVATIONS`. It reads neither the enabled
  flag nor the exclude list.
- `src/services/worker/agents/ResponseProcessor.ts` line 1071 gates the
  per-session write on `CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED`.
  `src/utils/claude-md-utils.ts` line 304 applies `CLAUDE_MEM_FOLDER_MD_EXCLUDE`
  on that path. This path was read, not run.

This is an external claim about another project, so it can go stale without
anything here changing. Re-verify at a newer revision before relying on it.

**Solution**:

1. Do not run `claude-mem generate` in this checkout.
2. Keep `CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED` at `false`, or add the absolute
   path of `.claude/agents` as an entry in the `CLAUDE_MEM_FOLDER_MD_EXCLUDE`
   JSON array. Both live in `settings.json` in the claude-mem data directory
   (`~/.claude-mem` unless `CLAUDE_MEM_DATA_DIR` points elsewhere), so the
   repository cannot set them for you. These guard only the per-session writer;
   `generate` ignores them.
3. If the stub returns, delete it.
   [`scripts/validation/check_agent_tree_frontmatter.py`](../../scripts/validation/check_agent_tree_frontmatter.py)
   fails pre-PR validation while it exists.
   [`build/scripts/check_agent_content_parity.py`](../../build/scripts/check_agent_content_parity.py)
   has no exemption for it. The stub is caught, not prevented.

---

## Best Practices

### Memory Creation

1. **Serena first**: Check existing Serena memories before creating new ones
2. **Atomic Serena**: One concept per memory file
3. **Link related**: Name related Serena memories in a References section
4. **Tag consistently**: Use established tags for discoverability

### Export Timing

**Export when**:

- Session produced 5+ notable observations
- Significant architectural decisions documented
- Frustration patterns identified
- Testing strategies developed

**Skip export when**:

- Trivial session (1-2 file edits)
- No memorable insights
- Pure bug fix with no learnings

---

## Metrics and Validation

### Track Export Coverage

Session log creation is discontinued; record this in the per-issue handoff or
transcript instead:

```markdown
### Memory Management

**Serena memory updated**: recurring-frustrations-integration
**Claude-Mem export**: .claude-mem/memories/exports/2026-01-03-session-229-frustrations.json
**Privacy review**: Completed (no sensitive data)
**Export committed**: Yes (SHA: abc123)
```

### Validate Memory Quality

Before exporting, verify:

- [ ] Each Serena memory covers one concept
- [ ] Privacy review completed (no secrets, paths, PII)
- [ ] Naming follows convention (YYYY-MM-DD-session-NNN-topic.json)
- [ ] Export path documented in the per-issue handoff or transcript

---

## Related Documents

- [`.claude/rules/session-logs.md`](../../.claude/rules/session-logs.md) - Session log mechanics
- [ADR-007: Memory-First Architecture](../../.project-toolkit/architecture/ADR-007-memory-first-architecture.md)
- [.claude-mem/memories/README.md](../../.claude-mem/memories/README.md) - Export detailed workflow
- [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import)

---

## Quick Reference

```bash
# Session End: Export observations
npx tsx scripts/export-memories.ts "session NNN" \
  .claude-mem/memories/exports/YYYY-MM-DD-session-NNN-topic.json

# Privacy review
grep -i "api_key\|password\|token\|secret" [export-file].json
```
