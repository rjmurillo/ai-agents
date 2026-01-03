# Tier Selection Guide

Deep guidance for selecting the correct memory tier.

## Tier Characteristics

| Tier | Access Speed | Scope | Reliability | Content Type |
|------|--------------|-------|-------------|--------------|
| **0: Working** | Instant | Current session | 100% | Active context |
| **1: Semantic** | ~500ms | All projects | 100% (Serena) | Facts, patterns, rules |
| **2: Episodic** | ~100ms | This project | 100% (local) | Session history, decisions |
| **3: Causal** | ~100ms | This project | 100% (local) | Relationships, patterns |

## Selection by Question Type

### "What is X?" → Tier 1

Factual questions about concepts, patterns, or rules.

```powershell
Search-Memory.ps1 -Query "PowerShell array handling"
```

### "What happened when...?" → Tier 2

Historical questions about past sessions.

```powershell
Get-Episode -SessionId "2026-01-01-session-126"
Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)
```

### "Why did X lead to Y?" → Tier 3

Causal questions about relationships.

```powershell
Get-CausalPath -FromLabel "decision: retry logic" -ToLabel "outcome: success"
```

### "What usually works?" → Tier 3

Pattern questions about success/failure rates.

```powershell
Get-Patterns -MinSuccessRate 0.7
```

### "What should I try?" → Multi-Tier

Complex questions requiring synthesis.

```text
1. Tier 1: Search for relevant patterns
2. Tier 2: Check if similar situation occurred before
3. Tier 3: Find what worked in similar situations
4. Synthesize recommendation
```

## Selection by Task Phase

| Task Phase | Primary Tier | Secondary Tier |
|------------|--------------|----------------|
| **Starting work** | 1 (context) | 2 (similar sessions) |
| **Encountering error** | 1 (solutions) | 3 (error patterns) |
| **Making decision** | 3 (patterns) | 1 (constraints) |
| **Completing session** | 2 (extract) | 3 (update) |
| **Debugging issue** | 2 (timeline) | 3 (causation) |

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
│
└── Tier 3 unavailable
    └── Check .agents/memory/causality/ exists
    └── If missing, no causal data yet
```

## Common Mistakes

### Mistake: Using Tier 1 for session history

**Wrong**: `Search-Memory -Query "what did I do yesterday"`
**Right**: `Get-Episodes -Since (Get-Date).AddDays(-1)`

### Mistake: Using Tier 2 for pattern discovery

**Wrong**: Scanning through multiple episodes manually
**Right**: `Get-Patterns -MinSuccessRate 0.7`

### Mistake: Using Tier 3 for fact lookup

**Wrong**: Searching causal graph for API documentation
**Right**: `Search-Memory -Query "API authentication"`

## Multi-Tier Query Example

When answering "How should I handle authentication errors?":

```powershell
# Tier 1: Get documented patterns
$facts = Search-Memory.ps1 -Query "authentication error handling"

# Tier 2: Find relevant past sessions
$episodes = Get-Episodes -Task "authentication" -MaxResults 10

# Tier 3: Check what worked
$patterns = Get-Patterns | Where-Object { $_.name -match "auth" }

# Synthesize answer from all three tiers
```
