#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Test-InvestigationEligibility.ps1 skill

.DESCRIPTION
    Tests the investigation eligibility check skill that allows agents
    to verify if staged files qualify for investigation-only QA skip.
    Verifies allowlist patterns match ADR-034 specification.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "session" "scripts" "Test-InvestigationEligibility.ps1"
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Import the shared allowlist module (script now delegates to this)
    Import-Module (Join-Path $PSScriptRoot '../scripts/modules/InvestigationAllowlist.psm1') -Force
    $investigationAllowlist = Get-InvestigationAllowlist
}

Describe "Test-InvestigationEligibility.ps1" {
    Context "Allowlist Pattern Verification" {
        It "Contains expected investigation-only patterns" {
            $investigationAllowlist | Should -Contain '^\.agents/sessions/'
            $investigationAllowlist | Should -Contain '^\.agents/analysis/'
            $investigationAllowlist | Should -Contain '^\.agents/retrospective/'
            $investigationAllowlist | Should -Contain '^\.serena/memories($|/)'
            $investigationAllowlist | Should -Contain '^\.agents/security/'
            $investigationAllowlist | Should -Contain '^\.agents/memory/'
            $investigationAllowlist | Should -Contain '^\.agents/architecture/REVIEW-'
            $investigationAllowlist | Should -Contain '^\.agents/critique/'
            $investigationAllowlist | Should -Contain '^\.agents/memory/episodes/'
        }

        It "Has exactly 9 allowlist patterns (ADR-034 base + Issue #732 extensions)" {
            $investigationAllowlist.Count | Should -Be 9
        }
    }

    Context "Pattern Matching Behavior" {
        BeforeEach {
            $patterns = Get-InvestigationAllowlist
        }

        It "Matches session log files" {
            $file = '.agents/sessions/2025-12-31-session-110.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches analysis files" {
            $file = '.agents/analysis/research-findings.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches retrospective files" {
            $file = '.agents/retrospective/session-learnings.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches Serena memory files" {
            $file = '.serena/memories/context.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches security assessment files" {
            $file = '.agents/security/threat-review.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches memory infrastructure files" {
            $file = '.agents/memory/causality/causal-graph.json'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches ADR review artifacts" {
            $file = '.agents/architecture/REVIEW-ADR-042.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches critique debate logs" {
            $file = '.agents/critique/debate-log.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Matches memory episode extractions" {
            $file = '.agents/memory/episodes/episode-001.json'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Does NOT match code files" {
            $file = 'scripts/Validate-Session.ps1'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -BeNullOrEmpty
        }

        It "Does NOT match workflow files" {
            $file = '.github/workflows/ci.yml'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -BeNullOrEmpty
        }

        It "Does NOT match planning documents" {
            $file = '.agents/planning/feature-prd.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -BeNullOrEmpty
        }

        It "Does NOT match .agents/sessions-evil/ path traversal" {
            $file = '.agents/sessions-evil/malicious.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -BeNullOrEmpty
        }

        It "Does NOT match .serena/memoriesX/ path traversal" {
            $file = '.serena/memoriesX/evil.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -BeNullOrEmpty
        }

        It "Does NOT match non-REVIEW architecture files" {
            $file = '.agents/architecture/ADR-042.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -BeNullOrEmpty
        }

        It "Matches .serena/memories directory itself" {
            $file = '.serena/memories'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }
    }

    Context "Path Normalization" {
        BeforeEach {
            $patterns = @('^\.agents/sessions/')
        }

        It "Normalizes Windows backslashes to forward slashes" {
            $file = '.agents\sessions\2025-12-31-session-110.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }

        It "Handles mixed path separators" {
            $file = '.agents/sessions\nested\file.md'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }
    }

    Context "Shared Module Import" {
        It "Script imports InvestigationAllowlist module" {
            $scriptContent | Should -Match 'InvestigationAllowlist'
            $scriptContent | Should -Match 'Import-Module'
        }

        It "Script uses Test-FileMatchesAllowlist function" {
            $scriptContent | Should -Match 'Test-FileMatchesAllowlist'
        }
    }

    Context "Git Output Parsing" {
        It "Script content contains proper newline splitting" {
            # The actual pattern uses backtick escapes: -split "`r?`n"
            $scriptContent | Should -Match '-split\s+'
            $scriptContent | Should -Match '`r\?`n'
        }

        It "Script content filters empty lines" {
            $scriptContent | Should -Match 'Where-Object\s*\{'
        }
    }

    Context "ErrorActionPreference" {
        It "Sets ErrorActionPreference to Stop" {
            $scriptContent | Should -Match '\$ErrorActionPreference\s*=\s*''Stop'''
        }
    }

    Context "JSON Output Structure" {
        It "Outputs Eligible field" {
            $scriptContent | Should -Match 'Eligible\s*='
        }

        It "Outputs StagedFiles field" {
            $scriptContent | Should -Match 'StagedFiles\s*='
        }

        It "Outputs Violations field" {
            $scriptContent | Should -Match 'Violations\s*='
        }

        It "Outputs AllowedPaths field" {
            $scriptContent | Should -Match 'AllowedPaths\s*='
        }

        It "Outputs Error field on git failure" {
            $scriptContent | Should -Match 'Error\s*='
        }
    }

    Context "Error Handling" {
        It "Checks LASTEXITCODE after git command" {
            $scriptContent | Should -Match '\$LASTEXITCODE\s*-ne\s*0'
        }

        It "Handles git errors gracefully with Error field" {
            $scriptContent | Should -Match 'Not in a git repository'
        }

        It "Always exits with code 0 (eligibility in output)" {
            $scriptContent | Should -Match 'exit\s+0'
            $scriptContent | Should -Not -Match 'exit\s+1'
        }
    }
}
