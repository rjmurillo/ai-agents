#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-Session.ps1 investigation-only validation

.DESCRIPTION
    Tests the investigation-only allowlist verification logic per ADR-034.
    Validates that sessions modifying only investigation artifacts can skip QA.
#>

BeforeAll {
    # Import the consolidated session validation module
    $modulePath = Join-Path $PSScriptRoot ".." "scripts" "modules" "SessionValidation.psm1"
    Import-Module $modulePath -Force

    # The functions Test-InvestigationOnlyEligibility and Get-ImplementationFiles
    # have been moved to scripts/modules/SessionValidation.psm1 during consolidation
}

Describe "InvestigationAllowlist" {
    It "Contains expected investigation-only paths" {
        $script:InvestigationAllowlist | Should -Contain '^\.agents/sessions/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/analysis/'
        $script:InvestigationAllowlist | Should -Contain '^\.agents/retrospective/'
        $script:InvestigationAllowlist | Should -Contain '^\.serena/memories($|/)'
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

        It "Returns eligible for Serena memories directory itself" {
            # Tests the ($|/) pattern matches end-of-string
            $files = @('.serena/memories')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeTrue
        }

        It "Rejects .serena/memories prefix bypass" {
            # .serena/memoriesX should NOT match .serena/memories($|/)
            $files = @('.serena/memoriesX/evil.md')
            $result = Test-InvestigationOnlyEligibility -Files $files
            $result.IsEligible | Should -BeFalse
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

Describe "AuditArtifacts" {
    It "Contains expected audit artifact paths" {
        $script:AuditArtifacts | Should -Contain '^\.agents/sessions/'
        $script:AuditArtifacts | Should -Contain '^\.agents/analysis/'
        $script:AuditArtifacts | Should -Contain '^\.serena/memories($|/)'
    }

    It "Has exactly 3 audit artifact patterns" {
        $script:AuditArtifacts.Count | Should -Be 3
    }
}

Describe "Get-ImplementationFiles" {
    Context "Empty or null input" {
        It "Returns empty array for empty file list" {
            $result = Get-ImplementationFiles -Files @()
            $result | Should -BeNullOrEmpty
            $result.Count | Should -Be 0
        }

        It "Returns empty array for null file list" {
            $result = Get-ImplementationFiles -Files $null
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Session logs (audit trail)" {
        It "Filters out session log files" {
            $files = @('.agents/sessions/2026-01-01-session-01.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out nested session log files" {
            $files = @('.agents/sessions/2026/01/deep/session.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Analysis artifacts" {
        It "Filters out analysis files" {
            $files = @('.agents/analysis/research-findings.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out nested analysis files" {
            $files = @('.agents/analysis/investigations/deep/report.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Serena memory files" {
        It "Filters out memory files" {
            $files = @('.serena/memories/project-context.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out deeply nested memory files" {
            $files = @('.serena/memories/category/subcategory/memory.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Filters out .serena/memories directory reference" {
            $files = @('.serena/memories')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Non-audit files preserved" {
        It "Preserves PowerShell scripts" {
            $files = @('scripts/Validate-Session.ps1')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain 'scripts/Validate-Session.ps1'
        }

        It "Preserves ADR files" {
            $files = @('.agents/architecture/ADR-001.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/architecture/ADR-001.md'
        }

        It "Preserves planning files" {
            $files = @('.agents/planning/feature-prd.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/planning/feature-prd.md'
        }

        It "Preserves QA reports" {
            $files = @('.agents/qa/feature-qa-report.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/qa/feature-qa-report.md'
        }

        It "Preserves workflow files" {
            $files = @('.github/workflows/ci.yml')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.github/workflows/ci.yml'
        }

        It "Preserves test files" {
            $files = @('tests/Feature.Tests.ps1')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain 'tests/Feature.Tests.ps1'
        }

        It "Preserves root-level .agents files" {
            $files = @('.agents/HANDOFF.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/HANDOFF.md'
        }

        It "Preserves critique files" {
            $files = @('.agents/critique/review.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/critique/review.md'
        }

        It "Preserves retrospective files (not in audit artifacts)" {
            $files = @('.agents/retrospective/learnings.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/retrospective/learnings.md'
        }

        It "Preserves security assessment files (not in audit artifacts)" {
            $files = @('.agents/security/threat-model.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/security/threat-model.md'
        }
    }

    Context "Mixed audit and implementation files" {
        It "Filters audit, preserves implementation from mixed input" {
            $files = @(
                '.agents/sessions/2026-01-01-session-01.md',
                'scripts/Validate-Session.ps1'
            )
            $result = Get-ImplementationFiles -Files $files
            $result.Count | Should -Be 1
            $result | Should -Contain 'scripts/Validate-Session.ps1'
            $result | Should -Not -Contain '.agents/sessions/2026-01-01-session-01.md'
        }

        It "Correctly separates multiple audit and implementation files" {
            $files = @(
                '.agents/sessions/2026-01-01-session-01.md',
                '.agents/analysis/findings.md',
                '.serena/memories/context.md',
                'scripts/Script1.ps1',
                'scripts/Script2.ps1',
                '.agents/architecture/ADR-001.md'
            )
            $result = Get-ImplementationFiles -Files $files
            $result.Count | Should -Be 3
            $result | Should -Contain 'scripts/Script1.ps1'
            $result | Should -Contain 'scripts/Script2.ps1'
            $result | Should -Contain '.agents/architecture/ADR-001.md'
            $result | Should -Not -Contain '.agents/sessions/2026-01-01-session-01.md'
            $result | Should -Not -Contain '.agents/analysis/findings.md'
            $result | Should -Not -Contain '.serena/memories/context.md'
        }

        It "Returns only ADR when session log + ADR staged (docs-only scenario)" {
            $files = @(
                '.agents/sessions/2026-01-01-session-01.md',
                '.agents/architecture/ADR-037.md'
            )
            $result = Get-ImplementationFiles -Files $files
            $result.Count | Should -Be 1
            $result | Should -Contain '.agents/architecture/ADR-037.md'
        }
    }

    Context "Path normalization" {
        It "Handles Windows-style backslashes" {
            $files = @('.agents\sessions\2026-01-01-session-01.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }

        It "Handles mixed path separators" {
            $files = @(
                '.agents/sessions\2026-01-01.md',
                '.serena\memories/context.md'
            )
            $result = Get-ImplementationFiles -Files $files
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Edge cases - path traversal prevention" {
        It "Does not filter similar-but-different paths (.agents/sessions-evil)" {
            $files = @('.agents/sessions-evil/malicious.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/sessions-evil/malicious.md'
        }

        It "Does not filter .serena/memoriesX prefix bypass" {
            $files = @('.serena/memoriesX/evil.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.serena/memoriesX/evil.md'
        }

        It "Does not filter .agents/analysisX prefix bypass" {
            $files = @('.agents/analysisX/evil.md')
            $result = Get-ImplementationFiles -Files $files
            $result | Should -Contain '.agents/analysisX/evil.md'
        }
    }
}

Describe "Get-ImplementationFiles vs Test-InvestigationOnlyEligibility" {
    <#
    .SYNOPSIS
        Verify the distinction between audit filtering and investigation eligibility

    .NOTES
        AuditArtifacts filters: sessions, analysis, memories
        InvestigationAllowlist allows: sessions, analysis, memories, retrospective, security

        Key difference: retrospective and security are investigation-eligible but NOT audit artifacts
    #>

    It "AuditArtifacts is subset of InvestigationAllowlist" {
        # Session logs, analysis, memories are in both
        $auditPatterns = @(
            '^\.agents/sessions/',
            '^\.agents/analysis/',
            '^\.serena/memories($|/)'
        )
        foreach ($pattern in $auditPatterns) {
            $script:InvestigationAllowlist | Should -Contain $pattern
        }
    }

    It "Retrospective is investigation-eligible but not audit artifact" {
        $files = @('.agents/retrospective/learnings.md')

        # Investigation: eligible
        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeTrue

        # Audit: NOT filtered (preserved as implementation)
        $implResult = Get-ImplementationFiles -Files $files
        $implResult | Should -Contain '.agents/retrospective/learnings.md'
    }

    It "Security is investigation-eligible but not audit artifact" {
        $files = @('.agents/security/threat-model.md')

        # Investigation: eligible
        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeTrue

        # Audit: NOT filtered (preserved as implementation)
        $implResult = Get-ImplementationFiles -Files $files
        $implResult | Should -Contain '.agents/security/threat-model.md'
    }

    It "Session log + ADR: filtered by audit, rejected by investigation" {
        $files = @(
            '.agents/sessions/2026-01-01-session-01.md',
            '.agents/architecture/ADR-001.md'
        )

        # Audit filtering: removes session log, keeps ADR
        $implResult = Get-ImplementationFiles -Files $files
        $implResult.Count | Should -Be 1
        $implResult | Should -Contain '.agents/architecture/ADR-001.md'

        # Investigation: NOT eligible (ADR is implementation)
        $investResult = Test-InvestigationOnlyEligibility -Files $files
        $investResult.IsEligible | Should -BeFalse
        $investResult.ImplementationFiles | Should -Contain '.agents/architecture/ADR-001.md'
    }
}
