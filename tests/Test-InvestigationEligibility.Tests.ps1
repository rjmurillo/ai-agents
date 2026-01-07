#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Test-InvestigationEligibility.ps1 skill

.DESCRIPTION
    Tests the investigation eligibility check skill that allows agents
    to verify if staged files qualify for investigation-only QA skip.
    Verifies allowlist patterns match Validate-SessionProtocol.ps1 exactly.
#>

BeforeAll {
    # Import the canonical session validation script to get InvestigationAllowlist
    $validateProtocolPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-SessionProtocol.ps1"
    . $validateProtocolPath

    $scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "session" "scripts" "Test-InvestigationEligibility.ps1"
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Extract the allowlist variable for pattern verification
    if ($scriptContent -match '(?ms)\$investigationAllowlist\s*=\s*@\(.*?^\)') {
        $allowlistDef = $Matches[0]
        Invoke-Expression $allowlistDef
    }
}

Describe "Test-InvestigationEligibility.ps1" {
    Context "Allowlist Pattern Verification" {
        It "Contains expected investigation-only patterns" {
            $investigationAllowlist | Should -Contain '^[.]agents/sessions/'
            $investigationAllowlist | Should -Contain '^[.]agents/analysis/'
            $investigationAllowlist | Should -Contain '^[.]agents/retrospective/'
            $investigationAllowlist | Should -Contain '^[.]serena/memories($|/)'
            $investigationAllowlist | Should -Contain '^[.]agents/security/'
        }

        It "Has exactly 5 allowlist patterns matching Validate-SessionProtocol.ps1" {
            $investigationAllowlist.Count | Should -Be 5
        }

        It "Matches patterns with Validate-SessionProtocol.ps1 exactly" {
            # Get canonical patterns from Validate-SessionProtocol.ps1 (already sourced in BeforeAll)
            # $script:InvestigationAllowlist is now available from the sourced script

            # Compare each pattern
            foreach ($pattern in $investigationAllowlist) {
                $script:InvestigationAllowlist | Should -Contain $pattern -Because "Pattern '$pattern' should exist in both scripts"
            }

            foreach ($pattern in $script:InvestigationAllowlist) {
                $investigationAllowlist | Should -Contain $pattern -Because "Pattern '$pattern' from Validate-SessionProtocol.ps1 should exist in Test-InvestigationEligibility.ps1"
            }
        }
    }

    Context "Pattern Matching Behavior" {
        BeforeEach {
            # Patterns to test against
            $patterns = @(
                '^[.]agents/sessions/',
                '^[.]agents/analysis/',
                '^[.]agents/retrospective/',
                '^[.]serena/memories($|/)',
                '^[.]agents/security/'
            )
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

        It "Does NOT match code files" {
            $file = 'scripts/Validate-SessionProtocol.ps1'
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

        It "Matches .serena/memories directory itself" {
            $file = '.serena/memories'
            $normalizedFile = $file -replace '\\', '/'
            $matched = $patterns | Where-Object { $normalizedFile -match $_ }
            $matched | Should -Not -BeNullOrEmpty
        }
    }

    Context "Path Normalization" {
        BeforeEach {
            $patterns = @('^[.]agents/sessions/')
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
