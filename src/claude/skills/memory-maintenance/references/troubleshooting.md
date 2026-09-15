# Memory System Troubleshooting Guide

## Overview

This guide provides solutions to common issues with the memory system. Issues are organized by component and symptom.

## Quick Diagnostics

### System Status Check

Run these commands to quickly assess system health:

One script covers every tier:

```bash
# All tiers, JSON (default)
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/test_memory_health.py"

# Human-readable
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/test_memory_health.py" --format table
```

### Expected Healthy Output

```json
{
  "timestamp": "2026-07-29T07:27:03.569031+00:00",
  "overall": "healthy",
  "tiers": {
    "tier0_working": {"name": "Working Memory", "available": true},
    "tier1_semantic": {
      "name": "Semantic Memory",
      "available": true,
      "serena":    {"available": true,  "count": 95}
    },
    "tier2_episodic": {
      "name": "Episodic Memory",
      "available": true,
      "episodes": {"available": true, "count": 322}
    }
  },
  "modules": [
    {"name": "memory_router",    "available": true},
    {"name": "reflexion_memory", "available": true}
  ],
  "recommendations": []
}
```

`overall` reports `unhealthy` only when Tier 1 itself is unreadable. Every
tier is backed by files in the working tree, so a tier reporting
`available: false` means a missing or unreadable directory, not a service
outage.

## Memory Router Issues

### Issue: No Results from Search

**Symptoms**:

- `search_memory` returns an empty list
- Expected memories not found

**Diagnosis**:

```python
import os
import sys
_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".claude"
sys.path.insert(0, f"{_root}/skills/memory")
from memory_core.memory_router import get_memory_router_status

status = get_memory_router_status()
print(status["Serena"])  # {"Available": ..., "Path": ...}
```

```bash
# Count memories, then try an exact filename match
ls .serena/memories/*.md | wc -l
ls .serena/memories/ | grep keyword
```

Serena scores on the **filename**, not the body, so a keyword that appears only
inside a memory will not match.

**Solutions**:

| Cause | Solution |
|-------|----------|
| Serena path incorrect | Verify `.serena/memories/` exists |
| No memories created yet | Create initial memories |
| Query too specific | Try broader search terms |
| Special characters in query | Use only alphanumeric + allowed punctuation |

### Issue: Query Validation Error

**Symptoms**:

- Error: "Cannot validate argument on parameter 'Query'"
- Query rejected before search

**Diagnosis**:

```python
import re

query = "your query here"
print(bool(re.match(r"^[a-zA-Z0-9\s\-.,_()&:]+$", query)))  # want True
```

**Solutions**:

| Invalid Character | Fix |
|-------------------|-----|
| `<` `>` | Remove or replace |
| `'` `"` | Remove or replace with word |
| `$` `@` | Remove |
| `!` `?` | Remove |
| `\` `/` | Use space or hyphen |

**Valid Query Examples**:

```text
"shell arrays"                        # Spaces OK
"git hooks: pre-commit"               # Colons OK
"authentication (OAuth 2.0)"          # Parentheses OK
"CI-CD pipelines"                     # Hyphens OK
```

### Issue: Slow Search Performance

**Symptoms**:

- Searches take >2 seconds
- Timeouts during search

**Diagnosis**:

```bash
time uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/search_memory.py" "test"
```

Or benchmark every tier at once:

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Too many memories | Archive old memories |
| Broad query matching many files | Narrow the query; every match is read in full |
| File system slow | Check disk I/O |
| Large memory files | Split into smaller memories |

**Performance Targets**:

| Operation | Target |
|-----------|--------|
| Lexical search | <500ms |
| Semantic search | <1000ms |
| Combined search | <1200ms |

## Reflexion Memory Issues

### Issue: Episode Not Found

**Symptoms**:

- `get_episode` returns `None`
- Error: "Episode not found for session"

**Diagnosis**:

```bash
SESSION_ID=2026-01-01-session-130

# Does the episode exist?
ls ".agents/memory/episodes/episode-$SESSION_ID.json"

# List available episodes
ls .agents/memory/episodes/*.json | head

# Does the session log exist? Logs are JSON, not markdown.
ls ".agents/sessions/$SESSION_ID.json"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Episode not extracted | Run extract_session_episode.py |
| Wrong session ID format | Use format: YYYY-MM-DD-session-NNN |
| Episode directory missing | Create `.agents/memory/episodes/` |

**Extracting Episode**:

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/extract_session_episode.py" \
    ".agents/sessions/2026-01-01-session-130.json"
```

### Issue: Episode Extraction Fails

**Symptoms**:

- extract_session_episode.py errors
- Incomplete or empty episodes

**Diagnosis**:

```bash
LOG=.agents/sessions/2026-01-01-session-130.json

# Is the log valid JSON, and does it carry the fields the extractor reads?
uv run python -c "
import json, sys
log = json.load(open('$LOG', encoding='utf-8'))
print('keys:', sorted(log))
print('has decisions:', bool(log.get('decisions')))
print('has outcome:', log.get('outcome'))
"

# Schema check
uv run python scripts/validate_session_json.py "$LOG"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Session log incomplete | Complete session log with all sections |
| Missing required sections | Add Decisions and Outcome sections |
| Malformed markdown | Fix markdown syntax |
| Encoding issues | Save as UTF-8 |

**Required Session Log Sections**:

Session logs are JSON, not markdown. See
`.agents/schemas/session-log.schema.json` for the full schema; the extractor
reads these fields:

```json
{
  "sessionId": "2026-01-01-session-130",
  "objective": "What the session aimed to accomplish",
  "decisions": [],
  "events": [],
  "outcome": "success",
  "lessons": [],
  "nextSteps": []
}
```

## Skill Issues

### Issue: Skill Script Not Found

**Symptoms**:

- Error: "Cannot find path"
- Skill invocation fails

**Diagnosis**:

```bash
# Verify skill location
test -f ".claude/skills/memory/scripts/search_memory.py" && echo "exists" || echo "not found"

# List available skills
find .claude/skills -name "*.py" -type f
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Wrong path | Use correct relative path from project root |
| Skill not installed | Verify skill directory structure |
| Permissions issue | Check file permissions |

### Issue: Module Import Failure

**Symptoms**:

- Error: "memory_router module not found"
- Python import fails

**Diagnosis**:

```bash
# Check the module file
ROOT="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
test -f "$ROOT/skills/memory/memory_core/memory_router.py" && echo exists || echo missing

# Test the import the same way the tests do
uv run python -c "
import os, sys
_root = os.environ.get('COPILOT_PLUGIN_ROOT') or os.environ.get('CLAUDE_PLUGIN_ROOT') or '.claude'
sys.path.insert(0, f'{_root}/skills/memory')
from memory_core.memory_router import search_memory
print('OK')
"
```

**Solutions**:

| Cause | Solution |
|-------|----------|
| Skill dir not on `sys.path` | the plugin root on `sys.path` first (see the snippet above) |
| Wrong working directory | Run from project root |
| Module file missing | Verify `.claude/skills/memory/memory_core/` |
| Syntax error in module | Check Python syntax |

`memory_core` is a package inside the skill, not an installed distribution.
`.claude/skills/memory/tests/conftest.py` shows the canonical import setup.

## Directory Structure Issues

### Issue: Memory Directories Missing

**Symptoms**:

- Error: "Directory not found"
- Episode operations fail

**Diagnosis**:

```bash
for dir in .serena/memories .agents/memory/episodes; do
    [ -d "$dir" ] && echo "$dir : present" || echo "$dir : MISSING"
done
```

**Solutions**:

Create missing directories:

```bash
mkdir -p .serena/memories .agents/memory/episodes
```

### Issue: Path Mismatch After Migration

**Symptoms**:

- Scripts reference old paths
- Tests fail with path errors

**Diagnosis**:

```bash
# Check for old path references
grep -rn '\.agents/episodes[^/]' scripts tests
```

**Solutions**:

Update all references to use new paths:

```text
Old Path                    New Path
.agents/episodes/           .agents/memory/episodes/
```

## Common Error Messages

### "Query contains invalid characters"

**Cause**: Query contains characters outside the allowed class.

**Fix**: Use only allowed characters: `a-zA-Z0-9\s\-.,_()&:`

### "Episode not found for session"

**Cause**: Episode not extracted from session log.

**Fix**: Run `extract_session_episode.py` on the session log.

### "Memory file not found"

**Cause**: Serena memory file doesn't exist.

**Fix**: Create memory or check filename spelling.

## Diagnostic Scripts

### Full System Check

`test_memory_health.py` already performs the full check. It covers every tier,
both module files, and emits remediation hints, so do not hand-roll a
diagnostic script.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/test_memory_health.py" --format table
```

It checks:

| Area | What it reports |
|------|-----------------|
| Tier 0 | Working memory (always available) |
| Tier 1 | Serena memory count and path |
| Tier 2 | Episode directory and episode count |
| Modules | `memory_router.py` and `reflexion_memory.py` presence |
| Overall | `healthy`, `degraded`, or `unhealthy`, plus `recommendations` |

Exit code is 0 when the system is healthy or degraded, non-zero when it is
unhealthy, so it is safe to use in a gate.

### Search Performance Test

`measure_memory_performance.py` already benchmarks the router. It warms up,
repeats, and reports the list/match/read split per query, so do not hand-roll a
timing loop.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/memory/scripts/measure_memory_performance.py" \
    --iterations 5 --warmup 1 --format console
```

| Option | Default | Description |
|--------|---------|-------------|
| `--queries ...` | built-in set | Queries to benchmark |
| `--iterations N` | see `--help` | Timed runs per query |
| `--warmup N` | see `--help` | Untimed runs before timing |
| `--format {console,markdown,json}` | `console` | Output format |
| `--serena-path PATH` | `.serena/memories` | Override the Serena store |

Measured on this repo with 95 Serena memories:

```text
=== Summary ===
Serena Average: 0.55ms
```

That figure is the in-process search only. The ~500ms in the performance
targets above is the end-to-end CLI cost, which is dominated by interpreter
startup.

## Getting Help

If issues persist after trying these solutions:

1. **Check Logs**: Review session logs for error context
2. **Verify Configuration**: Ensure ADR-037 and ADR-038 guidelines are followed
3. **Review Documentation**: See [API Reference](../../memory-search/references/api-reference.md) for function details
4. **File Issue**: Create GitHub issue with `memory-system` label

## Related Documentation

- [Skill overview](../SKILL.md) - Memory maintenance skill guide
- [API Reference](../../memory-search/references/api-reference.md) - Complete function signatures
- [Quick Start](../../memory-search/references/quick-start.md) - Common patterns
- [Benchmarking](benchmarking.md) - Performance measurement

<!-- vendor-portability: declared. This guide tells the user to create .agents/memory/episodes/ when the episode directory is missing. The path is the memory store's data dir, created by the fix the doc describes; it is not a read precondition. Issue #2050. -->
