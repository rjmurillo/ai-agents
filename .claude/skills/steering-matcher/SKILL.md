---
name: steering-matcher
description: Match file paths against steering file glob patterns to determine applicable steering guidance. Use when orchestrator needs to inject context-aware guidance based on files being modified.
license: MIT
metadata:
version: 1.0.0
model: claude-haiku-4-5
---

# Steering File Matcher Skill

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `match steering for these files` | Get-ApplicableSteering.ps1 |
| `which steering applies to this task` | Pattern match against changed files |
| `inject steering context` | Return applicable steering sorted by priority |

## Purpose

This skill helps orchestrator determine which steering files to inject into agent context based on the files being modified.

- Match file paths against glob patterns in steering file front matter
- Return applicable steering files sorted by priority
- Enable token-efficient context injection (30%+ savings)

## When to Use

Use this skill when:

- Orchestrator needs to inject context-aware steering based on files being modified
- You want to scope agent guidance to only relevant files (token optimization)
- Matching file paths against `applyTo` glob patterns in steering front matter

Use manual file reading instead when:

- You already know which steering file applies
- The task affects a single known steering domain

## Quick Usage

### Using Get-ApplicableSteering.ps1 Script

The script in `.claude/skills/steering-matcher/Get-ApplicableSteering.ps1` handles pattern matching.

```powershell
# Match files against steering patterns
$files = @(
    "src/claude/analyst.md",
    ".agents/security/TM-001-auth-flow.md"
)

$steering = pwsh .claude/skills/steering-matcher/Get-ApplicableSteering.ps1 `
    -Files $files `
    -SteeringPath ".agents/steering"

# Output: Array of hashtables with Name, Path, ApplyTo, Priority
foreach ($s in $steering) {
    Write-Host "Matched: $($s.Name) (Priority: $($s.Priority))"
}
```

## Process

This skill integrates with the orchestrator workflow:

1. **Task Analysis**: Orchestrator identifies files affected by task
2. **Pattern Matching**: Use this skill to find applicable steering
3. **Context Injection**: Include matched steering in agent prompt
4. **Token Optimization**: Only inject relevant guidance

### Standard Orchestrator Workflow

```powershell
# 1. Identify files from task
$filesAffected = @(
    "src/claude/security.md",
    ".agents/security/SR-001-oauth-review.md"
)

# 2. Get applicable steering
$applicableSteering = pwsh .claude/skills/steering-matcher/Get-ApplicableSteering.ps1 `
    -Files $filesAffected

# 3. Inject into agent context
# "Relevant steering: agent-prompts.md (Priority 9), security-practices.md (Priority 10)"
```

## Implementation

See `Get-ApplicableSteering.ps1` for the PowerShell implementation.

## Testing

Run Pester tests to verify pattern matching:

```powershell
Invoke-Pester .claude/skills/steering-matcher/tests/Get-ApplicableSteering.Tests.ps1
```

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Hardcoding steering file paths | Bypasses pattern matching, breaks on restructuring | Use Get-ApplicableSteering.ps1 |
| Injecting all steering files | Token bloat, irrelevant context | Match against changed files only |
| Ignoring priority ordering | Lower-priority guidance may contradict higher | Process results in priority order |

## Verification

After execution:

- [ ] Returned steering files match the `applyTo` patterns for the given files
- [ ] Results are sorted by priority (highest first)
- [ ] No duplicate steering entries in output

## Related

- [Steering System README](../../../.agents/steering/README.md)
- [Enhancement Project Plan](../../../.agents/planning/enhancement-PROJECT-PLAN.md)
- [Orchestrator Agent](../../../src/claude/orchestrator.md)
