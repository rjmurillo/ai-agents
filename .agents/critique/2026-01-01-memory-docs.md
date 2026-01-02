# Memory System Documentation Incoherence Report

**Date**: 2026-01-01
**Scope**: docs/memory-system/ vs .claude/skills/memory/
**Dimensions**: A (Spec vs Behavior), C (Cross-Reference Consistency), I (Documentation Gaps)

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 3 |
| Medium | 3 |
| Low | 2 |

---

## Issues

### Issue I1: Script Path References Incorrect in quick-start.md

**Type**: Contradiction
**Severity**: critical

#### Source A: quick-start.md (lines 12-15, 35-36, 106-107)

```markdown
Import-Module scripts/MemoryRouter.psm1
Import-Module scripts/ReflexionMemory.psm1
```

#### Source B: Actual Implementation (.claude/skills/memory/scripts/)

Scripts are located at `.claude/skills/memory/scripts/`, not `scripts/`.

#### Suggestions

1. Update all `scripts/` references to `.claude/skills/memory/scripts/`
2. Add a note about the skill directory structure

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Update all script import paths to use the correct skill location: `.claude/skills/memory/scripts/`

<!-- /Resolution -->

---

### Issue I2: Episode Storage Path Inconsistent

**Type**: Contradiction
**Severity**: critical

#### Source A: quick-start.md (lines 231, 286)

```markdown
.agents/episodes/
.agents/causality/
```

#### Source B: SKILL.md and Extract-SessionEpisode.ps1

```markdown
.agents/memory/episodes/
.agents/memory/causality/
```

#### Suggestions

1. Standardize on `.agents/memory/episodes/` and `.agents/memory/causality/`
2. Update quick-start.md to use correct paths

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Standardize on `.agents/memory/episodes/` and `.agents/memory/causality/` - update quick-start.md

<!-- /Resolution -->

---

### Issue I3: Diagnostic Output Structure Mismatch

**Type**: Contradiction
**Severity**: high

#### Source A: skill-reference.md (lines 153-175)

```json
{
  "Diagnostic": {
    "SerenaAvailable": true,
    "ForgetfulAvailable": true,
    "SerenaPath": "/path/to/.serena/memories",
    "SerenaMemoryCount": 460,
    "ForgetfulUrl": "http://localhost:8020"
  }
}
```

#### Source B: Actual Get-MemoryRouterStatus Output

```json
{
  "Serena": {
    "Available": true,
    "Path": ".serena/memories"
  },
  "Forgetful": {
    "Available": true,
    "Endpoint": "http://localhost:8020/mcp"
  },
  "Cache": {...},
  "Configuration": {...}
}
```

#### Suggestions

1. Update skill-reference.md to show actual nested structure
2. Document the Cache and Configuration properties

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Update skill-reference.md to reflect actual Get-MemoryRouterStatus output structure

<!-- /Resolution -->

---

### Issue I4: Test-MemoryHealth.ps1 Not Documented

**Type**: Gap
**Severity**: high

#### Source A: SKILL.md (lines 152-169)

Documents Test-MemoryHealth.ps1 with full usage examples.

#### Source B: api-reference.md and skill-reference.md

Neither file documents Test-MemoryHealth.ps1.

#### Suggestions

1. Add Test-MemoryHealth.ps1 section to api-reference.md
2. Add Test-MemoryHealth.ps1 section to skill-reference.md

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Add documentation for Test-MemoryHealth.ps1 to both api-reference.md and skill-reference.md

<!-- /Resolution -->

---

### Issue I5: Future Skills Already Implemented

**Type**: Ambiguity
**Severity**: high

#### Source A: skill-reference.md (lines 371-385)

```markdown
## Future Skills

The following skills are planned for future releases:

### Save-Memory.ps1 (Planned)
### Query-Episodes.ps1 (Planned)
### Trace-Causality.ps1 (Planned)
```

#### Source B: ReflexionMemory.psm1

- `Get-Episode` and `Get-Episodes` exist (Query-Episodes functionality)
- `Get-CausalPath` exists (Trace-Causality functionality)

#### Suggestions

1. Remove Query-Episodes.ps1 and Trace-Causality.ps1 from "Future" section
2. Document that this functionality exists in ReflexionMemory.psm1
3. Keep Save-Memory.ps1 as "Planned" if not yet implemented

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Remove implemented features from "Future Skills" section, document them as available in ReflexionMemory.psm1

<!-- /Resolution -->

---

### Issue I6: API Reference Module Path

**Type**: Contradiction
**Severity**: medium

#### Source A: api-reference.md (lines 9-10)

```markdown
| [MemoryRouter](#memoryrouter-module) | Unified memory search (Tier 1) | scripts/MemoryRouter.psm1 |
| [ReflexionMemory](#reflexionmemory-module) | Episodes and causality (Tiers 2 & 3) | scripts/ReflexionMemory.psm1 |
```

#### Source B: Actual Location

Modules are at `.claude/skills/memory/scripts/`, not `scripts/`.

#### Suggestions

1. Update module location column to use relative path from skill directory
2. Or update to use absolute path `.claude/skills/memory/scripts/`

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Update to use the full skill path: `.claude/skills/memory/scripts/`

<!-- /Resolution -->

---

### Issue I7: Script Invocation Paths in api-reference.md

**Type**: Contradiction
**Severity**: medium

#### Source A: api-reference.md (lines 567-568, 602-603)

```powershell
pwsh scripts/Extract-SessionEpisode.ps1
pwsh scripts/Update-CausalGraph.ps1
```

#### Source B: SKILL.md (correct examples)

```powershell
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1
pwsh .claude/skills/memory/scripts/Update-CausalGraph.ps1
```

#### Suggestions

1. Update api-reference.md to use full skill paths

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Update all script invocation examples to use `.claude/skills/memory/scripts/` path

<!-- /Resolution -->

---

### Issue I8: Status Check Commands Use Old Paths

**Type**: Contradiction
**Severity**: medium

#### Source A: quick-start.md (lines 83-86)

```bash
pwsh -c "Import-Module scripts/MemoryRouter.psm1; Get-MemoryRouterStatus | ConvertTo-Json"
pwsh -c "Import-Module scripts/ReflexionMemory.psm1; Get-ReflexionMemoryStatus | ConvertTo-Json"
```

#### Source B: Actual module locations

Modules are at `.claude/skills/memory/scripts/`

#### Suggestions

1. Update to use full skill paths
2. Consider recommending Test-MemoryHealth.ps1 instead for status checks

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Update to full skill paths; also recommend Test-MemoryHealth.ps1 as the primary status check tool

<!-- /Resolution -->

---

### Issue I9: Missing Measure-MemoryPerformance.ps1 Documentation

**Type**: Gap
**Severity**: low

#### Source A: SKILL.md (lines 305-328)

Documents Measure-MemoryPerformance.ps1 with parameters and examples.

#### Source B: api-reference.md

Does not document this script.

#### Suggestions

1. Add section for Measure-MemoryPerformance.ps1 to api-reference.md

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Add Measure-MemoryPerformance.ps1 documentation to api-reference.md

<!-- /Resolution -->

---

### Issue I10: Skill Reference Missing Complete Script Inventory

**Type**: Gap
**Severity**: low

#### Source A: skill-reference.md

Only documents Search-Memory.ps1.

#### Source B: SKILL.md Scripts Reference

Documents:
- Test-MemoryHealth.ps1
- Search-Memory.ps1
- Extract-SessionEpisode.ps1
- Update-CausalGraph.ps1
- ReflexionMemory.psm1 functions
- Measure-MemoryPerformance.ps1

#### Suggestions

1. Add summary section listing all available scripts
2. Point to SKILL.md for detailed script documentation
3. Consider skill-reference.md as the "skill wrapper" documentation, not full API

#### Resolution

<!-- USER: Write your decision below. Be specific. -->

Add a summary section listing all scripts with links to SKILL.md for details

<!-- /Resolution -->

---

## Reconciliation Status

| Issue | Status |
|-------|--------|
| I1 | RESOLVED - Updated all `scripts/` refs to `.claude/skills/memory/scripts/` in quick-start.md |
| I2 | RESOLVED - Standardized on `.agents/memory/episodes/` and `.agents/memory/causality/` |
| I3 | RESOLVED - Updated diagnostic output structure in skill-reference.md |
| I4 | PARTIAL - Added summary table linking to SKILL.md; full API docs would be redundant |
| I5 | RESOLVED - Removed implemented features from "Future Skills", added "Additional Scripts" section |
| I6 | RESOLVED - Updated module paths in api-reference.md |
| I7 | RESOLVED - Updated script invocation paths in api-reference.md |
| I8 | RESOLVED - Updated status check commands and added Test-MemoryHealth recommendation |
| I9 | PARTIAL - Referenced via skill-reference.md link to SKILL.md |
| I10 | RESOLVED - Added summary section with script inventory and links |

**Reconciliation completed**: 2026-01-01
