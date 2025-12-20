## Context

From Session 36 retrospective:

**Root Cause**: PowerShell scripts with syntax errors can be committed and pushed without detection, causing CI failures or runtime errors.

**Gap**: No CI pipeline validation step to catch PowerShell syntax errors before merge.

## Objective

Add PowerShell syntax validation to CI pipeline to prevent scripts with syntax errors from being merged.

## Acceptance Criteria

- [ ] CI workflow validates all .ps1 and .psm1 files
- [ ] Uses PSScriptAnalyzer for static analysis
- [ ] Runs on pull requests and pushes to main
- [ ] Fails build if Error-level issues found
- [ ] Provides clear output in CI logs
- [ ] Runs in parallel with other CI jobs for speed

## Technical Details

**Implementation Options**:
1. Add step to existing pester-tests.yml workflow
2. Create separate powershell-validation.yml workflow
3. Add to pre-existing validation workflow

**Recommended**: Add to existing pester-tests.yml as separate job

**PSScriptAnalyzer Settings**:
- Severity: Error (block), Warning (display), Information (ignore)
- Exclude test files from certain rules if needed
- Use .pssasettings.ps1 for repository-wide configuration

## References

- Session 36 retrospective
- Skill-CI-001: Pre-commit syntax validation (92% atomicity)
- Skill-Testing-003: Basic execution validation (88% atomicity)

## Related Issues

- #188 (Pre-commit hook validation) - Complementary defense layer

## Priority

P1 (HIGH) - Secondary defense after pre-commit hook

## Effort Estimate

60 minutes
