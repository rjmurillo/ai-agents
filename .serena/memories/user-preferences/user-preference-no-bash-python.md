# User Preference: No Bash or Python

**Date**: 2025-12-18
**Scope**: ai-agents repository

## Preference

User does NOT want bash or Python scripts in this repository.

**Rationale**:

- PowerShell is the standard for this project
- Consistency in tooling and testing
- All existing infrastructure uses PowerShell

## Exceptions

None. All scripts should be PowerShell.

## Related

- GitHub skill already provides tested PowerShell implementations
- Pester tests for PowerShell scripts
- Build scripts use PowerShell
- GitHub Actions workflows should use `shell: pwsh` instead of default bash

## Action

When implementing new functionality:

1. Check if GitHub skill already provides it (`.claude/skills/github/`)
2. If not, implement in PowerShell
3. Never create bash or Python scripts
4. For workflows, use `shell: pwsh` directive

## Historical Context

- **2025-12-18**: Removed .github/scripts/ai-review-common.sh (removed) and `.github/scripts/ai-review-common.bats`
- Converted all AI workflow steps to use PowerShell module `.github/scripts/AIReviewCommon.psm1`
- Added `Send-PRComment`, `Send-IssueComment`, `Get-VerdictEmoji` functions to the module
