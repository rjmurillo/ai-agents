# Skill-Creator-006: TOC Requirement for Long Files

## Statement

Files exceeding 100 lines SHOULD have a table of contents at the top. TOC enables Claude to navigate to relevant sections without scanning entire file.

## Context

When writing or reviewing skill modules, documentation, or any file Claude may read.

## Pattern

**Bad (long file, no TOC)**:

```powershell
# GitHubHelpers.psm1
function Test-GitHubNameValid { ... }
function Get-RepoInfo { ... }
# ... 400+ lines ...
```

**Good (TOC at top)**:

```powershell
# GitHubHelpers.psm1
#
# Table of Contents:
# - Input Validation: Test-GitHubNameValid, Test-SafeFilePath, Assert-ValidBodyFile
# - Repository: Get-RepoInfo, Resolve-RepoParams
# - Authentication: Test-GhAuthenticated, Assert-GhAuthenticated
# - Error Handling: Write-ErrorAndExit
# - API Helpers: Invoke-GhApiPaginated
# - Issue Comments: Get-IssueComments, Update-IssueComment, New-IssueComment

function Test-GitHubNameValid { ... }
```

## Why This Matters

- Claude uses TOC to identify relevant section without full scan
- Reduces cognitive load and token waste
- 100 lines = threshold where linear scanning becomes inefficient

## Format

```markdown
## Table of Contents

- [Section 1](#section-1) - Brief description
- [Section 2](#section-2) - Brief description
```

Or for code files:

```text
# Table of Contents:
# - Section 1: Function1, Function2
# - Section 2: Function3, Function4
```

## Evidence

PR #255 (2025-12-22): TOC added to `GitHubHelpers.psm1` (400+ lines). Commit `e8635fc`.

## Metrics

- Atomicity: 93%
- Category: documentation, navigation
- Created: 2025-12-22
- Tag: skill-creator
- Validated: 1 (PR #255)

## Related Skills

- Skill-Documentation-004 (pattern consistency)
- Skill-Creator-004 (reference extraction)

## Related

- [creator-001-frontmatter-trigger-specification](creator-001-frontmatter-trigger-specification.md)
- [creator-002-token-efficiency-comment-stripping](creator-002-token-efficiency-comment-stripping.md)
- [creator-003-test-separation-skill-directory](creator-003-test-separation-skill-directory.md)
- [creator-004-reference-material-extraction](creator-004-reference-material-extraction.md)
- [creator-005-schema-redundancy-elimination](creator-005-schema-redundancy-elimination.md)
