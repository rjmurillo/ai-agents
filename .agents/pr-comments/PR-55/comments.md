# PR Comment Map: PR #55

**Generated**: 2025-12-18 03:30:00
**PR**: docs(phase-0): establish spec layer, steering system foundation, and workflow patterns
**Branch**: copilot/setup-foundational-structure → main
**Total Comments**: 41
**Reviewers**: Copilot, rjmurillo, cursor[bot]

## Summary

- **Total**: 41 comments
- **Top-level**: 21
- **Replies**: 20
- **Resolved**: 19 (Copilot addressed with commits)
- **Unresolved**: 2 (cursor[bot] bugs awaiting fix)

## Unresolved Comments

### Comment 2629405501 (cursor[bot]) - BUG: Wildcard detection

**File**: `build/scripts/Invoke-PesterTests.ps1:111`
**Status**: 👀 Acknowledged
**Priority**: Low Severity
**Type**: Bug Report

**Issue**:
The condition `$fullPath -like "*?*"` incorrectly detects wildcard paths. In PowerShell's `-like` operator, `?` matches any single character, so this pattern matches virtually any non-empty string. This causes all paths to be treated as containing wildcards. The correct pattern to match a literal question mark is `*[?]*`.

**Impact**:
Low - `Get-Item` handles both wildcard and non-wildcard paths, but logic incorrectly routes all paths through wildcard expansion branch.

**Fix Required**:
Update line 111 from `$fullPath -like "*?*"` to `$fullPath -like "*[?]*"` or use a different wildcard detection strategy.

---

### Comment 2629405503 (cursor[bot]) - BUG: Exclude field ignored

**File**: `.agents/steering/documentation.md:4`
**Status**: 👀 Acknowledged
**Priority**: Medium Severity
**Type**: Bug Report

**Issue**:
The `documentation.md` steering file defines an `exclude` field to exclude `src/claude/**/*.md` and `.agents/steering/**` from matching. However, `Get-ApplicableSteering.ps1` only parses `applyTo` and `priority` fields from YAML front matter and has no logic to handle exclusions.

**Impact**:
Medium - Documentation steering will incorrectly match agent prompt files and steering files themselves, defeating the intended scoping.

**Locations**:
- `.agents/steering/documentation.md:3-4` - defines `exclude` field
- `.claude/skills/steering-matcher/Get-ApplicableSteering.ps1:53-55` - front matter parsing (missing exclude logic)

**Fix Required**:
1. Update `Get-ApplicableSteering.ps1` to parse `exclude` field from YAML front matter
2. Add exclusion logic after pattern matching to filter out excluded paths
3. Add Pester tests for exclusion behavior

---

## Resolved Comments (by Copilot)

All other comments (39/41) have been addressed by Copilot through commits:
- 46f6822: Claude skill, GitHub instructions, unified steering
- 1c5f49b: Pester tests, glob fixes, front matter updates, security/testing updates
- fda74d0: AGENT-SYSTEM.md workflow patterns updated
- 444f5aa: PowerShell patterns, test runner enhancements, security/testing glob fixes
- 395f685: Wildcard `?` bug fix in steering-matcher

## Comment Index

| ID | Author | Type | Path/Line | Status | Priority |
|----|--------|------|-----------|--------|----------|
| 2629405501 | cursor[bot] | review | build/scripts/Invoke-PesterTests.ps1#111 | pending | Low |
| 2629405503 | cursor[bot] | review | .agents/steering/documentation.md#4 | pending | Medium |
| (39 others) | Copilot | review | various | resolved | - |

