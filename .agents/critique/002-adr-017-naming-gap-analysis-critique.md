# Plan Critique: ADR-017 Naming Enforcement Gap Analysis

## Verdict

**NEEDS REVISION**

## Summary

Gap analysis correctly identifies 3 real validation gaps in ADR-017 enforcement. Gap 1 and Gap 4 are genuine issues requiring fixes. Gap 2 is theoretical but prevented by workflow design. Gap 3 is NOT a gap—ADR-017 intentionally does not enforce index file format beyond `| Keywords | File |` table structure.

## Strengths

- Identified specific code locations (line numbers) for each gap
- Distinguished between file content validation vs file reference validation
- Recognized cross-validation deficiency between two scripts
- Provided concrete scenario demonstrating Gap 2

## Issues Found

### Critical (Must Fix)

- [ ] **Gap 3 mischaracterization** at "Gap 3: Index file format validation missing": ADR-017 does NOT require index files be "Pure lookup table" with no title/metadata as a VALIDATION REQUIREMENT. Line 254 states "No title, no metadata. Pure lookup table." in IMPLEMENTATION section as a DESIGN PRINCIPLE. The Confirmation section (lines 200-205) lists 3 validation checks:
  1. Pre-commit hook validates new skill files are indexed
  2. CI workflow checks index ↔ file consistency
  3. Keyword density check (≥40% unique keywords)

  None of these enforce metadata prohibition. `Get-IndexEntries` (Validate-MemoryIndex.ps1 lines 98-145) parses `| Keywords | File |` table structure via regex at line 117-124. Metadata above the table is skipped; metadata within the table breaks parsing and triggers validation error. Format validation EXISTS via table parsing.

### Important (Should Fix)

- [ ] **Missing impact assessment**: No analysis of whether these gaps have caused actual failures in production or are only theoretical risks discovered via code review. Without evidence of real-world impact, prioritization is arbitrary.

- [ ] **No prioritization rationale**: Question "Which gaps are highest priority?" asks critic to assess, but provides no criteria (e.g., likelihood of occurrence, blast radius, current mitigation controls).

- [ ] **Gap 2 scenario incomplete**: Scenario states "Only the index file is staged (not the renamed file)" but analysis misses that CI workflow runs `Validate-MemoryIndex.ps1` on ALL files (line 126 of memory-validation.yml, no file filtering). However, `Validate-MemoryIndex.ps1` does NOT check filenames for `skill-` prefix—it only checks:
  - File existence (Test-FileReferences)
  - Keyword density (Test-KeywordDensity)
  - Orphan detection (Get-OrphanedFiles, which has the Gap 4 issue)

  Gap 2 is REAL but not for the stated reason.

### Minor (Consider)

- [ ] **Pre-commit hook assumption**: Analysis states "Pre-commit hook runs both during commits" but project has no `.git/hooks/pre-commit` or Husky configuration. Actual enforcement is CI workflow only (memory-validation.yml). This doesn't invalidate gaps but misrepresents enforcement mechanism.

- [ ] **Orphan detection pattern verification**: Gap 4 states `skill-pr-001.md` "wouldn't match `^pr-` pattern" but doesn't verify whether lines 282-283 exclusions (`-index$`, `memory-index`) would also skip it.

## Questions for Planner

1. Have any of these gaps caused actual validation failures in production, or are they theoretical risks discovered via code review?
2. For Gap 2: Why does the scenario stage "only the index file" without the renamed file? What Git operation produces this state? (Answer: `git add` on index after renaming file but before staging rename)
3. For Gap 4: If `skill-pr-001.md` exists, does `Get-OrphanedFiles` report it as unmatched (not an orphan), or silently ignore it? (Answer: Silently ignores—doesn't match domain pattern, not in exclusion list)

## Recommendations

### Gap 1: Index entries reference skill- prefixed files (CONFIRMED - P1)

**Issue**: Index file entries can reference `skill-` prefixed filenames without detection.

**Evidence**:
- `Validate-SkillFormat.ps1` excludes index files at lines 55, 68 (correct exclusion—index files are not skill content)
- `Validate-MemoryIndex.ps1` `Test-FileReferences` (lines 146-176) only checks file existence, not naming convention:
  ```powershell
  if (Test-Path $filePath) {
      $result.ValidFiles += $entry.FileName
  } else {
      $result.MissingFiles += $entry.FileName
  }
  ```

**Fix Strategy**: Add naming validation to `Test-FileReferences`:

```powershell
# After line 167 (Test-Path check passes)
if ($entry.FileName -match '^skill-') {
    $result.Passed = $false
    $result.Issues += "Index references deprecated 'skill-' prefix: $($entry.FileName).md (ADR-017 violation)"
}
```

**Test Case**:
```powershell
# In Validate-MemoryIndex.Tests.ps1
It 'Fails when index entry references skill- prefixed file' {
    $indexContent = @'
| Keywords | File |
|----------|------|
| test keywords | skill-pr-001 |
'@
    Set-Content $indexPath $indexContent
    $result = Invoke-MemoryIndexValidation -Path $memPath
    $result.Passed | Should -Be $false
    $result.Issues | Should -Contain "*skill-* prefix*"
}
```

**Priority**: P1 (High) - Direct violation of ADR-017 naming requirement. No existing mitigation.

### Gap 2: Cross-validation between skill-format and memory-index (CONFIRMED - P1)

**Issue**: Scenario where file renamed to `skill-` prefix and index updated, but validation passes.

**Real-World Scenario**:
1. Developer renames `pr-001.md` → `skill-pr-001.md` in filesystem
2. Developer updates index to reference `skill-pr-001`
3. Developer stages index file only: `git add .serena/memories/skills-pr-index.md`
4. Commit triggers validation:
   - `Validate-SkillFormat.ps1 -StagedOnly`: Excludes index files (line 68), checks only `skill-pr-001.md` if staged (but it's NOT staged) → PASS
   - `Validate-MemoryIndex.ps1`: Checks index references `skill-pr-001.md`, file exists → PASS (doesn't validate naming)
5. Result: Index points to `skill-` prefixed file, undetected

**Why It Occurs**: Validation scripts run independently. `Validate-SkillFormat.ps1` checks staged files. `Validate-MemoryIndex.ps1` checks all repository files but doesn't validate naming convention.

**Fix Strategy**: Same as Gap 1—add naming validation to `Test-FileReferences`. This fixes both gaps.

**Priority**: P1 (High) - Can occur during refactoring/renames. Shares fix with Gap 1.

### Gap 3: Index file format validation (NOT A GAP - Reject)

**Issue**: Analysis claims "ADR-017 requires index files be 'Pure lookup table' with no title/metadata" and "No validation enforces this format requirement."

**Counterevidence**:
- ADR-017 line 254: "No title, no metadata. Pure lookup table." appears in IMPLEMENTATION section as DESIGN PRINCIPLE, not validation requirement
- ADR-017 lines 200-205 (Confirmation section) lists 3 validation checks:
  1. Pre-commit hook validates new skill files are indexed
  2. CI workflow checks index ↔ file consistency
  3. Keyword density check (≥40% unique keywords)

  None mention metadata prohibition.

- ADR-017 line 248-252 shows required format: `| Keywords | File |` table structure (NOT "no titles")

**Actual Validation**: `Get-IndexEntries` (lines 98-145 in `Validate-MemoryIndex.ps1`) parses table structure:
```powershell
# Line 117-124: Regex matches "| keywords | filename |" pattern
$pattern = '\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
```

If index has titles/metadata ABOVE the table, `Get-IndexEntries` skips them (line 106-115 skips until table header found). If metadata is WITHIN the table (malformed rows), parsing fails and validation reports error.

**Conclusion**: Format validation EXISTS via table parsing. Metadata prohibition is a STYLE GUIDELINE for token efficiency (ADR-017 principle: "Zero Retrieval-Value Content Elimination"), not a functional requirement.

**Priority**: N/A (not a gap)

### Gap 4: Orphaned file detection doesn't catch prefix violations (CONFIRMED - P0)

**Issue**: `Get-OrphanedFiles` matches domain prefix pattern `^pr-`, so `skill-pr-001.md` doesn't match and isn't flagged as orphaned.

**Evidence**:
- Line 289: `if ($baseName -match "^$domain-" -and -not $referencedFiles.ContainsKey($baseName))`
- `skill-pr-001` does NOT match `^pr-` pattern, so loop continues without adding to orphans
- Line 277-283 exclusions (`-index$`, `memory-index`) don't apply to `skill-pr-001`

**Consequence**: File with `skill-` prefix sits in repository, never detected by:
- `Validate-SkillFormat.ps1` (not staged or in changed files)
- `Validate-MemoryIndex.ps1` orphan detection (doesn't match domain pattern)
- `Validate-MemoryIndex.ps1` reference check (file not in any index)

**Silent Failure Mode**: Developer renames file, forgets to update index, `skill-` file remains in repo indefinitely.

**Fix Strategy**: Add dedicated `skill-` prefix detection in `Get-OrphanedFiles`:

```powershell
# After line 285 (skip memory-index check), before domain pattern loop

# Check for deprecated skill- prefix (ADR-017 violation)
if ($baseName -match '^skill-') {
    [void]$orphans.Add([PSCustomObject]@{
        File = $baseName
        Domain = 'INVALID'
        ExpectedIndex = 'N/A - Rename to {domain}-{description} format per ADR-017'
    })
    continue  # Skip domain pattern matching
}
```

**Test Case**:
```powershell
It 'Detects skill- prefixed files as orphans with INVALID domain' {
    # Create skill- prefixed file NOT in any index
    New-Item "$memPath/skill-pr-001.md" -ItemType File
    $orphans = Get-OrphanedFiles -AllIndices $indices -MemoryPath $memPath
    $orphans | Should -HaveCount 1
    $orphans[0].File | Should -Be 'skill-pr-001'
    $orphans[0].Domain | Should -Be 'INVALID'
    $orphans[0].ExpectedIndex | Should -Match 'ADR-017'
}
```

**Priority**: P0 (Critical) - Silent failure mode. No detection mechanism for existing files. Undermines ADR-017 migration.

## Approval Conditions

1. **Revise Gap 3** to reflect that format validation exists via table parsing, metadata prohibition is style guideline (not validation requirement)
2. **Add impact assessment**: Have any of these gaps caused real failures in production? Search codebase for `skill-*.md` files to determine if Gap 4 already exists.
3. **Consolidate Gap 1 and Gap 2**: Both fixed by adding filename validation to `Test-FileReferences`
4. **Provide test plan**: Add test cases for Gap 1/2 fix and Gap 4 fix
5. **Correct enforcement mechanism**: Replace "pre-commit hook" references with "CI workflow (memory-validation.yml)"

## Impact Analysis Review

**Consultation Coverage**: N/A (gap analysis, not architectural decision)

**Cross-Domain Conflicts**: None

**Escalation Required**: No

### Specialist Agreement Status

| Specialist | Agrees with Plan | Concerns |
|------------|-----------------|----------|
| N/A | N/A | Single-author analysis |

**Unanimous Agreement**: N/A

## Recommendations Priority Matrix

| Gap | Priority | Effort | Risk if Ignored | Fix Complexity |
|-----|----------|--------|-----------------|----------------|
| Gap 1 | P1 | Low | High - Index drift | 5 lines (add naming check to Test-FileReferences) |
| Gap 2 | P1 | Low | High - Rename bypass | Same fix as Gap 1 |
| Gap 3 | N/A | N/A | None - Not a gap | N/A |
| Gap 4 | P0 | Low | Critical - Silent failure | 10 lines (add skill- detection to Get-OrphanedFiles) |

**Combined Fix**: Gap 1 + Gap 2 = single function modification (Test-FileReferences)

## Next Steps

Plan needs revision. Recommend orchestrator routes to planner with these issues:

1. **Merge Gap 1 and Gap 2 fixes** (same root cause: filename validation missing from `Test-FileReferences`)
2. **Provide implementation plan for Gap 4 fix** (add `skill-` prefix detection to `Get-OrphanedFiles`)
3. **Remove Gap 3 from analysis** (not a gap—table parsing provides format validation)
4. **Add test plan** for each fix with specific test cases
5. **Search codebase** for existing `skill-*.md` files to assess Gap 4 impact (use `find .serena/memories -name 'skill-*.md'`)

## Handoff Protocol

As subagent, I CANNOT delegate to planner. Returning critique to orchestrator with recommendation:

**NEEDS REVISION**: Route to planner to create implementation plan addressing:
- Combined Gap 1/2 fix (Test-FileReferences naming validation)
- Gap 4 fix (Get-OrphanedFiles skill- prefix detection)
- Test plan with coverage for both fixes
- Impact assessment (search for existing violations)
