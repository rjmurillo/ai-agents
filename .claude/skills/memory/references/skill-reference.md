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

Unified memory search across Serena and Forgetful.

### Description

Agent-facing skill script that wraps the memory router module. Provides unified memory search with Serena-first routing and optional Forgetful augmentation per ADR-037.

### Syntax

```bash
search_memory.py
    --query <String>
    [--max-results <Int32>]
    [--lexical-only]
    [--semantic-only]
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

#### --lexical-only

Search only Serena (lexical/file-based). Faster and requires no network access.

| Property | Value |
|----------|-------|
| Type | Switch |
| Position | Named |
| Required | No |

**Use When**:

- Forgetful is unavailable
- Performance is critical
- Exact keyword matching is needed
- Offline operation required

#### --semantic-only

Search only Forgetful (semantic/vector). Requires Forgetful MCP server running.

| Property | Value |
|----------|-------|
| Type | Switch |
| Position | Named |
| Required | No |

**Use When**:

- Need conceptual similarity matching
- Keywords are ambiguous
- Exploring related topics
- Finding context without exact terms

**Note**: Will fail if Forgetful is not available. Use try/catch with fallback to --lexical-only.

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
    "Forgetful": { "Available": true, "Endpoint": "http://localhost:8020/mcp" },
    "Cache": { "AgeSeconds": 5.2, "TTLSeconds": 30 },
    "Configuration": {...}
  }
}
```

**Table Format**: Human-readable formatted table:

```text
Name                    Source    Score Preview
----                    ------    ----- -------
powershell-arrays       Serena    1.0   PowerShell arrays need @() for...
array-handling          Forgetful 0.85  Common array gotchas include...
```

### Output Structure

#### JSON Output

```json
{
  "Query": "string",
  "Count": 0,
  "Source": "Unified|Serena|Forgetful",
  "Results": [
    {
      "Name": "memory-name",
      "Source": "Serena|Forgetful",
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
    "Forgetful": {
      "Available": true,
      "Endpoint": "http://localhost:8020/mcp"
    },
    "Cache": {
      "AgeSeconds": 5.2,
      "TTLSeconds": 30
    },
    "Configuration": {
      "SerenaPath": ".serena/memories",
      "ForgetfulPort": 8020,
      "ForgetfulTimeout": 500,
      "MaxResults": 10
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

#### Example 2: Lexical Only with Table Format

```bash
python3 .claude/skills/memory/scripts/search_memory.py \
    --query "PowerShell arrays" \
    --lexical-only \
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

#### Example 4: Semantic Search

```bash
python3 .claude/skills/memory/scripts/search_memory.py \
    --query "user login security" \
    --semantic-only
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
| Forgetful MCP | No | Semantic memory search |

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
# Per SESSION-PROTOCOL.md - search relevant context
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
    --query "[decision topic] patterns" \
    --lexical-only)

echo "$patterns" | python3 -c "
import sys, json, re
data = json.load(sys.stdin)
relevant = [r for r in data['Results'] if re.search('success|recommended|best practice', r['Content'])]
"
```

#### Fallback Pattern

```bash
# Try semantic, fall back to lexical
result=$(python3 .claude/skills/memory/scripts/search_memory.py \
    --query "[topic]" \
    --semantic-only 2>&1)

if [ $? -ne 0 ]; then
    echo "Semantic search failed, using lexical" >&2
    result=$(python3 .claude/skills/memory/scripts/search_memory.py \
        --query "[topic]" \
        --lexical-only)
fi
```

## Additional Scripts

The memory skill includes additional scripts beyond search_memory.py. See the full skill documentation for details:

| Script | Purpose | Documentation |
|--------|---------|---------------|
| check_memory_health.py | System health check | [SKILL.md](.claude/skills/memory/SKILL.md) |
| extract_session_episode.py | Episode extraction | [SKILL.md](.claude/skills/memory/SKILL.md) |
| update_causal_graph.py | Causal graph updates | [SKILL.md](.claude/skills/memory/SKILL.md) |
| measure_memory_performance.py | Benchmarking | [SKILL.md](.claude/skills/memory/SKILL.md) |

**Module Functions** (reflexion_memory module):

- `get_episode`, `get_episodes` - Query episodic memory
- `get_causal_path` - Trace causal relationships
- `get_patterns`, `get_anti_patterns` - Pattern discovery

## Future Skills

The following skills are planned for future releases:

### save_memory.py (Planned)

Store new memories to Serena with optional Forgetful sync.

## Related Documentation

- [Memory Router](memory-router.md) - Underlying module
- [Agent Integration](agent-integration.md) - Agent workflows
- [API Reference](api-reference.md) - Complete API
- [Quick Start](quick-start.md) - Common patterns
