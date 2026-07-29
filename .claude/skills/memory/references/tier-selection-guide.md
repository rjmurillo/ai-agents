# Tier Selection Guide

Deep guidance for selecting the correct memory tier.

## Tier Characteristics

| Tier | Access Speed | Scope | Reliability | Content Type |
|------|--------------|-------|-------------|--------------|
| **0: Working** | Instant | Current session | 100% | Active context |
| **1: Semantic** | ~500ms | All projects | 100% (Serena) | Facts, patterns, rules |
| **2: Episodic** | ~100ms | This project | 100% (local) | Session history, decisions |

## Selection by Question Type

### "What is X?" → Tier 1

Factual questions about concepts, patterns, or rules.

```bash
python3 .claude/skills/memory/scripts/search_memory.py --query "PowerShell array handling"
```

### "What happened when...?" → Tier 2

Historical questions about past sessions.

```powershell
Get-Episode -SessionId "2026-01-01-session-126"
Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)
```

### "Why did X lead to Y?" → Tier 2

Read the episodes that recorded the decision and its outcome.

```powershell
Get-Episodes -Outcome "failure" -MaxResults 20
```

### "What should I try?" → Multi-Tier

Complex questions requiring synthesis.

```text
1. Tier 1: Search for relevant patterns
2. Tier 2: Check if a similar situation occurred before, and how it ended
3. Synthesize recommendation
```

## Selection by Task Phase

| Task Phase | Primary Tier | Secondary Tier |
|------------|--------------|----------------|
| **Starting work** | 1 (context) | 2 (similar sessions) |
| **Encountering error** | 1 (solutions) | 2 (prior occurrences) |
| **Making decision** | 1 (constraints) | 2 (prior outcomes) |
| **Completing session** | 2 (extract) | 1 (record the fact) |
| **Debugging issue** | 2 (timeline) | 1 (known causes) |

## Fallback Strategy

```text
Primary tier unavailable?
│
├── Tier 1 (Forgetful part) unavailable
│   └── Use -LexicalOnly (Serena always works)
│
├── Tier 2 unavailable
│   └── Check .agents/memory/episodes/ exists
│   └── If missing, no historical data yet
```

## Common Mistakes

### Mistake: Using Tier 1 for session history

**Wrong**: `Search-Memory -Query "what did I do yesterday"`
**Right**: `Get-Episodes -Since (Get-Date).AddDays(-1)`

### Mistake: Using Tier 2 for fact lookup

**Wrong**: Scanning episodes for API documentation
**Right**: `Search-Memory -Query "API authentication"`

## Multi-Tier Query Example

When answering "How should I handle authentication errors?":

```bash
# Tier 1: Get documented patterns
facts=$(python3 .claude/skills/memory/scripts/search_memory.py --query "authentication error handling")

# Tier 2: Find relevant past sessions and how they ended
$episodes = Get-Episodes -Task "authentication" -MaxResults 10

# Synthesize answer from both tiers
```
