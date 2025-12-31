#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-Session.ps1 investigation-only validation

.DESCRIPTION
    Tests the investigation-only allowlist verification logic per ADR-034.
    Validates that sessions modifying only investigation artifacts can skip QA.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1"

    # Extract the functions we need to test
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Extract the allowlist variable
    if ($scriptContent -match '\$script:InvestigationAllowlist\s*=\s*@\([^)]+\)') {
        $allowlistDef = $Matches[0]
        Invoke-Expression $allowlistDef
    }

    # Extract Test-InvestigationOnlyEligibility function (advanced function with CmdletBinding)
    $functionPattern = '(?ms)function Test-InvestigationOnlyEligibility\s*\{.*?^\}'
    if ($scriptContent -match $functionPattern) {
        $functionDef = $Matches[0]
        Invoke-Expression $functionDef
    }

    # Also extract Is-DocsOnly for comparison tests
    $docsOnlyPattern = '(?ms)function Is-DocsOnly\s*\([^)]*\)\s*\{.*?\n\}'
    if ($scriptContent -match $docsOnlyPattern) {
        $docsOnlyDef = $Matches[0]
        Invoke-Expression $docsOnlyDef
    }
}

Describe "InvestigationAllowlist" {
    It "Contains expected investigation-only paths" {
        $script:InvestigationAllowlist | Should -Contain '^\.agents/sessions/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/analysis/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/retrospective/'
        $script:InvestigationAllowlist | Should -Contain '^\.serena/memories/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/security/'
    }

    It "Has exactly 5 allowlist patterns" {
        $script:InvestigationAllowlist.Count | Should -Be 5
    }
}

Describe "Test-InvestigationOnlyEligibility" {
    Context "Empty or null input" {
        It "Returns eligible for empty file list" {
            $result = Test-InvestigationOnlyEligibility -Files @()
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }

        It "Returns eligible for null file list" {
            $result = Test-InvestigationOnlyEligibility -Files $null
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }
    }

    Context "Pure investigation sessions" {
        It "Returns eligible for session log only" {
            $files = @('.agents/sessions/2025-12-31-session-110.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }

        It "Returns eligible for analysis files" {
            $files = @('.agents/analysis/research-findings.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for retrospective files" {
            $files = @('.agents/retrospective/session-learnings.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for Serena memory files" {
            $files = @('.serena/memories/project-context.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for security assessment files" {
            $files = @('.agents/security/threat-assessment.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Returns eligible for multiple allowed paths combined" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/analysis/findings.md',
                '.serena/memories/context.md',
                '.agents/retrospective/learnings.md',
                '.agents/security/review.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
            $result.ImplementationFiles.Count | Should -Be 0
        }
    }

    Context "Implementation sessions (not investigation-only)" {
        It "Rejects code changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                'scripts/Validate-Session.ps1'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles | Should -Contain 'scripts/Validate-Session.ps1'
        }

        It "Rejects workflow changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.github/workflows/ci.yml'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles | Should -Contain '.github/workflows/ci.yml'
        }

        It "Rejects test file changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                'tests/Feature.Tests.ps1'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Rejects planning document changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/planning/feature-prd.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles | Should -Contain '.agents/planning/feature-prd.md'
        }

        It "Rejects architecture document changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/architecture/adr-001.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Rejects QA report changes" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                '.agents/qa/feature-qa-report.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Returns all implementation files when multiple present" {
            $files = @(
                '.agents/sessions/2025-12-31-session-110.md',
                'scripts/Script1.ps1',
                'scripts/Script2.ps1',
                'tests/Test.ps1'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
            $result.ImplementationFiles.Count | Should -Be 3
        }
    }

    Context "Path normalization" {
        It "Handles Windows-style backslashes" {
            $files = @('.agents\sessions\2025-12-31-session-110.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Handles mixed path separators" {
            $files = @(
                '.agents/sessions\2025-12-31-session-110.md',
                '.serena\memories/context.md'
            )
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }
    }

    Context "Edge cases" {
        It "Rejects similar but not matching paths" {
            # .agents/sessions-evil/ should NOT match .agents/sessions/
            $files = @('.agents/sessions-evil/malicious.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Rejects root-level .agents files" {
            $files = @('.agents/HANDOFF.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
        }

        It "Handles deeply nested investigation paths" {
            $files = @('.agents/sessions/2025/12/deep/session.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }
    }
}

Describe "Is-DocsOnly vs Test-InvestigationOnlyEligibility" {
    <#
    .SYNOPSIS
        Verify the distinction between docs-only and investigation-only
    #>

    It "Docs-only: pure markdown anywhere passes" {
        $files = @('README.md', 'docs/guide.md')
        $result = Is-DocsOnly $files
        $result | Should -BeTrue
    }

    It "Investigation-only: pure markdown outside allowed paths fails" {
        $files = @('README.md', 'docs/guide.md')
        $result = Test-InvestigationOnlyEligibility -Files $files
        $result.IsEligible | Should -BeFalse
    }

    It "Both pass for markdown in allowed paths" {
        $files = @('.agents/sessions/2025-12-31-session-110.md')
        $docsResult = Is-DocsOnly $files
        $docsResult | Should -BeTrue

        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeTrue
    }
}
