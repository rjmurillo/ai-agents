# Memory Skill Documentation Incoherence Report

**Date**: 2026-01-02
**Session**: S127 - Memory Skill Incoherence Detection
**Scope**: `.claude/skills/memory/references/*.md`, `.claude/skills/memory/scripts/`, `.claude/skills/memory/SKILL.md`

---

## Executive Summary

Analyzed 11 reference documents, 7 scripts, and the main SKILL.md for incoherence across four dimensions. Found **12 issues** (2 critical, 4 high, 4 medium, 2 low).

| Severity | Count | Main Categories |
|----------|-------|-----------------|
| Critical | 2 | Path inconsistencies, missing parameter documentation |
| High | 4 | Script path references, function signature mismatches |
| Medium | 4 | Cross-reference inconsistencies, stale paths |
| Low | 2 | Minor documentation gaps |

---

## Dimension A: Specification vs Behavior (Docs vs Code)

### Issue A1: Get-Episodes Missing `-Task` Parameter in API Reference

**Severity**: Critical

**Files**:
- `api-reference.md:180-192` - Documents Get-Episodes without `-Task` parameter
- `ReflexionMemory.psm1:298-403` - Implements `-Task` parameter (line 330)

**Description**: The API reference documents `Get-Episodes` with only `-Outcome`, `-Since`, and `-MaxResults` parameters, but the actual implementation includes a `-Task` filter parameter.

**In api-reference.md (lines 180-186)**:
```powershell
Get-Episodes
    [-Outcome <String>]
    [-Since <DateTime>]
    [-MaxResults <Int32>]
```

**In ReflexionMemory.psm1 (lines 326-336)**:
```powershell
param(
    [ValidateSet("success", "partial", "failure")]
    [string]$Outcome,

    [string]$Task,  # <-- Missing from docs

    [datetime]$Since,

    [ValidateRange(1, 100)]
    [int]$MaxResults = 20
)
```

**Suggested Fix**: Add `-Task` parameter to api-reference.md Get-Episodes documentation with description "Filter by task name (substring match, case-insensitive)".

---

### Issue A2: reflexion-memory.md Get-Episodes Example Uses Undocumented Parameter

**Severity**: High

**Files**:
- `reflexion-memory.md:287-289` - Uses `-Task` parameter in example
- `api-reference.md:180-192` - Missing `-Task` parameter

**Description**: The reflexion-memory.md shows example usage of `-Task` parameter that isn't documented in the API reference.

**In reflexion-memory.md (line 286-288)**:
```powershell
$episodes = Get-Episodes -Task "memory system" -MaxResults 20
```

**Suggested Fix**: Either document `-Task` in api-reference.md OR ensure consistency between example and parameter table (preferably document the parameter).

---

## Dimension C: Cross-Reference Consistency

### Issue C1: Script Path References Missing Full Path Prefix

**Severity**: High

**Files**:
- `reflexion-memory.md:646-650` - References `scripts/Extract-SessionEpisode.ps1`
- `reflexion-memory.md:692-696` - References `scripts/Update-CausalGraph.ps1`
- `benchmarking.md:7-8` - References `scripts/Measure-MemoryPerformance.ps1`

**Description**: Multiple documentation files reference scripts using relative `scripts/` path instead of the full `.claude/skills/memory/scripts/` path. This is inconsistent with the SKILL.md which uses full paths.

**In reflexion-memory.md (lines 646-650)**:
```powershell
pwsh scripts/Extract-SessionEpisode.ps1
    -SessionLogPath <String>
```

**In SKILL.md (lines 26-27)**:
```powershell
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 -SessionLogPath "..."
```

**Suggested Fix**: Update all script references in reflexion-memory.md and benchmarking.md to use full paths starting with `.claude/skills/memory/scripts/`.

---

### Issue C2: Inconsistent Storage Path References

**Severity**: High

**Files**:
- `reflexion-memory.md:17-18` - Documents `.agents/memory/episodes/` (extra space after path in diagram)
- `reflexion-memory.md:60` - Documents `.agents/memory/episodes/episode-{session-id}.json`
- `api-reference.md:232` - Documents `.agents/memory/episodes/episode-{SessionId}.json`

**Description**: Minor inconsistency in storage path documentation. Diagram at line 17 shows path with trailing space padding for visual alignment. Not a functional issue but could cause confusion.

**Suggested Fix**: Verify all storage path references are consistent and trimmed.

---

### Issue C3: Forgetful Health Script Path Inconsistency

**Severity**: Medium

**Files**:
- `troubleshooting.md:24` - References `scripts/forgetful/Test-ForgetfulHealth.ps1`
- `troubleshooting.md:85` - References same path

**Description**: Troubleshooting guide references `scripts/forgetful/Test-ForgetfulHealth.ps1` but this path is outside the memory skill scripts directory. It's located at the project root `scripts/forgetful/` level.

**Context**: This isn't wrong per se (it's a project-level script), but it's inconsistent with the memory skill focus. The memory skill has its own `Test-MemoryHealth.ps1` script.

**Suggested Fix**: Add clarification that this is a project-level script, not a memory skill script. Consider using `Test-MemoryHealth.ps1` for memory-specific health checks.

---

## Dimension D: Temporal Consistency (Stale References)

### Issue D1: Serena Memory Path Reference Without Dot Prefix

**Severity**: Medium

**Files**:
- `MemoryRouter.psm1:36` - Uses `.serena/memories` (correct)
- `memory-router.md:298-302` - Documents `.serena/memories` (correct)
- `troubleshooting.md:23` - References `.serena/memories` (correct)

**Note**: All Serena path references appear consistent. No stale references found.

### Issue D2: ADR References Without Full Paths

**Severity**: Low

**Files**:
- `api-reference.md:721-722` - References "ADR-037" and "ADR-038" without paths
- `reflexion-memory.md:7-9` - References ADRs without full paths
- `memory-router.md:6` - References "ADR-037" without path

**Description**: ADR references are consistent but don't include the full file path (`.agents/architecture/ADR-037-memory-router-architecture.md`). This could become stale if ADRs are reorganized.

**In MemoryRouter.psm1 (line 18)**:
```powershell
#    ADR: .agents/architecture/ADR-037-memory-router-architecture.md
```

**Suggested Fix**: Consider adding full ADR paths in at least one canonical location (API reference) for future-proofing.

---

## Dimension I: Completeness & Documentation Gaps

### Issue I1: Missing Health Check Script Documentation in API Reference

**Severity**: Critical

**Files**:
- `SKILL.md:152-169` - Documents `Test-MemoryHealth.ps1`
- `api-reference.md` - Does NOT document Test-MemoryHealth.ps1

**Description**: The main SKILL.md references `Test-MemoryHealth.ps1` as a key script ("Run first when diagnosing issues"), but it's completely absent from the API reference. The script exists at `.claude/skills/memory/scripts/Test-MemoryHealth.ps1`.

**Suggested Fix**: Add `Test-MemoryHealth.ps1` section to api-reference.md Scripts section with parameters, return types, and examples.

---

### Issue I2: MemoryRouter Private Functions Not Documented

**Severity**: Low

**Files**:
- `memory-router.md:241-290` - Documents internal functions briefly
- `MemoryRouter.psm1:46-263` - Implements 4 private functions

**Description**: The memory-router.md mentions internal functions (Invoke-SerenaSearch, Invoke-ForgetfulSearch, Merge-MemoryResults, Get-ContentHash) but with minimal detail. This is intentional (they're private) but could be expanded for maintainability.

**Private functions in MemoryRouter.psm1**:
1. `Get-ContentHash` (lines 46-74)
2. `Invoke-SerenaSearch` (lines 76-169)
3. `Invoke-ForgetfulSearch` (lines 171-263)
4. `Merge-MemoryResults` (lines 265-320)

**Suggested Fix**: No action required (private functions). Consider adding to a separate internal-reference.md if needed for maintainers.

---

### Issue I3: Get-DecisionSequence Not Mentioned in SKILL.md

**Severity**: Medium

**Files**:
- `api-reference.md:246-270` - Documents Get-DecisionSequence
- `ReflexionMemory.psm1:503-533` - Implements Get-DecisionSequence
- `SKILL.md` - Does NOT mention Get-DecisionSequence

**Description**: The SKILL.md Quick Reference table and triggers list don't mention `Get-DecisionSequence` even though it's a useful function for agents reviewing decision history.

**Suggested Fix**: Add to SKILL.md Quick Reference table with appropriate trigger phrase.

---

### Issue I4: Benchmarking Script Path Uses Inconsistent Formats

**Severity**: Medium

**Files**:
- `benchmarking.md:17-18` - Uses `scripts/Measure-MemoryPerformance.ps1`
- `benchmarking.md:413-414` - Uses `.claude/skills/memory/scripts/Measure-MemoryPerformance.ps1`
- `SKILL.md:310-311` - Uses `.claude/skills/memory/scripts/Measure-MemoryPerformance.ps1`

**Description**: The benchmarking.md document uses inconsistent path formats - short form in Quick Start section but full form in Advanced Usage section.

**In benchmarking.md (lines 17-18)**:
```bash
pwsh scripts/Measure-MemoryPerformance.ps1
```

**In benchmarking.md (lines 413-414)**:
```bash
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1 -Format json > baseline.json
```

**Suggested Fix**: Standardize all paths in benchmarking.md to use full `.claude/skills/memory/scripts/` prefix.

---

## Summary Table

| ID | Dimension | Severity | File | Line(s) | Issue |
|----|-----------|----------|------|---------|-------|
| A1 | Spec vs Behavior | Critical | api-reference.md | 180-192 | Get-Episodes missing -Task parameter |
| A2 | Spec vs Behavior | High | reflexion-memory.md | 287 | Example uses undocumented -Task |
| C1 | Cross-Reference | High | reflexion-memory.md | 646, 692 | Script paths missing full prefix |
| C2 | Cross-Reference | High | Multiple | - | Minor path formatting inconsistency |
| C3 | Cross-Reference | Medium | troubleshooting.md | 24, 85 | External script path reference |
| D2 | Temporal | Low | Multiple | - | ADR references lack full paths |
| I1 | Gaps | Critical | api-reference.md | - | Test-MemoryHealth.ps1 undocumented |
| I2 | Gaps | Low | memory-router.md | 241-290 | Private functions minimal docs |
| I3 | Gaps | Medium | SKILL.md | - | Get-DecisionSequence not mentioned |
| I4 | Gaps | Medium | benchmarking.md | 17, 413 | Inconsistent script path formats |

---

## Recommended Priority

1. **Fix Critical Issues First** (I1, A1): Add missing API documentation for Test-MemoryHealth.ps1 and the -Task parameter
2. **Address High Issues** (A2, C1, C2): Standardize script paths across all docs
3. **Resolve Medium Issues** (C3, I3, I4): Add clarifications and missing quick reference entries
4. **Optional Low Issues** (D2, I2): Consider full ADR paths and expanded internal docs

---

## Verification Commands

```powershell
# Verify Get-Episodes has -Task parameter
Get-Help Get-Episodes -Parameter Task

# Verify Test-MemoryHealth.ps1 exists
Test-Path ".claude/skills/memory/scripts/Test-MemoryHealth.ps1"

# Search for inconsistent script paths
Get-ChildItem ".claude/skills/memory/references/*.md" | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match 'pwsh scripts/[^.]') {
        Write-Host "$($_.Name): Uses short path 'scripts/...'"
    }
}
```

---

**Report Generated By**: Claude Session S127
**Analysis Method**: Four-dimension incoherence detection (A, C, D, I)
