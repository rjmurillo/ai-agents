# Memory Management Workflow

> **Status**: Operational Guidance
> **Last Updated**: 2026-01-03
> **Related**: ADR-007 (Memory-First Architecture), `AGENTS.md` Retrieval gate

This document describes the unified memory management workflow across three memory systems: **Serena**, **Forgetful**, and **Claude-Mem**.

---

## Three-Tier Memory Architecture

| System | Purpose | Scope | Persistence | Export/Import |
|--------|---------|-------|-------------|---------------|
| **Serena** | Project-specific context, code symbols | Single project | `.serena/memories/` (git) | Manual (filesystem) |
| **Forgetful** | Cross-project semantic memory | All projects | PostgreSQL + HNSW | `execute_forgetful_tool` |
| **Claude-Mem** | Session observations, prompts | Claude Code sessions | SQLite | `python3 .claude-mem/scripts/export_claude_mem_memories.py` |

---

## Memory System Selection Guide

### Use Serena When

- **Project-specific patterns**: Patterns that only apply to ai-agents
- **Code architecture**: File structure, module relationships, symbol locations
- **Cross-session context**: Information needed by next session on this project
- **Integration points**: Where to find specific functionality in codebase

**Example**: "The GitHub skills are located in `.claude/skills/github/scripts/` and use Python modules in `.claude/skills/modules/`"

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
3. Document import count in the transcript or per-issue handoff
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

## Claude-Mem Export/Import Detailed Workflow

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

### Import Commands

**Single file** (direct plugin call):

```bash
npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts \
  .claude-mem/memories/shared-learnings.json
```

**Bulk import** (using Python CLI):

```bash
# Auto-imports all .json files from .claude-mem/memories/
python3 .claude-mem/scripts/import_claude_mem_memories.py
```

**Locating the importer across harnesses**

Claude-Mem is an optional dependency, and its Copilot CLI integration is
MCP-only: it installs an MCP server entry and no importer path. The
bulk-importer script itself does exist upstream, and is the very script this
command invokes, so the gap is not a missing script. The gap is that nothing in
the Copilot integration installs it or points at an installed copy, so there is
a Claude Code default path to fall back on and no Copilot equivalent of it.

External source, pinned: `github.com/thedotmack/claude-mem` at commit
`8f085b4f8861122201a5524be71d696a49a812a3` (2026-08-31),
`src/services/integrations/McpIntegrations.ts` line 242:

```typescript
  'copilot-cli': installMcpIntegration(COPILOT_CLI_CONFIG),
```

`COPILOT_CLI_CONFIG` in the same file (lines 116 to 122) writes
`~/.github/copilot/mcp.json`. At that revision `scripts/import-memories.ts`
exists but nothing routes Copilot to it. This is an external claim about another
project, so it can go stale without anything here changing: re-verify at a newer
revision before relying on it.

The bulk importer resolves its path from configuration before any harness
default.

Canonical source: `.claude-mem/scripts/import_claude_mem_memories.py`. The
resolution order is `resolve_importer` at lines 276 to 289, quoted verbatim:

```python
    if explicit is not None:
        if is_blank(explicit):
            return ImporterResolution(None, _SOURCE_ARGUMENT_BLANK)
        return ImporterResolution(expand_home(explicit, home), _SOURCE_ARGUMENT)

    env_value = env.get(IMPORTER_ENV_VAR, "")
    if not is_blank(env_value):
        return ImporterResolution(expand_home(env_value, home), _SOURCE_ENVIRONMENT)

    default = claude_default_importer(home)
    if default.exists():
        return ImporterResolution(default, _SOURCE_DEFAULT)

    return ImporterResolution(None, _SOURCE_UNSET)
```

Read as: `--importer PATH` first, then the `CLAUDE_MEM_IMPORTER` environment
variable, then the Claude Code plugin default, which is returned only when it
already exists on disk.

The two blank cases are deliberately asymmetric, which the quoted code shows:

| Input | Treated as | Exit | Why |
|-------|-----------|------|-----|
| `CLAUDE_MEM_IMPORTER=""` | unset, falls through | 0 or the next tier's outcome | `VAR=""` is the shell idiom for disabling an inherited value |
| `--importer ""` | configured but invalid | 1 | The caller passed the highest-priority option and supplied nothing usable; falling through would disregard an explicit instruction |

`is_blank` performs the blank test for both tiers. It is detection only: the
original unstripped string is what resolves, because a POSIX filename may
legitimately begin or end with a space, and trimming the value that resolves
would execute a different file or report a real importer missing.

A leading `~` is expanded by `expand_home`, not by `Path.expanduser`. The claims
below are about that function's body, so it is quoted rather than described.
From `.claude-mem/scripts/import_claude_mem_memories.py`, lines 234 to 243,
verbatim:

```python
    mod: PathModule = os.path if pathmod is None else pathmod
    seps = path_separators(mod)
    if raw == "~":
        return home
    if not raw.startswith(tuple("~" + sep for sep in seps)):
        return Path(raw)
    suffix = raw[2:].lstrip(seps)
    if mod.splitdrive(suffix)[0]:
        return Path(raw)
    return home / suffix
```

with `path_separators` at lines 177 to 178 of the same file:

```python
    mod: PathModule = os.path if pathmod is None else pathmod
    return mod.sep + (mod.altsep or "")
```

Four things follow from the quoted lines.

`Path.expanduser` is never called, so the expansion depends on the `home` passed
in and not on the process `HOME` or the password database.

What counts as a separator is asked of a standard-library path module, defaulting
to `os.path`, which IS `posixpath` or `ntpath` for the running platform. A
backslash is therefore a separator on Windows and an ordinary filename character
on POSIX, where `altsep` is None. The same argument means two different things on
the two platforms, deliberately.

A `~otheruser` prefix does not match the `startswith` test, so it falls to
`return Path(raw)` and is returned unchanged. That makes it a relative path
beginning with a literal `~otheruser` segment, so it never resolves against a
stranger's home. The existence check then runs against whatever that relative
path resolves to under the process working directory. That normally does not
exist and the error reports the literal path, but failure is not guaranteed: a
directory literally named `~otheruser` in the working directory would satisfy
the check and be executed. This branch is a non-expansion, not a rejection, and
must not be relied on as one.

A suffix still carrying a drive after the `lstrip` takes the same literal return.
Stripping separators does not make a suffix relative on Windows, where a drive is
a second anchoring mechanism: `~/D:/x` leaves `D:/x`, and joining that onto
`home` yields `D:\x`, dropping `home` exactly as a rooted suffix would. On POSIX
`splitdrive` reports no drive, so `D:` stays an ordinary directory name and the
path expands normally.

```bash
# Point at an importer installed outside the Claude Code plugin root
CLAUDE_MEM_IMPORTER=/opt/claude-mem/scripts/import-memories.ts \
  python3 .claude-mem/scripts/import_claude_mem_memories.py

# Or pass it explicitly
python3 .claude-mem/scripts/import_claude_mem_memories.py \
  --importer /opt/claude-mem/scripts/import-memories.ts
```

The exit code is decided by `is_configured`, not by the absence itself. From
`main` in the same file, lines 367 to 382, quoted verbatim:

```python
    importer = resolution.path
    if importer is None or not importer.exists():
        # is_configured, not the absence itself, decides the exit code: a path
        # the caller named is a real failure, an uninstalled optional plugin is
        # a supported state.
        if resolution.is_configured:
            print(
                f"ERROR: Claude-Mem importer from {resolution.source} not found at: {importer}",
                file=sys.stderr,
            )
            return 1
        print(
            "SKIP: Claude-Mem plugin not installed. Set "
            f"${IMPORTER_ENV_VAR} or pass --importer to enable importing."
        )
        return 0
```

`is_configured` is true only for the argument and environment sources, per the
tuple at line 96 and the property at lines 119 to 128 of the same file. Both are
needed: the property alone does not say which sources count as configured.

```python
_CONFIGURED_SOURCES = (_SOURCE_ARGUMENT, _SOURCE_ARGUMENT_BLANK, _SOURCE_ENVIRONMENT)

    @property
    def is_configured(self) -> bool:
        """True when configuration was attempted, so a miss is a real failure.

        That is: ``--importer`` was supplied, even blank, or a nonblank
        ``CLAUDE_MEM_IMPORTER`` was set. It does NOT mean a usable path exists.
        A blank ``--importer`` names no path and is still configured, which is
        why ``path`` may be None here.
        """
        return self.source in _CONFIGURED_SOURCES
```

| Situation | Exit | Reason |
|-----------|------|--------|
| Nothing configured, no plugin installed | 0 | Optional dependency absent; import skipped with a `SKIP:` line |
| Configured path missing, or importer fails | 1 | The caller named an importer that does not work |
| `--importer ""` | 1 | Highest-priority option supplied with nothing usable |

A Copilot CLI session with no bulk importer on disk therefore skips cleanly
instead of reporting a false failure (issue #4780).

**Stricter/looser/different than canonical**: no divergence. This section
restates the quoted fragments above and adds no rule the script does not
implement. Line numbers are a reading aid and drift with edits; the function and
property names (`resolve_importer`, `ImporterResolution.is_configured`) are the
stable anchors.

**Manual bulk import** (advanced users):

```bash
for file in .claude-mem/memories/*.json; do
    npx tsx ~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts "$file"
done
```

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
3. **Auto-import**: `python3 .claude-mem/scripts/import_claude_mem_memories.py`
4. **Verify**: Search for imported memories in Claude-Mem

### Onboarding New Team Members

**Step 1**: Bulk export current knowledge

```bash
# Export all project-related memories using Python CLI
python3 .claude-mem/scripts/export_claude_mem_memories.py "" --topic "onboarding"
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

```bash
# Clone repo
git clone https://github.com/user/ai-agents.git
cd ai-agents

# Auto-import all memories using Python CLI
python3 .claude-mem/scripts/import_claude_mem_memories.py

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
python3 -m scripts.memory.memory_health

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

Session log creation is discontinued; record this in the per-issue handoff or
transcript instead:

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
- [ ] Export path documented in the per-issue handoff or transcript

---

## Related Documents

- [`.claude/rules/session-logs.md`](../../.claude/rules/session-logs.md) - Session log mechanics
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
