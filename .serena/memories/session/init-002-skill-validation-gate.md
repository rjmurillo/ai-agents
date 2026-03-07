# Init: Skill Validation Gate

## Skill-Init-002: Skill Validation Gate

**Statement**: Before ANY GitHub operation, check `.claude/skills/github/` directory for existing capability

**Context**: Before writing code calling `gh` CLI or GitHub API, verify `.claude/skills/github/scripts/` contains needed functionality. If exists: use skill. If missing: extend skill (don't write inline).

**Evidence**: Session 15 - 3+ raw `gh` command violations in 10 minutes despite skill availability

**Atomicity**: 95%

**Tag**: CRITICAL

**Impact**: 10/10 - Prevents duplicate implementations and token waste

**Implementation**:

1. Create `Check-SkillExists.ps1` tool:
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

2. Add Phase 1.5 to SESSION-PROTOCOL.md (BLOCKING):
   - MUST run `Check-SkillExists.ps1` before GitHub operations
   - MUST provide tool output as verification
   - If skill exists: use it
   - If skill missing: extend skill, then use

**Verification**: Tool output showing check performed (not agent promise)

---