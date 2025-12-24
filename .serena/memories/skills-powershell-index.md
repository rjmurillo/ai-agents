# PowerShell Skills Index

**Domain**: PowerShell patterns and best practices
**Skills**: 16
**Updated**: 2025-12-23

## Activation Vocabulary

| Keywords | File |
|----------|------|
| string interpolation variable colon scope qualifier subexpression braced syntax double-quoted | powershell-string-safety |
| herestring here-string terminator column zero whitespace `"@` `'@` leading syntax | powershell-string-safety |
| contains array null null-safety coercion single item case-insensitive ToLowerInvariant Where-Object | powershell-array-contains |
| regex AI output injection security hardened metacharacters labels milestones parsing sanitize | powershell-security-ai-output |
| Import-Module path prefix relative `./` PSModulePath CI workflow psm1 psd1 module file | powershell-cross-platform-ci |
| temp tempdir temporary GetTempPath cross-platform ARM Linux Windows macOS $env:TEMP | powershell-cross-platform-ci |
| exit code LASTEXITCODE persistence external command npm npx git false failure | powershell-cross-platform-ci |
| pester test combination ShouldProcess PassThru WhatIf parameter switch coverage | powershell-testing-patterns |
| path normalization Resolve-Path 8.3 short name Windows RUNNER~1 relative substring | powershell-testing-patterns |
| validation order exit-code external tool gh auth parameter before environment | powershell-testing-patterns |
| wildcard escape bracket `[?]` `[*]` -like operator literal character matching | powershell-testing-patterns |
| platform document assumption Windows Linux ARM revert migration cross-platform | powershell-testing-patterns |
| absolute path PSScriptRoot import module test hierarchy directory tree | powershell-testing-patterns |

## Coverage

| File | Skills | Lines |
|------|--------|-------|
| powershell-string-safety | 001, 007 | 80 |
| powershell-array-contains | 002, 003, 004 | 120 |
| powershell-security-ai-output | Security-001 | 60 |
| powershell-cross-platform-ci | 005, 006, 008 | 140 |
| powershell-testing-patterns | Testing-001, Testing-002, Param-001, Path-001, Wildcard-001, Platform-001, TestPath-001 | 458 |

## Related

- Source: PR #79, #212, #224, #255, #298
- Security index: `skills-security`
