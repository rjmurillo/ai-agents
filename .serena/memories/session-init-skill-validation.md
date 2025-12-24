# Skill-Init-002: Skill Validation Gate

**Statement**: Before ANY GitHub operation, check `.claude/skills/github/` directory for existing capability.

**Context**: Before writing code calling `gh` CLI or GitHub API.

**Evidence**: Session 15 - 3+ raw `gh` command violations in 10 minutes despite skill availability.

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Prevents duplicate implementations and token waste

## Decision Flow

1. If skill exists → USE skill
2. If skill missing → EXTEND skill (don't write inline)

## Implementation Pattern

```powershell
param(
    [ValidateSet('pr','issue','reaction','label','milestone')]
    [string]$Operation,

    [ValidateSet('create','comment','view','edit','label','close')]
    [string]$Action
)

$skillPath = ".claude/skills/github/scripts/$Operation/*$Action*.ps1"
Test-Path $skillPath
```

## Verification

Tool output showing check performed (not agent promise)
