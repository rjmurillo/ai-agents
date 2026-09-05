# Memory System Skill Reference

## Overview

The memory system exposes functionality through Claude Code skills - standardized Python scripts that agents can invoke. This document provides complete reference for all memory-related skills.

## Skill Location

```text
.claude/
└── skills/
    └── memory/
        └── scripts/
            └── search_memory.py
```

## search_memory.py

### Synopsis

Unified memory search across Serena and the episode store.

### Description

Agent-facing skill script that searches the two file-based memory stores. The semantic backend it also queried, and the two flags that selected between the stores, were removed in issue #5574.

### Syntax

```bash
search_memory.py
    --query <String>
    [--max-results <Int32>]
    [--format <String>]
```

### Parameters

#### --query

Search query string.

| Property | Value |
|----------|-------|
| Type | String |
| Position | 0 |
| Required | Yes |
| Length | 1-500 characters |
| Pattern | `^[a-zA-Z0-9\s\-.,_()&:]+$` |

**Allowed Characters**:

- Letters (a-z, A-Z)
- Numbers (0-9)
- Spaces
- Punctuation: `-` `.` `,` `_` `(` `)` `&` `:`

**Examples**:

```text
"PowerShell arrays"           # Valid
"git hooks: pre-commit"       # Valid
"authentication (OAuth 2.0)"  # Valid
"invalid<script>query"        # Invalid - special characters
```

#### --max-results

Maximum number of results to return.

| Property | Value |
|----------|-------|
| Type | Int32 |
| Position | Named |
| Required | No |
| Default | 10 |
| Range | 1-100 |

#### --format

Output format for results.

| Property | Value |
|----------|-------|
| Type | String |
| Position | Named |
| Required | No |
| Default | Json |
| Values | Json, Table |

**Json Format**: Structured output for programmatic consumption:

```json
{
  "Query": "PowerShell arrays",
  "Count": 3,
  "Source": "Unified",
  "Results": [...],
  "Diagnostic": {
    "Serena": { "Available": true, "Path": ".serena/memories" },
    "Episodes": { "Available": true, "Path": ".agents/memory/episodes" }
  }
}
```

**Table Format**: Human-readable formatted table:

```text
Name                    Source    Score Preview
----                    ------    ----- -------
powershell-arrays       Serena    1.0   PowerShell arrays need @() for...
array-handling          Episodes  0.85  Common array gotchas include...
```

### Output Structure

#### JSON Output

```json
{
  "Query": "string",
  "Count": 0,
  "Source": "Unified",
  "Results": [
    {
      "Name": "memory-name",
      "Source": "Serena|Episodes",
      "Score": 1.0,
      "Path": "/path/to/memory",
      "Content": "Full memory content..."
    }
  ],
  "Diagnostic": {
    "Serena": {
      "Available": true,
      "Path": ".serena/memories"
    },
    "Episodes": {
      "Available": true,
      "Path": ".agents/memory/episodes"
    }
  }
}
```

#### Error Output

```json
{
  "Error": "Error message",
  "Query": "original query",
  "Details": "Stack trace..."
}
```

### Examples

#### Example 1: Basic Search

```bash
python3 .claude/skills/memory/scripts/search_memory.py --query "git hooks"
```

Output:

```json
{
  "Query": "git hooks",
  "Count": 5,
  "Source": "Unified",
  "Results": [
    {
      "Name": "git-hooks-pre-commit",
      "Source": "Serena",
      "Score": 1.0,
      "Path": ".serena/memories/git-hooks-pre-commit.md",
      "Content": "Pre-commit hooks validate..."
    }
  ]
}
```

#### Example 2: Table Format

```bash
python3 .claude/skills/memory/scripts/search_memory.py \
    --query "PowerShell arrays" \
    --format table
```

Output:

```text
Name                    Source Score Preview
----                    ------ ----- -------
powershell-array-handling Serena 1.0   PowerShell arrays need @() f...
powershell-arrays        Serena 1.0   Common array operations incl...
```

#### Example 3: Limited Results

```bash
python3 .claude/skills/memory/scripts/search_memory.py \
    --query "authentication" \
    --max-results 3
```

#### Example 5: From Shell Script

```bash
result=$(python3 .claude/skills/memory/scripts/search_memory.py \
    --query "CI pipelines" \
    --max-results 5)

echo "$result" | python3 -c "import sys,json; data=json.load(sys.stdin); [print(f'=== {m[\"Name\"]} ===\n{m[\"Content\"]}') for m in data['Results']]"
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (see JSON output for details) |

### Dependencies

| Dependency | Required | Purpose |
|------------|----------|---------|
| Python 3.12+ | Yes | Script execution |
| memory router module | Yes | Core search functionality |
| Serena MCP | Yes | Lexical memory search |

### Validation

The skill validates input before processing:

1. **Query Length**: Must be 1-500 characters
2. **Query Characters**: Must match allowed pattern
3. **--max-results Range**: Must be 1-100
4. **--format Value**: Must be json or table
5. **Module Existence**: Memory router module must be importable

### Error Handling

The skill handles errors gracefully:

```python
try:
    results = search_memory(search_params)
    # ... output results
except Exception as e:
    error_output = {
        "Error": str(e),
        "Query": query,
        "Details": traceback.format_exc()
    }
    print(json.dumps(error_output, indent=2))
    sys.exit(1)
```

### Security Considerations

1. **Input Validation**: Query is validated against a strict pattern to prevent injection
2. **No Shell Expansion**: Query is passed as-is, no variable expansion
3. **Sandboxed Execution**: Skill runs in Python subprocess
4. **Read-Only**: Skill only reads memory, never writes

### Performance

| Metric | Typical Value |
|--------|---------------|
| Cold start | 100-200ms |
| Warm start | 50-100ms |
| Lexical search | 300-500ms |
| Semantic search | 500-1000ms |
| Combined search | 600-1200ms |

### Integration with Agent Workflows

#### Session Start Pattern

```bash
# At session start - search relevant context
context=$(python3 .claude/skills/memory/scripts/search_memory.py \
    --query "[session objectives]" \
    --max-results 10)

echo "$context" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data['Count'] > 0:
    print(f'Found {data[\"Count\"]} relevant memories')
    for result in data['Results']:
        print(f'- {result[\"Name\"]}: {result[\"Content\"][:100]}...')
"
```

#### Pre-Decision Pattern

```bash
# Before making technical decisions
patterns=$(python3 .claude/skills/memory/scripts/search_memory.py \
    --query "[decision topic] patterns")

echo "$patterns" | python3 -c "
import sys, json, re
data = json.load(sys.stdin)
relevant = [r for r in data['Results'] if re.search('success|recommended|best practice', r['Content'])]
"
```

## Additional Scripts

The memory skill includes additional scripts beyond search_memory.py. See the full skill documentation for details:

| Script | Purpose | Documentation |
|--------|---------|---------------|
| test_memory_health.py | System health check | [SKILL.md](../../memory/SKILL.md) |
| extract_session_episode.py | Episode extraction | [SKILL.md](../../memory/SKILL.md) |
| measure_memory_performance.py | Benchmarking | [SKILL.md](../../memory/SKILL.md) |

**Module Functions** (reflexion_memory module):

- `get_episode`, `get_episodes` - Query episodic memory
- `get_decision_sequence` - Read the decisions one episode recorded
- `new_episode` - Create an episode record

## Future Skills

The following skills are planned for future releases:

### save_memory.py (Planned)

Store new memories to Serena.

## Related Documentation

- [Memory Router](memory-router.md) - Underlying module
- [Agent Integration](../../memory-gate/references/agent-integration.md) - Agent workflows
- [API Reference](api-reference.md) - Complete API
- [Quick Start](quick-start.md) - Common patterns
