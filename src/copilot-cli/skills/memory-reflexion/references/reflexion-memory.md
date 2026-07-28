# Reflexion Memory

<!-- vendor-portability: declared. This reference documents upstream memory artifact paths under .agents/memory/ for the episodic memory schema. It is reference material only; runtime writes stay in the canonical memory scripts and their path helpers. Issue #2050. -->

## Overview

The Reflexion Memory module (`.claude/skills/memory/scripts/extract_session_episode.py`) provides episodic replay. This implements Tier 2 of the memory architecture.

ADR-088 removed the Tier 3 derived causal graph this module once maintained: nothing read it, and its aggregated output was noise. Episodes are unaffected and remain the system of record.

**ADR**: ADR-038 Reflexion Memory Schema, ADR-088 Causal Tier Removal

**Task**: M-005 (Phase 2A Memory System)

## Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                   Episodic Memory (Tier 2)                    │
│      Session transcripts, decision sequences, outcomes        │
│                    (.agents/memory/episodes/)                        │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
        No code reads these files today. The query API has no
        caller outside its own module, its tests, and doc
        examples. Tracked in issue 3630.
```

## Core Concepts

### Episodic Memory

Episodes are structured extracts from session logs, optimized for replay and analysis.

**Key Features**:

- Decision sequences with timestamps
- Event chains (commits, errors, milestones)
- Outcome classification (success, partial, failure)
- Metrics (duration, tool calls, errors, recoveries)
- Lessons learned

**Token Efficiency**: Episodes are 500-2000 tokens vs 10K-50K tokens for full session logs.

## Storage Formats

### Episode Schema

**Location**: `.agents/memory/episodes/episode-{session-id}.json`

```json
{
  "id": "episode-2026-01-01-session-126",
  "session": "2026-01-01-session-126",
  "timestamp": "2026-01-01T17:00:00Z",
  "outcome": "success",
  "task": "Implement MemoryRouter module",
  "decisions": [
    {
      "id": "d001",
      "timestamp": "2026-01-01T17:05:00Z",
      "type": "design",
      "context": "Choosing routing strategy",
      "chosen": "Serena-first routing",
      "rationale": "Lower latency, no network dependency",
      "outcome": "success",
      "effects": ["d002", "d003"]
    }
  ],
  "events": [
    {
      "id": "e001",
      "timestamp": "2026-01-01T17:10:00Z",
      "type": "commit",
      "content": "Created memory_router module (search_memory.py)",
      "caused_by": ["d001"],
      "leads_to": ["e002"]
    }
  ],
  "metrics": {
    "duration_minutes": 45,
    "tool_calls": 87,
    "errors": 2,
    "recoveries": 2,
    "commits": 3,
    "files_changed": 8
  },
  "lessons": [
    "Pre-commit hooks check all markdown, not just staged files",
    "Use --no-verify with documented justification for unrelated failures"
  ]
}
```

## Usage

### Episode Queries

```powershell
# Import reflexion_memory module functions
# (Python equivalent: python3 .claude/skills/memory/scripts/extract_session_episode.py)

# Get specific episode
$episode = Get-Episode -SessionId "2026-01-01-session-126"

# Get recent failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)

# Get all successes
$successes = Get-Episodes -Outcome "success" -MaxResults 50

# Get decision sequence from episode
$decisions = Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"
```

### System Status

```powershell
# Get reflexion memory status
$status = Get-ReflexionMemoryStatus

Write-Host "Episodes: $($status.Episodes.Count) in $($status.Episodes.Path)"
```

## Functions

### Episode Functions

#### Get-Episode

Retrieves an episode by session ID.

**Syntax**:

```powershell
Get-Episode -SessionId <String>
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| SessionId | String | Yes | Session identifier (e.g., "2026-01-01-session-126") |

**Returns**: `PSCustomObject` with episode data, or `$null` if not found.

**Example**:

```powershell
$episode = Get-Episode -SessionId "2026-01-01-session-126"
if ($episode) {
    Write-Host "Task: $($episode.task)"
    Write-Host "Outcome: $($episode.outcome)"
    Write-Host "Decisions: $($episode.decisions.Count)"
}
```

#### Get-Episodes

Retrieves episodes matching criteria.

**Syntax**:

```powershell
Get-Episodes
    [-Outcome <String>]
    [-Since <DateTime>]
    [-MaxResults <Int32>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| Outcome | String | No | - | Filter by outcome: success, partial, failure |
| Since | DateTime | No | - | Filter episodes since this date |
| MaxResults | Int32 | No | 20 | Maximum number of episodes to return (1-100) |

**Returns**: Array of `PSCustomObject` sorted by timestamp descending.

**Example**:

```powershell
# Get last week's failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)

foreach ($ep in $failures) {
    Write-Host "$($ep.session): $($ep.task) - $($ep.lessons.Count) lessons learned"
}
```

#### New-Episode

Creates a new episode from structured data.

**Syntax**:

```powershell
New-Episode
    -SessionId <String>
    -Task <String>
    -Outcome <String>
    [-Decisions <Array>]
    [-Events <Array>]
    [-Lessons <Array>]
    [-Metrics <Hashtable>]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| SessionId | String | Yes | - | Source session identifier |
| Task | String | Yes | - | High-level task description |
| Outcome | String | Yes | - | Episode outcome: success, partial, failure |
| Decisions | Array | No | @() | Array of decision objects |
| Events | Array | No | @() | Array of event objects |
| Lessons | Array | No | @() | Array of lesson strings |
| Metrics | Hashtable | No | @{} | Metrics hashtable |

**Returns**: Hashtable with episode data. Also writes JSON file to `.agents/memory/episodes/`.

**Example**:

```powershell
$episode = New-Episode `
    -SessionId "2026-01-01-session-130" `
    -Task "Implement feature X" `
    -Outcome "success" `
    -Decisions @(
        @{
            id = "d001"
            timestamp = (Get-Date).ToString("o")
            type = "design"
            context = "Choosing architecture"
            chosen = "Event-driven design"
            rationale = "Better scalability"
            outcome = "success"
            effects = @()
        }
    ) `
    -Lessons @("Event-driven design reduced coupling")
```

#### Get-DecisionSequence

Retrieves the decision sequence from an episode.

**Syntax**:

```powershell
Get-DecisionSequence -EpisodeId <String>
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| EpisodeId | String | Yes | Episode identifier (e.g., "episode-2026-01-01-126") |

**Returns**: Array of decision objects sorted by timestamp.

**Example**:

```powershell
$decisions = Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"

foreach ($d in $decisions) {
    Write-Host "$($d.timestamp): $($d.type) - $($d.chosen)"
}
```

### Status Functions

#### Get-ReflexionMemoryStatus

Gets the status of the reflexion memory system.

**Syntax**:

```powershell
Get-ReflexionMemoryStatus
```

**Returns**: `PSCustomObject` with:

- `Episodes`: Path and count of episode files
- `Configuration`: EpisodesPath setting

**Example**:

```powershell
$status = Get-ReflexionMemoryStatus

Write-Host "=== Reflexion Memory Status ==="
Write-Host "Episodes:"
Write-Host "  Path: $($status.Episodes.Path)"
Write-Host "  Count: $($status.Episodes.Count)"
```

## Scripts

### extract_session_episode.py

Extracts episode data from session logs.

**Syntax**:

```bash
python3 scripts/extract_session_episode.py <session-log-path>
    [--output-path <String>]
    [--force | --preserve]
    [--pending-stage]
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| session_log_path | String | Yes | - | Positional. Path to the session log file |
| --output-path | String | No | .agents/memory/episodes/ | Output directory for episode JSON |
| --force | Switch | No | - | Overwrite an existing episode file |
| --preserve | Switch | No | - | Merge fresh extraction over an existing episode. Mutually exclusive with --force |
| --pending-stage | Switch | No | - | Count the not-yet-staged episode file in the staged-file total |

**Extraction Targets**:

- Session metadata (date, objectives, status)
- Decisions made during the session
- Events (commits, errors, milestones, tests)
- Metrics (duration, file counts, errors, recoveries)
- Lessons learned

**Example**:

```bash
python3 scripts/extract_session_episode.py \
    ".agents/sessions/2026-01-01-session-126.json"

# Output:
# Episode extracted:
#   ID:        episode-2026-01-01-session-126
#   Session:   2026-01-01-session-126
#   Outcome:   success
#   Decisions: 5
#   Events:    12
#   Lessons:   3
#   Output:    .agents/memory/episodes/episode-2026-01-01-session-126.json
```

## Integration

### With Retrospective Agent

The retrospective agent auto-extracts episodes at session end:

```bash
# In retrospective agent workflow
SESSION_LOG=".agents/sessions/${SESSION_ID}.md"

# Extract episode
python3 scripts/extract_session_episode.py "$SESSION_LOG"

# Store in Serena/Forgetful
EPISODE_SUMMARY="Episode ${SESSION_ID}: ${TASK} outcome=${OUTCOME}"
# ... save to memory systems
```

### With Session Protocol

Episode extraction is part of session end checklist:

```markdown
## Session End (BLOCKING)

- [ ] Complete session log
- [ ] Extract episode: `scripts/extract_session_episode.py`
- [ ] Update Serena memory
- [ ] Commit all changes (including .agents/memory/episodes/)
```

### With Memory Router

Future enhancement to search episodes via Memory Router:

```powershell
# Not yet implemented - placeholder
Search-Memory -Query "routing decision" -IncludeEpisodes
```

## Use Cases

### Review Past Failures

```powershell
# Get last month's failures
$failures = Get-Episodes -Outcome "failure" -Since (Get-Date).AddMonths(-1)

foreach ($failure in $failures) {
    Write-Host "`n=== $($failure.session) ==="
    Write-Host "Task: $($failure.task)"
    Write-Host "`nLessons Learned:"
    foreach ($lesson in $failure.lessons) {
        Write-Host "  - $lesson"
    }

    # Find what caused the failure
    $errorEvents = $failure.events | Where-Object { $_.type -eq "error" }
    if ($errorEvents) {
        Write-Host "`nErrors:"
        foreach ($err in $errorEvents) {
            Write-Host "  - $($err.content)"
        }
    }
}
```

### Compare Decision Outcomes

```powershell
# Get all episodes with routing decisions
$routingEpisodes = Get-Episodes -MaxResults 100 | Where-Object {
    $_.decisions | Where-Object { $_.context -match "routing" }
}

# Group by outcome
$outcomes = $routingEpisodes | Group-Object -Property outcome

foreach ($group in $outcomes) {
    Write-Host "$($group.Name): $($group.Count) episodes"

    # Show common patterns
    $decisions = $group.Group.decisions | Where-Object { $_.context -match "routing" }
    $chosen = $decisions | Group-Object -Property chosen | Sort-Object Count -Descending

    foreach ($choice in $chosen) {
        Write-Host "  - $($choice.Name): $($choice.Count) times"
    }
}
```

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Get-Episode | <50ms | Single JSON file read |
| Get-Episodes | ~200ms | O(n) scan of episode directory |
| Get-DecisionSequence | <10ms | In-memory array sort |
| Extract-SessionEpisode | ~500ms | Parse markdown, extract structured data |

## Best Practices

### For Agents

1. **Learn from failures**: Query `Get-Episodes -Outcome "failure"` for similar scenarios


### For Episode Extraction

1. **Run at session end**: Extract episodes while session is fresh
2. **Validate extraction**: Check episode JSON for completeness
3. **Commit with session**: Include episodes in session commit

## Troubleshooting

### Episode Not Found

**Symptoms**: `Get-Episode` returns `$null`

**Solutions**:

1. Verify episode file exists: `Test-Path ".agents/memory/episodes/episode-$sessionId.json"`
2. Check session ID format: Must match file naming convention
3. Re-extract from session log: `scripts/extract_session_episode.py`

## Related Documentation

- [Memory Router](memory-router.md) - Tier 1 semantic memory (Serena + Forgetful)
- [Benchmarking](benchmarking.md) - Performance measurement
- [API Reference](api-reference.md) - Complete function signatures
- ADR-038 - Reflexion Memory Schema
- ADR-007 - Memory-First Architecture
